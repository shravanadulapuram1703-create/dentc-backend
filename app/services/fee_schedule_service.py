"""Fee Schedule service — restore (FEE-1) and effective-date versioning (FEE-4).

Fee schedules are **soft-deleted** (``is_active=false``); ``restore`` flips that
back. ``new_version`` clones a schedule and all its entries under a new
effective date, linking the copy to the source's lineage root.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, NotFoundError
from app.db.models import FeeSchedule, FeeScheduleEntry


def _get_in_tenant(db: Session, schedule_id: int, tenant_id: int) -> FeeSchedule:
    row = db.get(FeeSchedule, schedule_id)
    if row is None:
        raise NotFoundError(f"FeeSchedule '{schedule_id}' was not found")
    if row.tenant_id != tenant_id:
        raise ForbiddenError("Fee schedule does not belong to the authenticated tenant")
    return row


def restore(db: Session, schedule_id: int, tenant_id: int) -> FeeSchedule:
    row = _get_in_tenant(db, schedule_id, tenant_id)
    row.is_active = True
    db.commit()
    db.refresh(row)
    return row


def new_version(
    db: Session, schedule_id: int, tenant_id: int, effective_date: date, name: str | None
) -> FeeSchedule:
    source = _get_in_tenant(db, schedule_id, tenant_id)
    clone = FeeSchedule(
        tenant_id=tenant_id,
        name=name or source.name,
        fee_type=source.fee_type,
        ins_plan_id=source.ins_plan_id,
        office_id=source.office_id,
        effective_date=effective_date,
        version=(source.version or 1) + 1,
        # Keep the whole version chain pointing at the lineage root.
        parent_schedule_id=source.parent_schedule_id or source.id,
        is_active=True,
    )
    db.add(clone)
    db.flush()  # assign clone.id before copying entries

    entries = db.execute(
        select(FeeScheduleEntry).where(FeeScheduleEntry.fee_schedule_id == source.id)
    ).scalars().all()
    for e in entries:
        db.add(FeeScheduleEntry(
            fee_schedule_id=clone.id,
            procedure_code=e.procedure_code,
            amb_code=e.amb_code,
            patient_fee=e.patient_fee,
            insurance_fee=e.insurance_fee,
            effective_date=effective_date,
        ))
    db.commit()
    db.refresh(clone)
    return clone
