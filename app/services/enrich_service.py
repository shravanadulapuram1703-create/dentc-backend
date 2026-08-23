"""Shared read-enrich hooks that denormalise names/totals onto generated read
models (Reports dev-report G7/G9). Wired via ``CrudConfig.read_enrich`` so the
money/report list endpoints stop returning id-only rows and the frontend stops
its per-row `GET /patients/{id}` fan-out.

Every resolver batches by distinct id, so cost is independent of page size.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    InsuranceCarrier,
    Office,
    Patient,
    Provider,
    TreatmentPlanItem,
)


def _patient_names(db: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    out: dict[int, str] = {}
    for p in db.execute(select(Patient).where(Patient.id.in_(ids))).scalars():
        name = ", ".join(x for x in (p.last_name, p.first_name) if x)
        out[p.id] = name or p.chart_no or f"Patient {p.id}"
    return out


def _provider_names(db: Session, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    return {p.id: p.name for p in db.execute(select(Provider).where(Provider.id.in_(ids))).scalars()}


def _carrier_names(db: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return {c.id: c.name for c in db.execute(select(InsuranceCarrier).where(InsuranceCarrier.id.in_(ids))).scalars()}


def enrich_patient_office(db: Session, items, tenant_id=None) -> None:  # noqa: ANN001, ARG001
    """LEG-16: resolve ``home_office_id`` → office name + code on ``PatientRead`` so
    screens display the office by name without a separate ``GET /offices`` fan-out.

    PE-4: also resolves ``created_by`` / ``updated_by`` → display names, mirroring
    ``UserRead``, so the Edit dialog header's Modified-By field needs no extra
    ``GET /users/{id}``."""
    from app.services.user_admin_service import resolve_user_names

    rows = list(items)
    ids = {r.home_office_id for r in rows if getattr(r, "home_office_id", None)}
    offices = {o.id: o for o in db.execute(select(Office).where(Office.id.in_(ids))).scalars()} if ids else {}
    actor_ids = {r.created_by for r in rows if getattr(r, "created_by", None) is not None}
    actor_ids |= {r.updated_by for r in rows if getattr(r, "updated_by", None) is not None}
    names = resolve_user_names(db, actor_ids)
    for r in rows:
        office = offices.get(r.home_office_id)
        r.home_office_name = office.name if office else None
        r.home_office_code = (office.short_id or office.office_code) if office else None
        r.created_by_name = names.get(r.created_by) if r.created_by is not None else None
        r.updated_by_name = names.get(r.updated_by) if r.updated_by is not None else None


def enrich_patient_provider(db: Session, items, tenant_id=None) -> None:  # noqa: ANN001, ARG001
    rows = list(items)
    patients = _patient_names(db, {r.patient_id for r in rows if getattr(r, "patient_id", None)})
    providers = _provider_names(db, {r.provider_id for r in rows if getattr(r, "provider_id", None)})
    for r in rows:
        r.patient_name = patients.get(r.patient_id)
        r.provider_name = providers.get(r.provider_id)


def enrich_patient_procedure(db: Session, items, tenant_id=None) -> None:  # noqa: ANN001, ARG001
    """CHG-5: patient/provider names **plus** the per-procedure applied totals the
    "Procedures To Post" grid needs (Pat Paid / Pat Adj / Rem Amt). Batched, so a
    page costs a fixed handful of statements."""
    from app.services.procedure_totals_service import ZERO, applied_totals, patient_share

    rows = list(items)
    enrich_patient_provider(db, rows)
    totals = applied_totals(db, [r.id for r in rows])
    for r in rows:
        applied = totals.get(r.id, {})
        r.paid_to_date = applied.get("paid_to_date", ZERO)
        r.insurance_paid_to_date = applied.get("insurance_paid_to_date", ZERO)
        r.adjusted_to_date = applied.get("adjusted_to_date", ZERO)
        # AL-15: patient_estimate is 0.00 on essentially every migrated row, so a
        # bare subtraction reported "nothing outstanding" on unpaid charges.
        r.remaining_amount = patient_share(r) - r.paid_to_date - r.adjusted_to_date
        r.outstanding_amount = (
            Decimal(r.fee or 0) - r.paid_to_date - r.insurance_paid_to_date - r.adjusted_to_date
        )


def enrich_patient_carrier(db: Session, items, tenant_id=None) -> None:  # noqa: ANN001, ARG001
    rows = list(items)
    patients = _patient_names(db, {r.patient_id for r in rows if getattr(r, "patient_id", None)})
    carriers = _carrier_names(db, {r.carrier_id for r in rows if getattr(r, "carrier_id", None)})
    for r in rows:
        r.patient_name = patients.get(r.patient_id)
        r.carrier_name = carriers.get(r.carrier_id)


def _actor_names(db: Session, rows, attrs: tuple[str, ...]) -> dict[int, str]:  # noqa: ANN001
    from app.services.user_admin_service import resolve_user_names

    ids: set[int] = set()
    for r in rows:
        for attr in attrs:
            value = getattr(r, attr, None)
            if value is not None:
                ids.add(value)
    return resolve_user_names(db, ids)


def enrich_ortho_plan(db: Session, items, tenant_id=None) -> None:  # noqa: ANN001, ARG001
    """OPP-2/11 + PP-7: resolve the contract header's actor, provider and office.

    ``created_by`` is legacy free text (a migrated user label) and cannot be
    resolved — ``created_by_id`` is the FK the API stamps going forward, so the
    name falls back to the legacy string when only that is present.
    """
    rows = list(items)
    names = _actor_names(db, rows, ("created_by_id", "updated_by"))
    providers = _provider_names(
        db, {r.pref_provider_id for r in rows if getattr(r, "pref_provider_id", None)}
    )
    office_ids = {r.created_office_id for r in rows if getattr(r, "created_office_id", None)}
    offices = {
        o.id: o for o in db.execute(select(Office).where(Office.id.in_(office_ids))).scalars()
    } if office_ids else {}
    for r in rows:
        r.created_by_name = (
            names.get(r.created_by_id) if r.created_by_id is not None else r.created_by
        )
        r.updated_by_name = names.get(r.updated_by) if r.updated_by is not None else None
        r.pref_provider_name = providers.get(r.pref_provider_id)
        office = offices.get(r.created_office_id)
        r.created_office_name = office.name if office else None
        r.created_office_code = (office.short_id or office.office_code) if office else None


def enrich_payment_plan(db: Session, items, tenant_id=None) -> None:  # noqa: ANN001, ARG001
    """PP-7: "Created By" / "Modified By" on a regular contract (see above)."""
    rows = list(items)
    names = _actor_names(db, rows, ("created_by_id", "updated_by"))
    for r in rows:
        r.created_by_name = (
            names.get(r.created_by_id) if r.created_by_id is not None else r.created_by
        )
        r.updated_by_name = names.get(r.updated_by) if r.updated_by is not None else None


def enrich_treatment_plan(db: Session, items, tenant_id=None) -> None:  # noqa: ANN001, ARG001
    """G9: patient name + rolled-up plan totals (no per-plan item N+1)."""
    rows = list(items)
    patients = _patient_names(db, {r.patient_id for r in rows if getattr(r, "patient_id", None)})
    plan_ids = [r.id for r in rows]
    totals: dict[str, tuple] = {}
    if plan_ids:
        for plan_id, cnt, fee, ins in db.execute(
            select(
                TreatmentPlanItem.plan_id,
                func.count(),
                func.coalesce(func.sum(TreatmentPlanItem.fee), 0),
                func.coalesce(func.sum(TreatmentPlanItem.insurance_estimate), 0),
            )
            .where(TreatmentPlanItem.plan_id.in_(plan_ids), TreatmentPlanItem.is_archived.is_(False))
            .group_by(TreatmentPlanItem.plan_id)
        ).all():
            totals[plan_id] = (cnt, Decimal(fee), Decimal(ins))
    for r in rows:
        r.patient_name = patients.get(r.patient_id)
        cnt, fee, ins = totals.get(r.id, (0, Decimal("0"), Decimal("0")))
        r.item_count = cnt
        r.total_fee = fee
        r.est_insurance = ins
        r.est_patient = fee - ins
