"""Security -> Groups service: rights catalog, group->rights assignment, copy.

Resolves docs/users/groups_backend_devreport.md gaps #1–#3. The group's rights are
stored normalised in ``user_group_rights`` (group_id, permission_id); the API speaks
in permission *codes* (the frontend's slug), so this layer maps codes <-> ids.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.db.models import Permission, UserGroup, UserGroupRight


# ── Catalog (gap #1) ─────────────────────────────────────────────────────────
def list_permissions(db: Session) -> list[Permission]:
    return list(db.execute(
        select(Permission)
        .where(Permission.is_active.is_(True))
        .order_by(Permission.category.asc(), Permission.label.asc())
    ).scalars().all())


# ── Group helpers ────────────────────────────────────────────────────────────
def _require_group(db: Session, group_id: int, tenant_id: int) -> UserGroup:
    group = db.execute(
        select(UserGroup).where(UserGroup.id == group_id, UserGroup.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if group is None:
        raise NotFoundError(f"User group '{group_id}' was not found")
    return group


def _codes_for_group(db: Session, group_id: int) -> list[str]:
    rows = db.execute(
        select(Permission.code)
        .join(UserGroupRight, UserGroupRight.permission_id == Permission.id)
        .where(UserGroupRight.group_id == group_id)
        .order_by(Permission.code.asc())
    ).scalars().all()
    return list(rows)


# ── Read / write assignments (gap #2) ────────────────────────────────────────
def get_group_rights(db: Session, group_id: int, tenant_id: int) -> list[str]:
    _require_group(db, group_id, tenant_id)
    return _codes_for_group(db, group_id)


def set_group_rights(db: Session, group_id: int, tenant_id: int, right_codes: list[str]) -> list[str]:
    _require_group(db, group_id, tenant_id)
    desired_codes = set(right_codes)

    # Resolve codes -> permission ids; reject unknown codes so the two sides stay in sync.
    id_by_code = {
        code: pid for code, pid in db.execute(
            select(Permission.code, Permission.id).where(Permission.code.in_(desired_codes))
        ).all()
    }
    unknown = sorted(desired_codes - id_by_code.keys())
    if unknown:
        raise ValidationError(
            "Unknown right code(s)", code="unknown_right_codes", details={"codes": unknown}
        )

    existing = {
        row.permission_id: row
        for row in db.execute(
            select(UserGroupRight).where(UserGroupRight.group_id == group_id)
        ).scalars()
    }
    desired_ids = set(id_by_code.values())
    for pid, row in existing.items():
        if pid not in desired_ids:
            db.delete(row)
    for pid in desired_ids - existing.keys():
        db.add(UserGroupRight(tenant_id=tenant_id, group_id=group_id, permission_id=pid))
    db.commit()
    return _codes_for_group(db, group_id)


# ── Copy group with its rights (gap #3) ──────────────────────────────────────
def copy_group(db: Session, group_id: int, tenant_id: int) -> UserGroup:
    source = _require_group(db, group_id, tenant_id)
    new_group = UserGroup(
        tenant_id=tenant_id,
        name=f"{source.name} (copy)",
        description=source.description,
        is_active=source.is_active,
    )
    db.add(new_group)
    db.flush()  # assign new_group.id
    source_pids = db.execute(
        select(UserGroupRight.permission_id).where(UserGroupRight.group_id == group_id)
    ).scalars().all()
    for pid in source_pids:
        db.add(UserGroupRight(tenant_id=tenant_id, group_id=new_group.id, permission_id=pid))
    db.commit()
    db.refresh(new_group)
    return new_group
