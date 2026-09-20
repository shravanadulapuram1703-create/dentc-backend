"""My Page self-service logic (profile, tasks, preferences, notifications).

Everything is derived from the auth token — a user only ever reads/writes their
own rows (MP tenant-isolation). No client-supplied user id is trusted.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.db.models import (
    Notification,
    Provider,
    User,
    UserPreference,
    UserTask,
)

_PREF_KEY = "ui_prefs"  # MP-4: single opaque JSON blob per user


# ── MP-1: profile ─────────────────────────────────────────────────────────────
def update_self(db: Session, user: User, data: dict) -> User:
    for key in ("first_name", "last_name", "phone", "email"):
        if key in data:
            setattr(user, key, data[key])
    # OFF-SCOPE-3: the working office is validated against the caller's own
    # assignments (a user cannot remember an office they are not assigned to);
    # ``None`` clears it. Resolved here rather than at the route so the generic
    # PATCH /users/me shares the rule.
    if "current_office_id" in data:
        office_id = data["current_office_id"]
        if office_id is not None:
            from app.services import office_scope_service, permission_service

            assigned = office_scope_service.assigned_office_ids(db, user.id, user.tenant_id)
            privileged = bool(
                permission_service.office_rights(db, user)
                & {permission_service.OFFICES_VIEW_ALL, permission_service.OFFICES_SWITCH_ANY}
            )
            if int(office_id) not in assigned and not privileged and assigned:
                from app.core.exceptions import ForbiddenError

                raise ForbiddenError(
                    f"Office '{office_id}' is not assigned to you",
                    code="office_not_assigned",
                    details={"office_id": int(office_id), "field": "current_office_id"},
                )
        user.current_office_id = office_id
    # OFF-SCOPE-3: cross-device restore of the default patient (validated against
    # the tenant; a missing/cross-tenant patient is rejected, ``None`` clears).
    # Validated in-memory (no intermediate commit) so a bad patient id rolls the
    # whole PATCH back rather than half-applying the office change.
    if "last_patient_id" in data:
        pid = data["last_patient_id"]
        if pid is not None:
            from app.services import patient_context_service

            if patient_context_service._valid_patient(db, pid, user.tenant_id) is None:
                raise NotFoundError(f"Patient '{pid}' was not found")
        user.last_patient_id = pid
    try:
        db.commit()
    except Exception as exc:  # unique email, etc.  # noqa: BLE001
        db.rollback()
        raise ConflictError("Could not update profile (email may be in use)",
                            details=str(getattr(exc, "orig", exc))) from exc
    db.refresh(user)
    return user


# ── MP-7: the provider row linked to this user ───────────────────────────────
def linked_provider_id(db: Session, user_id: int) -> str | None:
    return db.execute(
        select(Provider.id).where(Provider.user_id == user_id, Provider.is_active.is_(True))
    ).scalars().first()


# ── MP-3: tasks ───────────────────────────────────────────────────────────────
def list_tasks(db: Session, user: User) -> list[UserTask]:
    return list(db.execute(
        select(UserTask).where(UserTask.user_id == user.id)
        .order_by(UserTask.is_done.asc(), UserTask.due_date.asc().nulls_last(), UserTask.id.desc())
    ).scalars().all())


def create_task(db: Session, user: User, data: dict) -> UserTask:
    task = UserTask(tenant_id=user.tenant_id, user_id=user.id, **data)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _own_task(db: Session, user: User, task_id: int) -> UserTask:
    task = db.get(UserTask, task_id)
    if task is None or task.user_id != user.id:
        raise NotFoundError(f"Task '{task_id}' was not found")
    return task


def update_task(db: Session, user: User, task_id: int, data: dict) -> UserTask:
    task = _own_task(db, user, task_id)
    for key, value in data.items():
        setattr(task, key, value)
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, user: User, task_id: int) -> None:
    task = _own_task(db, user, task_id)
    db.delete(task)
    db.commit()


# ── MP-4: preferences blob ────────────────────────────────────────────────────
def get_preferences(db: Session, user: User) -> dict:
    row = db.execute(
        select(UserPreference).where(
            UserPreference.user_id == user.id, UserPreference.pref_key == _PREF_KEY
        )
    ).scalar_one_or_none()
    if row is None or not row.pref_value:
        return {}
    try:
        return json.loads(row.pref_value)
    except (ValueError, TypeError):
        return {}


def set_preferences(db: Session, user: User, preferences: dict) -> dict:
    row = db.execute(
        select(UserPreference).where(
            UserPreference.user_id == user.id, UserPreference.pref_key == _PREF_KEY
        )
    ).scalar_one_or_none()
    payload = json.dumps(preferences)
    if row is None:
        row = UserPreference(tenant_id=user.tenant_id, user_id=user.id,
                             pref_key=_PREF_KEY, pref_value=payload)
        db.add(row)
    else:
        row.pref_value = payload
    db.commit()
    return preferences


# ── MP-6: notifications ───────────────────────────────────────────────────────
def list_notifications(db: Session, user: User, *, unread_only: bool = False, limit: int = 50) -> dict:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    items = list(db.execute(
        stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)
    ).scalars().all())
    unread = db.execute(
        select(func.count()).select_from(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
    ).scalar_one()
    return {"unread_count": unread, "items": items}


def mark_notification_read(db: Session, user: User, notif_id: int) -> Notification:
    notif = db.get(Notification, notif_id)
    if notif is None or notif.user_id != user.id:
        raise NotFoundError(f"Notification '{notif_id}' was not found")
    if not notif.is_read:
        notif.is_read = True
        notif.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(notif)
    return notif


def mark_all_read(db: Session, user: User) -> int:
    rows = db.execute(
        select(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False))
    ).scalars().all()
    now = datetime.now(timezone.utc)
    for n in rows:
        n.is_read = True
        n.read_at = now
    db.commit()
    return len(rows)
