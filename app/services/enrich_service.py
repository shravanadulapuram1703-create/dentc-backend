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


def enrich_patient_provider(db: Session, items, tenant_id=None) -> None:  # noqa: ANN001, ARG001
    rows = list(items)
    patients = _patient_names(db, {r.patient_id for r in rows if getattr(r, "patient_id", None)})
    providers = _provider_names(db, {r.provider_id for r in rows if getattr(r, "provider_id", None)})
    for r in rows:
        r.patient_name = patients.get(r.patient_id)
        r.provider_name = providers.get(r.provider_id)


def enrich_patient_carrier(db: Session, items, tenant_id=None) -> None:  # noqa: ANN001, ARG001
    rows = list(items)
    patients = _patient_names(db, {r.patient_id for r in rows if getattr(r, "patient_id", None)})
    carriers = _carrier_names(db, {r.carrier_id for r in rows if getattr(r, "carrier_id", None)})
    for r in rows:
        r.patient_name = patients.get(r.patient_id)
        r.carrier_name = carriers.get(r.carrier_id)


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
