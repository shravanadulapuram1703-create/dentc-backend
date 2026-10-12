"""Office delete / reactivate (OFF-QA-15…17).

``DELETE /offices/{id}`` used to be the generic soft delete, ``is_active=false``
and 204, whatever still pointed at the office. That made it the same as
Status → Inactive, kept no record of who deleted the office, and offered no way
to remove an office created by mistake. This module is the one place that
decides what an office delete means:

* ``delete_impact``: the counts the Delete dialog shows, in one call.
* ``soft_delete``: 409 ``office_in_use`` while there are upcoming appointments
  or users who would be left with no active office, unless ``force``. Either way
  the office's active operatories are deactivated, and their ids are kept on
  the office row so a reactivate restores exactly those chairs (and not ones an
  admin had already retired). ``deleted_at``/``deleted_by`` are stamped.
* ``hard_delete``: removes the office and the configuration it owns. Allowed
  only when no other row in the database references it; the check walks every
  foreign key into ``offices`` (and into the operatories it would remove), so a
  newly added table cannot be forgotten.
* ``on_reactivate``: run by ``OfficeCRUD.update`` when ``is_active`` goes back
  to true. Clears the stamp and restores the remembered operatories.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Table, delete, distinct, exists, func, or_, select, update
from sqlalchemy.orm import Session

from app.core import audit_context
from app.core.datetimes import office_today
from app.core.exceptions import ConflictError, ForbiddenError
from app.db.base import Base
from app.db.models import Appointment, Office, Operatory, Patient, Provider, User, UserOffice
from app.db.models.office_assignment import ProviderOffice

#: Tables that are *the office's own configuration*. A hard delete removes their
#: rows with the office. Every other foreign key into ``offices`` blocks it.
OWNED_TABLES = (
    "office_statement_settings", "office_integrations", "office_advanced_settings",
    "office_smart_assist_items", "office_smart_assist", "office_schedule_days",
    "account_holidays", "office_phone_assignments", "office_procedure_codes",
    "office_note_macros", "office_code_bundles", "office_letter_templates",
    "office_prescription_library", "office_production_types", "appointnow_reasons",
    "operatories",
)
#: References that are a per-user *preference*, not data about the office. They
#: are cleared on a hard delete instead of blocking it.
CLEARED_REFERENCES = (("users", "current_office_id"),)
HARD_DELETE_ROLES = frozenset({"admin", "owner", "super_admin"})


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── impact (OFF-QA-15.1) ─────────────────────────────────────────────────────
def delete_impact(db: Session, office: Office) -> dict:
    today = office_today(office.timezone)
    future_appointments = db.execute(
        select(func.count()).select_from(Appointment).where(
            Appointment.office_id == office.id, Appointment.date >= today,
            Appointment.is_archived.is_(False), Appointment.is_cancelled.is_(False),
        )
    ).scalar_one()
    home_patients = db.execute(
        select(func.count()).select_from(Patient).where(
            Patient.home_office_id == office.id, Patient.is_active.is_(True))
    ).scalar_one()
    assigned = select(UserOffice.user_id).join(User, User.id == UserOffice.user_id).where(
        UserOffice.office_id == office.id, User.is_active.is_(True))
    assigned_user_ids = set(db.execute(assigned).scalars().all())
    # A user keeps working if they hold another *active* office.
    with_other = set(db.execute(
        select(distinct(UserOffice.user_id))
        .join(Office, Office.id == UserOffice.office_id)
        .where(UserOffice.user_id.in_(assigned_user_ids), UserOffice.office_id != office.id,
               Office.is_active.is_(True))
    ).scalars().all()) if assigned_user_ids else set()
    stranded = sorted(assigned_user_ids - with_other)
    providers = db.execute(
        select(func.count(distinct(Provider.id))).where(
            Provider.is_active.is_(True),
            or_(Provider.office_id == office.id,
                Provider.id.in_(select(ProviderOffice.provider_id).where(ProviderOffice.office_id == office.id))),
        )
    ).scalar_one()
    operatories = db.execute(
        select(func.count()).select_from(Operatory).where(
            Operatory.office_id == office.id, Operatory.is_active.is_(True))
    ).scalar_one()
    return {
        "office_id": office.id,
        "is_active": office.is_active,
        "as_of": today.isoformat(),
        "future_appointments": future_appointments,
        "home_patients": home_patients,
        "assigned_users": len(assigned_user_ids),
        "users_with_no_other_office": len(stranded),
        "stranded_user_ids": stranded,
        "providers": providers,
        "operatories": operatories,
        "blocking": [k for k, v in (("future_appointments", future_appointments),
                                    ("users_with_no_other_office", len(stranded))) if v],
    }


# ── soft delete (OFF-QA-15.2 / 16) ───────────────────────────────────────────
def soft_delete(db: Session, office: Office, user_id: int | None, *, force: bool) -> dict:
    impact = delete_impact(db, office)
    if impact["blocking"] and not force:
        raise ConflictError(
            "This office still has upcoming appointments or users who would have no office",
            code="office_in_use",
            details={"code": "office_in_use", "impact": impact, "override_param": "force"},
        )
    op_ids = list(db.execute(
        select(Operatory.id).where(Operatory.office_id == office.id, Operatory.is_active.is_(True))
    ).scalars().all())
    if op_ids:
        db.execute(update(Operatory).where(Operatory.id.in_(op_ids)).values(is_active=False))
    was_active = office.is_active
    office.is_active = False
    office.deleted_at = _now()
    office.deleted_by = user_id
    # Accumulate across a delete of an already-inactive office, never lose ids.
    office.deleted_operatory_ids = sorted(set(office.deleted_operatory_ids or []) | set(op_ids))
    office.updated_at = _now()
    audit_context.record(
        resource_id=str(office.id), row_id=office.id,
        before={"is_active": was_active},
        after={"is_active": False, "deleted": True, "forced": bool(force and impact["blocking"]),
               "deactivated_operatory_ids": op_ids, "impact": {k: v for k, v in impact.items()
                                                               if k != "stranded_user_ids"}},
    )
    db.commit()
    return impact


def on_reactivate(db: Session, office: Office) -> list[str]:
    """``is_active`` false -> true: clear the delete stamp and bring back the
    chairs the delete switched off. Returns the restored operatory ids."""
    ids = list(office.deleted_operatory_ids or [])
    if ids:
        db.execute(update(Operatory).where(Operatory.id.in_(ids), Operatory.office_id == office.id)
                   .values(is_active=True))
    office.deleted_at = None
    office.deleted_by = None
    office.deleted_operatory_ids = None
    return ids


# ── hard delete (OFF-QA-17) ──────────────────────────────────────────────────
def _fk_columns_into(table_name: str) -> list[tuple[Table, str]]:
    out = []
    for t in Base.metadata.tables.values():
        for fk in t.foreign_keys:
            if fk.column.table.name == table_name:
                out.append((t, fk.parent.name))
    return out


def hard_delete_references(db: Session, office: Office) -> list[dict]:
    """Every row outside the office's own configuration that references it
    (or one of the operatories a hard delete would remove)."""
    refs: list[dict] = []
    for table, col in _fk_columns_into("offices"):
        if table.name in OWNED_TABLES or (table.name, col) in CLEARED_REFERENCES or table.name == "offices":
            continue
        if db.execute(select(exists().where(table.c[col] == office.id))).scalar():
            refs.append({"table": table.name, "column": col})
    op_ids = select(Operatory.id).where(Operatory.office_id == office.id).scalar_subquery()
    for table, col in _fk_columns_into("operatories"):
        if table.name in OWNED_TABLES:
            continue
        if db.execute(select(exists().where(table.c[col].in_(op_ids)))).scalar():
            refs.append({"table": table.name, "column": col, "via": "operatories"})
    return refs


def hard_delete(db: Session, office: Office, user: User) -> None:
    if (user.role or "").lower() not in HARD_DELETE_ROLES:
        raise ForbiddenError("Only an administrator can permanently delete an office",
                             code="hard_delete_forbidden")
    refs = hard_delete_references(db, office)
    if refs:
        raise ConflictError(
            "This office is referenced by other records and can only be deactivated",
            code="office_in_use",
            details={"code": "office_in_use", "hard": True, "references": refs,
                     "impact": delete_impact(db, office)},
        )
    tables = dict(Base.metadata.tables)
    for table_name, col in CLEARED_REFERENCES:
        db.execute(update(tables[table_name]).where(tables[table_name].c[col] == office.id)
                   .values({col: None}))
    # Children first: smart-assist items before their settings row, etc. The
    # tuple is already ordered that way, and nothing outside it points in.
    for name in OWNED_TABLES:
        db.execute(delete(tables[name]).where(tables[name].c.office_id == office.id))
    audit_context.record(resource_id=str(office.id), row_id=office.id,
                         before={"name": office.name, "office_code": office.office_code},
                         after={"hard_deleted": True})
    db.delete(office)
    db.commit()
