"""Security -> Users service.

Holds the multi-resource logic that doesn't belong in a route handler: the
compound (atomic) user create/update that fans a single payload across users +
user_offices + memberships + ip_rules + preferences + time-clock + login
restrictions, plus setup-metadata, the per-user settings upserts, and the
self-service password change.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import filestore
from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, UnauthorizedError, ValidationError
from app.core.security import hash_password, verify_password
from app.db.models import (
    Definition,
    User,
    UserGroupMembership,
    UserIpRule,
    UserLoginRestriction,
    UserOffice,
    UserPreference,
    UserTimeClockConfig,
)

# Fallback option sets (used when no `definitions` rows are seeded for the group).
_DEFAULT_ROLES = ["admin", "provider", "front_desk", "staff", "super_admin"]
_DEFAULT_ACCESS_LEVELS = ["full", "limited", "read_only", "none"]
_DEFAULT_OVERTIME_METHODS = ["none", "weekly_40", "daily_8", "california"]

# Static schema for the preferences tab (option lists per preference key).
_PREFERENCES_SCHEMA = {
    "startup_screen": ["scheduler", "patients", "dashboard", "reports"],
    "default_perio_screen": ["chart", "exam", "summary"],
    "navigation_search": ["patient", "appointment", "claim"],
    "search_by": ["name", "chart_no", "phone", "dob"],
    "referral_view": ["all", "incoming", "outgoing"],
}


def _options_from_definitions(db: Session, tenant_id: int, group_code: str, fallback: list[str]) -> list[dict]:
    rows = db.execute(
        select(Definition.key1, Definition.description).where(
            Definition.tenant_id == tenant_id,
            Definition.group_code == group_code,
            Definition.is_active.is_(True),
        )
    ).all()
    if rows:
        return [{"value": k, "label": d or k} for k, d in rows]
    return [{"value": v, "label": v.replace("_", " ").title()} for v in fallback]


def get_setup_metadata(db: Session, tenant_id: int) -> dict:
    return {
        "roles": _options_from_definitions(db, tenant_id, "user_role", _DEFAULT_ROLES),
        "patient_access_levels": _options_from_definitions(
            db, tenant_id, "patient_access_level", _DEFAULT_ACCESS_LEVELS
        ),
        "overtime_methods": _options_from_definitions(
            db, tenant_id, "overtime_method", _DEFAULT_OVERTIME_METHODS
        ),
        "time_clock_config": {"overtime_methods": _DEFAULT_OVERTIME_METHODS},
        "user_preferences_schema": _PREFERENCES_SCHEMA,
    }


def list_roles(db: Session, tenant_id: int) -> list[dict]:
    return _options_from_definitions(db, tenant_id, "user_role", _DEFAULT_ROLES)


# ── per-section reconcilers (operate on the session; caller commits) ──────────
def _set_offices(db: Session, user: User, office_ids: list[int], home_office_id: int | None) -> None:
    existing = {l.office_id: l for l in db.execute(
        select(UserOffice).where(UserOffice.user_id == user.id)).scalars()}
    desired = set(office_ids)
    if home_office_id is not None:
        desired.add(home_office_id)
    for oid, link in existing.items():
        if oid not in desired:
            db.delete(link)
    for oid in desired:
        link = existing.get(oid) or UserOffice(user_id=user.id, office_id=oid)
        link.is_primary = (oid == home_office_id)
        db.add(link)


def _set_groups(db: Session, user: User, tenant_id: int, group_ids: list[int]) -> None:
    existing = {m.group_id: m for m in db.execute(
        select(UserGroupMembership).where(UserGroupMembership.user_id == user.id)).scalars()}
    desired = set(group_ids)
    for gid, link in existing.items():
        if gid not in desired:
            db.delete(link)
    for gid in desired - set(existing):
        db.add(UserGroupMembership(tenant_id=tenant_id, user_id=user.id, group_id=gid))


def _set_ip_rules(db: Session, user: User, tenant_id: int, rules: list[dict]) -> None:
    for row in db.execute(select(UserIpRule).where(UserIpRule.user_id == user.id)).scalars():
        db.delete(row)
    for r in rules:
        db.add(UserIpRule(tenant_id=tenant_id, user_id=user.id, **r))


def _set_preferences(db: Session, user: User, tenant_id: int, prefs: dict[str, str]) -> None:
    existing = {p.pref_key: p for p in db.execute(
        select(UserPreference).where(UserPreference.user_id == user.id)).scalars()}
    for key, value in prefs.items():
        if key in existing:
            existing[key].pref_value = value
        else:
            db.add(UserPreference(tenant_id=tenant_id, user_id=user.id, pref_key=key, pref_value=value))


def _set_time_clock(db: Session, user: User, tenant_id: int, data: dict) -> UserTimeClockConfig:
    row = db.execute(
        select(UserTimeClockConfig).where(UserTimeClockConfig.user_id == user.id)
    ).scalar_one_or_none()
    if row is None:
        row = UserTimeClockConfig(tenant_id=tenant_id, user_id=user.id)
        db.add(row)
    for k, v in data.items():
        setattr(row, k, v)
    return row


def _set_login_restrictions(db: Session, user: User, tenant_id: int, data: dict) -> UserLoginRestriction:
    row = db.execute(
        select(UserLoginRestriction).where(UserLoginRestriction.user_id == user.id)
    ).scalar_one_or_none()
    if row is None:
        row = UserLoginRestriction(tenant_id=tenant_id, user_id=user.id)
        db.add(row)
    for k, v in data.items():
        setattr(row, k, v)
    return row


_IDENTITY_FIELDS = {
    "email", "username", "first_name", "last_name", "phone", "role",
    "is_active", "must_change_password", "patient_access_level",
    # structural gaps 1-4 (users_missing_fields dev-report); image_url via upload endpoint
    "short_id", "report_access_provider_id", "custom_1", "custom_2", "signature_data",
}


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("User violates a uniqueness/reference constraint",
                            details=str(getattr(exc, "orig", exc))) from exc


def _flush(db: Session) -> None:
    # Uniqueness violations (e.g. duplicate short_id / username) surface at flush,
    # before _commit's guard — convert them to a 409 here too.
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("User violates a uniqueness/reference constraint",
                            details=str(getattr(exc, "orig", exc))) from exc


def create_complete(db: Session, tenant_id: int, payload: dict, created_by: int | None) -> User:
    user = User(
        tenant_id=tenant_id,
        email=payload["email"],
        username=payload["username"],
        password_hash=hash_password(payload["password"]),
        first_name=payload.get("first_name"),
        last_name=payload.get("last_name"),
        phone=payload.get("phone"),
        role=payload.get("role", "staff"),
        must_change_password=payload.get("must_change_password", False),
        patient_access_level=payload.get("patient_access_level"),
        short_id=payload.get("short_id"),
        report_access_provider_id=payload.get("report_access_provider_id"),
        custom_1=payload.get("custom_1"),
        custom_2=payload.get("custom_2"),
        signature_data=payload.get("signature_data"),
        created_by=created_by,
    )
    db.add(user)
    _flush(db)  # assign user.id (converts uniqueness violations to 409)
    _apply_related(db, user, tenant_id, payload, is_create=True)
    _commit(db)
    db.refresh(user)
    return user


def update_complete(db: Session, tenant_id: int, user_id: int, payload: dict,
                    updated_by: int | None = None) -> User:
    user = db.execute(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if user is None:
        raise NotFoundError(f"User '{user_id}' was not found")
    for field in _IDENTITY_FIELDS & payload.keys():
        setattr(user, field, payload[field])
    if "password" in payload and payload["password"]:
        user.password_hash = hash_password(payload["password"])
    user.updated_by = updated_by  # gap #8: record the editing actor
    _apply_related(db, user, tenant_id, payload, is_create=False)
    _commit(db)
    db.refresh(user)
    return user


def _apply_related(db: Session, user: User, tenant_id: int, payload: dict, *, is_create: bool) -> None:
    if is_create or "assigned_offices" in payload or "home_office_id" in payload:
        _set_offices(db, user, payload.get("assigned_offices") or [], payload.get("home_office_id"))
    if is_create or "group_ids" in payload:
        _set_groups(db, user, tenant_id, payload.get("group_ids") or [])
    if is_create or "ip_rules" in payload:
        _set_ip_rules(db, user, tenant_id, payload.get("ip_rules") or [])
    if payload.get("preferences"):
        _set_preferences(db, user, tenant_id, payload["preferences"])
    if payload.get("time_clock") is not None:
        _set_time_clock(db, user, tenant_id, payload["time_clock"])
    if payload.get("login_restrictions") is not None:
        _set_login_restrictions(db, user, tenant_id, payload["login_restrictions"])


# ── standalone per-user settings (Gaps 3,4) ──────────────────────────────────
def _require_user(db: Session, user_id: int, tenant_id: int) -> User:
    user = db.execute(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if user is None:
        raise NotFoundError(f"User '{user_id}' was not found")
    return user


def get_time_clock(db: Session, user_id: int, tenant_id: int) -> UserTimeClockConfig:
    _require_user(db, user_id, tenant_id)
    row = db.execute(
        select(UserTimeClockConfig).where(UserTimeClockConfig.user_id == user_id)
    ).scalar_one_or_none()
    if row is None:
        row = UserTimeClockConfig(tenant_id=tenant_id, user_id=user_id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def set_time_clock(db: Session, user_id: int, tenant_id: int, data: dict) -> UserTimeClockConfig:
    user = _require_user(db, user_id, tenant_id)
    row = _set_time_clock(db, user, tenant_id, data)
    _commit(db)
    db.refresh(row)
    return row


def get_security_settings(db: Session, user_id: int, tenant_id: int) -> dict:
    user = _require_user(db, user_id, tenant_id)
    row = db.execute(
        select(UserLoginRestriction).where(UserLoginRestriction.user_id == user_id)
    ).scalar_one_or_none()
    restrictions = {
        "is_24_7": row.is_24_7 if row else True,
        "allowed_days": row.allowed_days if row else None,
        "start_time": row.start_time if row else None,
        "end_time": row.end_time if row else None,
    }
    return {"user_id": user_id, "patient_access_level": user.patient_access_level,
            "login_restrictions": restrictions}


def set_security_settings(db: Session, user_id: int, tenant_id: int, payload: dict,
                          updated_by: int | None = None) -> dict:
    user = _require_user(db, user_id, tenant_id)
    if "patient_access_level" in payload:
        user.patient_access_level = payload["patient_access_level"]
    if payload.get("login_restrictions") is not None:
        _set_login_restrictions(db, user, tenant_id, payload["login_restrictions"])
    user.updated_by = updated_by  # gap #8
    _commit(db)
    return get_security_settings(db, user_id, tenant_id)


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.password_hash):
        raise UnauthorizedError("Current password is incorrect", code="invalid_password")
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    db.commit()


# ── User image / avatar (users_missing_fields dev-report gap #5) ─────────────
def save_user_image(db: Session, user_id: int, tenant_id: int, filename: str,
                    content_type: str, data: bytes, updated_by: int | None = None) -> User:
    user = _require_user(db, user_id, tenant_id)
    if content_type not in settings.LOGO_ALLOWED_TYPES:
        raise ValidationError(
            f"Unsupported image type '{content_type}'. Allowed: "
            f"{', '.join(settings.LOGO_ALLOWED_TYPES)}",
            code="invalid_image_type",
        )
    if len(data) > settings.LOGO_MAX_BYTES:
        raise ValidationError(
            f"Image exceeds {settings.LOGO_MAX_BYTES // (1024 * 1024)} MB limit",
            code="image_too_large",
        )
    # Replace any prior avatar so we don't orphan files on disk.
    filestore.delete_file(_image_rel_path(user.image_url))
    _, url = filestore.save_file("user_images", filename, data)
    user.image_url = url
    user.updated_by = updated_by  # gap #8
    db.commit()
    db.refresh(user)
    return user


def delete_user_image(db: Session, user_id: int, tenant_id: int,
                      updated_by: int | None = None) -> None:
    user = _require_user(db, user_id, tenant_id)
    filestore.delete_file(_image_rel_path(user.image_url))
    user.image_url = None
    user.updated_by = updated_by  # gap #8
    db.commit()


def _image_rel_path(image_url: str | None) -> str | None:
    """Map a stored avatar URL back to its filestore-relative path."""
    if not image_url:
        return None
    return f"user_images/{image_url.rsplit('/', 1)[-1]}"


# ── Audit Information panel (users dev-report gap #8): id -> display name ─────
def _display_name(u: User) -> str:
    full = " ".join(p for p in (u.first_name, u.last_name) if p).strip()
    return full or u.username


def resolve_user_names(db: Session, user_ids: set[int]) -> dict[int, str]:
    """Batch-resolve user ids to display names (no N+1)."""
    ids = {i for i in user_ids if i is not None}
    if not ids:
        return {}
    rows = db.execute(select(User).where(User.id.in_(ids))).scalars().all()
    return {u.id: _display_name(u) for u in rows}


def attach_audit_names(db: Session, users: User | list[User]) -> None:
    """Set transient ``created_by_name`` / ``updated_by_name`` on user ORM objects.

    These are non-mapped attributes Pydantic's ``from_attributes`` reads when
    serialising ``UserRead`` (gap #8). Mutates in place.
    """
    items = [users] if isinstance(users, User) else list(users)
    wanted: set[int] = set()
    for u in items:
        if u.created_by is not None:
            wanted.add(u.created_by)
        if u.updated_by is not None:
            wanted.add(u.updated_by)
    names = resolve_user_names(db, wanted)
    for u in items:
        u.created_by_name = names.get(u.created_by) if u.created_by is not None else None
        u.updated_by_name = names.get(u.updated_by) if u.updated_by is not None else None


# ── Gap 6: list users filtered by office / role ──────────────────────────────
def office_user_ids(db: Session, office_id: int) -> list[int]:
    return list(db.execute(
        select(UserOffice.user_id).where(UserOffice.office_id == office_id)
    ).scalars().all())
