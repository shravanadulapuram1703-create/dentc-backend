"""Fee Schedule service — restore (FEE-1), effective-date versioning (FEE-4), and
the Setup write guardrails (§3.6).

Fee schedules are **soft-deleted** (``is_active=false``); ``restore`` flips that
back. ``new_version`` clones a schedule and all its entries under a new
effective date, linking the copy to the source's lineage root.

The three ``*CRUD`` classes enforce, on every write path, the rules that keep the
three Setup maintainers from contradicting each other — an assignment must name a
payer/person, a bound schedule must be a live schedule of this tenant, Plan Pays
belongs only on a copay list, a copay list must be a payer type, and a schedule
still in use cannot be retired. Each validator fires only when its field is
present and changed, so a legacy row stays editable.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.crud.base import CRUDBase
from app.db.models import (
    FeeSchedule,
    FeeScheduleAssignment,
    FeeScheduleEntry,
    Office,
    Patient,
)
from app.services import fee_vocab


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
            # ``fee_schedule_entries`` gained ``tenant_id`` in Alembic
            # ``d4f1a9c7b3e2`` (the table had none, so ``CRUDBase`` could not scope
            # it and ``/fee-schedule-entries/{id}`` was cross-tenant writable). Now
            # that the column exists, every writer must fill it: a clone left with
            # NULL is invisible to the tenant-scoped listing, i.e. the new version
            # would appear to have no prices at all.
            tenant_id=clone.tenant_id,
            fee_schedule_id=clone.id,
            procedure_code=e.procedure_code,
            amb_code=e.amb_code,
            patient_fee=e.patient_fee,
            insurance_fee=e.insurance_fee,
            is_no_charge=e.is_no_charge,
            effective_date=effective_date,
        ))
    db.commit()
    db.refresh(clone)
    return clone


# ── Setup write guardrails (§3.6) ────────────────────────────────────────────


def _err(code: str) -> str:
    return fee_vocab.ERROR_CODES.get(code, code)


def _effective(current: object, data: dict, key: str):  # noqa: ANN001, ANN202
    """The value a write would leave on ``key``: the payload's when present, else
    the stored row's (None on a create)."""
    if key in data:
        return data[key]
    return getattr(current, key, None) if current is not None else None


def _schedule_valid(db: Session, schedule_id, tenant_id: int | None) -> bool:  # noqa: ANN001
    """A referenced schedule must exist, belong to this tenant, and be active."""
    if schedule_id is None:
        return False
    sched = db.get(FeeSchedule, schedule_id)
    return sched is not None and sched.tenant_id == tenant_id and bool(sched.is_active)


class FeeScheduleEntryCRUD(CRUDBase):
    """Refuse a negative fee and a Plan Pays amount on a non-copay list. The
    ``(schedule, code, effective_date)`` uniqueness is a DB constraint that
    surfaces as a 409 on its own; this only adds the semantic 422s."""

    def create(self, db, data, *, tenant_id=None, created_by=None):  # noqa: ANN001, ANN201
        self._guard(db, data, current=None)
        return super().create(db, data, tenant_id=tenant_id, created_by=created_by)

    def update(self, db, obj_id, data, *, tenant_id=None, updated_by=None):  # noqa: ANN001, ANN201
        current = self.get(db, obj_id, tenant_id=tenant_id)
        self._guard(db, data, current=current)
        return super().update(db, obj_id, data, tenant_id=tenant_id, updated_by=updated_by)

    @staticmethod
    def _guard(db: Session, data: dict, *, current) -> None:  # noqa: ANN001
        if "patient_fee" not in data and "insurance_fee" not in data:
            return
        sched_id = _effective(current, data, "fee_schedule_id")
        sched = db.get(FeeSchedule, sched_id) if sched_id else None
        _validate_entry_amounts(
            sched,
            data["patient_fee"] if "patient_fee" in data else None,
            data["insurance_fee"] if "insurance_fee" in data else None,
        )


def _validate_entry_amounts(sched, patient_fee, insurance_fee) -> None:  # noqa: ANN001
    """Shared by the entry CRUD guard and the bulk write ops: no negative fee, and
    Plan Pays (``insurance_fee > 0``) only on a copay list. A ``None`` value (a
    field not being written) is skipped, and the Plan Pays check is skipped when
    the schedule cannot be resolved."""
    for field, value in (("patient_fee", patient_fee), ("insurance_fee", insurance_fee)):
        if value is not None and Decimal(str(value)) < 0:
            raise ValidationError(_err("fee_entry_negative"),
                                  details={"code": "fee_entry_negative", "field": field})
    if insurance_fee is not None and Decimal(str(insurance_fee)) > 0 \
            and sched is not None and not fee_vocab.allows_plan_pays(sched.fee_type, sched.pricing_model):
        raise ValidationError(_err("insurance_fee_not_allowed"),
                              details={"code": "insurance_fee_not_allowed", "field": "insurance_fee"})


class FeeScheduleAssignmentCRUD(CRUDBase):
    """The only binding table. A row must name a payer or person (scope-only rows
    are refused), the bound schedule must be a live schedule of this tenant, and
    the target tuple must be unique. Validators fire on a *move* (create, or a
    PATCH that changes a key), never on stored state."""

    def create(self, db, data, *, tenant_id=None, created_by=None):  # noqa: ANN001, ANN201
        self._guard(db, data, tenant_id, current=None)
        return super().create(db, data, tenant_id=tenant_id, created_by=created_by)

    def update(self, db, obj_id, data, *, tenant_id=None, updated_by=None):  # noqa: ANN001, ANN201
        current = self.get(db, obj_id, tenant_id=tenant_id)
        self._guard(db, data, tenant_id, current=current)
        return super().update(db, obj_id, data, tenant_id=tenant_id, updated_by=updated_by)

    @staticmethod
    def _guard(db: Session, data: dict, tenant_id: int | None, *, current) -> None:  # noqa: ANN001
        keys = fee_vocab.ASSIGNMENT_KEYS + ("fee_schedule_id",)
        merged = {k: _effective(current, data, k) for k in keys}

        if not fee_vocab.has_assignment_target(merged):
            raise ValidationError(_err("assignment_needs_target"),
                                  details={"code": "assignment_needs_target",
                                           "keys": list(fee_vocab.ASSIGNMENT_RANK_KEYS)})

        schedule_changed = current is None or (
            "fee_schedule_id" in data and data["fee_schedule_id"] != current.fee_schedule_id
        )
        if schedule_changed and not _schedule_valid(db, merged.get("fee_schedule_id"), tenant_id):
            raise ValidationError(_err("assignment_schedule_invalid"),
                                  details={"code": "assignment_schedule_invalid",
                                           "field": "fee_schedule_id"})

        keys_changed = current is None or any(
            k in data and data[k] != getattr(current, k, None) for k in fee_vocab.ASSIGNMENT_KEYS
        )
        if keys_changed and _duplicate_assignment(
            db, merged, tenant_id, exclude_id=(current.id if current is not None else None)
        ):
            raise ConflictError(_err("assignment_duplicate_target"),
                                details={"code": "assignment_duplicate_target"})


def _duplicate_assignment(db: Session, merged: dict, tenant_id: int | None, *, exclude_id) -> bool:  # noqa: ANN001
    """True when another assignment already binds this exact key tuple. NULL-aware
    (a key left blank must match blank, not any value), tenant-scoped, self excluded."""
    conds = [FeeScheduleAssignment.tenant_id == tenant_id]
    for key in fee_vocab.ASSIGNMENT_KEYS:
        col = getattr(FeeScheduleAssignment, key)
        val = merged.get(key)
        conds.append(col.is_(None) if val in (None, "") else col == val)
    if exclude_id is not None:
        conds.append(FeeScheduleAssignment.id != exclude_id)
    return db.execute(select(FeeScheduleAssignment.id).where(and_(*conds)).limit(1)).first() is not None


class FeeScheduleCRUD(CRUDBase):
    """Canonicalise ``fee_type`` / ``pricing_model`` on write, refuse a copay list
    that is not a payer type (the Postgres CHECK's twin for SQLite), and refuse
    retiring a schedule that is still referenced by an assignment, an office
    pointer or a patient."""

    def create(self, db, data, *, tenant_id=None, created_by=None):  # noqa: ANN001, ANN201
        self._normalise(data)
        self._guard_pricing_model(data, current=None)
        return super().create(db, data, tenant_id=tenant_id, created_by=created_by)

    def update(self, db, obj_id, data, *, tenant_id=None, updated_by=None):  # noqa: ANN001, ANN201
        current = self.get(db, obj_id, tenant_id=tenant_id)
        self._normalise(data)
        self._guard_pricing_model(data, current=current)
        if "is_active" in data and data["is_active"] is False and bool(current.is_active):
            self._guard_not_referenced(db, current, tenant_id)
        return super().update(db, obj_id, data, tenant_id=tenant_id, updated_by=updated_by)

    def delete(self, db, obj_id, *, tenant_id=None) -> None:  # noqa: ANN001
        current = self.get(db, obj_id, tenant_id=tenant_id)
        self._guard_not_referenced(db, current, tenant_id)
        return super().delete(db, obj_id, tenant_id=tenant_id)

    @staticmethod
    def _normalise(data: dict) -> None:
        if "fee_type" in data and data["fee_type"] is not None:
            data["fee_type"] = fee_vocab.canonical_fee_type(data["fee_type"])
        if "pricing_model" in data and data["pricing_model"] is not None:
            data["pricing_model"] = fee_vocab.canonical_pricing_model(data["pricing_model"])

    @staticmethod
    def _guard_pricing_model(data: dict, *, current) -> None:  # noqa: ANN001
        model = _effective(current, data, "pricing_model") or fee_vocab.DEFAULT_PRICING_MODEL
        fee_type = _effective(current, data, "fee_type")
        if model == "copay" and fee_vocab.canonical_fee_type(fee_type) not in fee_vocab.COPAY_CAPABLE_FEE_TYPES:
            raise ValidationError(_err("pricing_model_requires_payer_type"),
                                  details={"code": "pricing_model_requires_payer_type",
                                           "field": "pricing_model"})

    @staticmethod
    def _guard_not_referenced(db: Session, sched: FeeSchedule, tenant_id: int | None) -> None:
        counts = _reference_counts(db, sched.id, tenant_id)
        refs = [name for name in ("assignments", "offices", "patients") if counts[name]]
        if refs:
            raise ConflictError(_err("fee_schedule_in_use"),
                                details={"code": "fee_schedule_in_use", "referenced_by": refs,
                                         "counts": counts})


def _reference_counts(db: Session, schedule_id: int, tenant_id: int | None) -> dict:
    """How many rows point at this schedule, by kind. Used by ``/usage`` and the
    retire guard so both answer from one place."""
    def _count(stmt) -> int:  # noqa: ANN001
        return int(db.execute(stmt).scalar() or 0)

    return {
        "assignments": _count(select(func.count()).select_from(FeeScheduleAssignment).where(
            FeeScheduleAssignment.fee_schedule_id == schedule_id,
            FeeScheduleAssignment.tenant_id == tenant_id)),
        "offices": _count(select(func.count()).select_from(Office).where(
            Office.tenant_id == tenant_id,
            (Office.default_fee_schedule_id == schedule_id)
            | (Office.default_ucr_fee_schedule_id == schedule_id))),
        "patients": _count(select(func.count()).select_from(Patient).where(
            Patient.tenant_id == tenant_id, Patient.fee_schedule_id == schedule_id)),
        "entries": _count(select(func.count()).select_from(FeeScheduleEntry).where(
            FeeScheduleEntry.fee_schedule_id == schedule_id)),
    }


def usage(db: Session, schedule_id: int, tenant_id: int) -> dict:
    """Where a schedule is used (Setup "Where used" panel). ``can_retire`` is false
    when any payer/office/patient still points at it."""
    sched = _get_in_tenant(db, schedule_id, tenant_id)
    counts = _reference_counts(db, sched.id, tenant_id)
    blocking = counts["assignments"] + counts["offices"] + counts["patients"]
    return {
        "fee_schedule_id": sched.id,
        "name": sched.name,
        "is_active": bool(sched.is_active),
        "counts": counts,
        "can_retire": blocking == 0,
    }


def retire(db: Session, schedule_id: int, tenant_id: int) -> FeeSchedule:
    """Soft-retire a schedule (``is_active=false``), refusing while it is still
    referenced. The counterpart of :func:`restore`; ``is_active`` is managed by
    these two routes rather than the generic update."""
    row = _get_in_tenant(db, schedule_id, tenant_id)
    FeeScheduleCRUD._guard_not_referenced(db, row, tenant_id)
    row.is_active = False
    db.commit()
    db.refresh(row)
    return row


# ── Bulk write ops (§3.5) ────────────────────────────────────────────────────

_CENTS = Decimal("0.01")


def _upsert_entry(db: Session, schedule_id: int, tenant_id: int, code: str, eff: date,
                  fields: dict) -> bool:
    """Upsert one entry keyed on (schedule, code, effective_date). Returns True if
    a new row was created."""
    row = db.execute(
        select(FeeScheduleEntry).where(
            FeeScheduleEntry.fee_schedule_id == schedule_id,
            FeeScheduleEntry.procedure_code == code,
            FeeScheduleEntry.effective_date == eff,
        )
    ).scalar_one_or_none()
    created = row is None
    if row is None:
        row = FeeScheduleEntry(tenant_id=tenant_id, fee_schedule_id=schedule_id,
                               procedure_code=code, effective_date=eff)
        db.add(row)
    for key in ("patient_fee", "insurance_fee", "amb_code", "is_no_charge"):
        if key in fields:
            setattr(row, key, fields[key])
    return created


def bulk_upsert_entries(db: Session, schedule_id: int, tenant_id: int, *,
                        effective_date: date | None, entries: list[dict]) -> dict:
    """Upsert many entries into one schedule in a single transaction. A body-level
    ``effective_date`` (or a per-entry one) is the "New Effective Date" workflow —
    a new dated set of prices *inside the same schedule*, never a clone-and-repoint,
    because the resolver already picks the entry in force on the date of service.
    Each amount is validated (no negative, Plan Pays only on a copay list)."""
    sched = _get_in_tenant(db, schedule_id, tenant_id)
    default_eff = effective_date or date.today()
    created = updated = 0
    for item in entries:
        _validate_entry_amounts(sched, item.get("patient_fee"), item.get("insurance_fee"))
        eff = item.get("effective_date") or default_eff
        if _upsert_entry(db, schedule_id, tenant_id, item["procedure_code"], eff, item):
            created += 1
        else:
            updated += 1
    db.commit()
    return {"fee_schedule_id": schedule_id, "created": created, "updated": updated,
            "effective_date": default_eff.isoformat()}


def _adjust_fee(current, mode: str, value) -> Decimal | None:  # noqa: ANN001
    if current is None:
        return None
    cur = Decimal(str(current))
    if mode == "percent":
        new = cur * (Decimal("1") + Decimal(str(value)) / Decimal("100"))
    else:  # amount
        new = cur + Decimal(str(value))
    return max(new.quantize(_CENTS, rounding=ROUND_HALF_UP), Decimal("0"))


def adjust_entries(db: Session, schedule_id: int, tenant_id: int, *, mode: str, value,
                   effective_date: date, codes: list[str] | None = None) -> dict:  # noqa: ANN001
    """Write a new dated set of prices adjusted from each code's most recent entry
    (a percentage or a flat amount), floored at 0. Like ``bulk_upsert_entries`` this
    only *adds* dated rows to the same schedule (the "New Effective Date" workflow),
    so history and the current prices are untouched until ``effective_date``."""
    if mode not in ("percent", "amount"):
        raise ValidationError("mode must be 'percent' or 'amount'",
                              details={"code": "invalid_adjust_mode", "field": "mode"})
    sched = _get_in_tenant(db, schedule_id, tenant_id)
    rows = db.execute(
        select(FeeScheduleEntry).where(FeeScheduleEntry.fee_schedule_id == schedule_id)
    ).scalars().all()
    # The most recent entry per code is the one to adjust from.
    latest: dict[str, FeeScheduleEntry] = {}
    for row in rows:
        cur = latest.get(row.procedure_code)
        if cur is None or (row.effective_date or date.min) > (cur.effective_date or date.min):
            latest[row.procedure_code] = row

    wanted = set(codes) if codes else None
    adjusted = 0
    for code, src in latest.items():
        if wanted is not None and code not in wanted:
            continue
        new_patient = _adjust_fee(src.patient_fee, mode, value)
        new_insurance = _adjust_fee(src.insurance_fee, mode, value)
        _validate_entry_amounts(sched, new_patient, new_insurance)
        _upsert_entry(db, schedule_id, tenant_id, code, effective_date, {
            "patient_fee": new_patient, "insurance_fee": new_insurance,
            "amb_code": src.amb_code, "is_no_charge": src.is_no_charge,
        })
        adjusted += 1
    db.commit()
    return {"fee_schedule_id": schedule_id, "adjusted": adjusted,
            "effective_date": effective_date.isoformat(), "mode": mode}


def reassign_patients(db: Session, source_schedule_id: int, tenant_id: int, *,
                      to_fee_schedule_id: int, patient_ids: list[int] | None = None) -> dict:
    """Move patients off ``source_schedule_id`` onto ``to_fee_schedule_id`` (the
    Change Patient Fee Schedule utility — what makes retiring a list possible). The
    target must be a live schedule of this tenant; the source need not be (it may be
    the one being retired). All patients on the source move unless ``patient_ids``
    narrows it. The request is audited as one mutation by the middleware."""
    _get_in_tenant(db, source_schedule_id, tenant_id)
    if not _schedule_valid(db, to_fee_schedule_id, tenant_id):
        raise ValidationError(_err("patient_schedule_invalid"),
                              details={"code": "patient_schedule_invalid",
                                       "field": "to_fee_schedule_id"})
    stmt = select(Patient).where(
        Patient.tenant_id == tenant_id, Patient.fee_schedule_id == source_schedule_id,
    )
    if patient_ids:
        stmt = stmt.where(Patient.id.in_(patient_ids))
    patients = db.execute(stmt).scalars().all()
    for patient in patients:
        patient.fee_schedule_id = to_fee_schedule_id
    db.commit()
    return {"from_fee_schedule_id": source_schedule_id,
            "to_fee_schedule_id": to_fee_schedule_id, "moved": len(patients)}
