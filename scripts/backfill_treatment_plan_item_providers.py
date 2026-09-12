"""Backfill ``treatment_plan_items.provider_id`` (PLAN-APPT-3).

The Denticon migration (``s27b``) wrote each planned procedure's PROVIDERID into
``diagnosed_by`` as a free-text label — ``providers.legacy_id`` — and never
populated the FK column ``provider_id`` (added later, PLAN-5). So "the provider
chosen on the treatment plan" does not exist on migrated rows, and New Appt
cannot default to it.

Resolution order per item (first hit wins, NULL rows only):

1. ``diagnosed_by`` as a ``providers.id``            (app-written rows)
2. ``diagnosed_by`` as a ``providers.legacy_id``     (migrated rows)
3. the provider the rest of the plan's items use     (``--from-plan``)
4. the patient's ``preferred_provider_id``           (``--from-patient``)

Sources 3–4 are inference, so they are opt-in. Idempotent: an item that already
has a ``provider_id`` is never touched.

    python -m scripts.backfill_treatment_plan_item_providers --dry-run
    python -m scripts.backfill_treatment_plan_item_providers --tenant 1
    python -m scripts.backfill_treatment_plan_item_providers --from-plan --from-patient
"""

from __future__ import annotations

import argparse
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Patient, Provider, TreatmentPlan, TreatmentPlanItem
from app.db.session import SessionLocal


def _tenants(db: Session, only: int | None) -> list[int]:
    if only is not None:
        return [only]
    return list(db.execute(select(Patient.tenant_id).distinct().order_by(Patient.tenant_id)).scalars())


def run(db: Session, *, tenant_id: int, dry_run: bool, from_plan: bool, from_patient: bool) -> dict:
    providers = list(db.execute(select(Provider).where(Provider.tenant_id == tenant_id)).scalars())
    by_id = {p.id: p.id for p in providers}
    by_legacy: dict[str, str] = {}
    for p in sorted(providers, key=lambda x: (not x.is_active, x.id)):
        if p.legacy_id and p.legacy_id not in by_legacy:
            by_legacy[p.legacy_id] = p.id

    rows = db.execute(
        select(TreatmentPlanItem, TreatmentPlan)
        .join(TreatmentPlan, TreatmentPlan.id == TreatmentPlanItem.plan_id)
        .join(Patient, Patient.id == TreatmentPlan.patient_id)
        .where(Patient.tenant_id == tenant_id, TreatmentPlanItem.provider_id.is_(None))
    ).all()

    plan_majority: dict[str, str | None] = {}
    if from_plan:
        counts: dict[str, Counter] = {}
        for plan_id, pid in db.execute(
            select(TreatmentPlanItem.plan_id, TreatmentPlanItem.provider_id)
            .join(TreatmentPlan, TreatmentPlan.id == TreatmentPlanItem.plan_id)
            .join(Patient, Patient.id == TreatmentPlan.patient_id)
            .where(Patient.tenant_id == tenant_id, TreatmentPlanItem.provider_id.is_not(None))
        ).all():
            counts.setdefault(plan_id, Counter())[pid] += 1
        plan_majority = {k: c.most_common(1)[0][0] for k, c in counts.items()}

    stats = Counter()
    for item, plan in rows:
        label = (item.diagnosed_by or "").strip()
        pid = by_id.get(label) or by_legacy.get(label)
        source = "diagnosed_by" if pid else None
        if pid is None and from_plan:
            pid = plan_majority.get(plan.id)
            source = "plan" if pid else None
        if pid is None and from_patient:
            patient = db.get(Patient, plan.patient_id)
            pid = getattr(patient, "preferred_provider_id", None)
            source = "patient" if pid else None
        if pid is None:
            stats["unresolved"] += 1
            continue
        stats[source] += 1
        if not dry_run:
            item.provider_id = pid
    if not dry_run:
        db.commit()
    return dict(stats)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tenant", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--from-plan", action="store_true", help="fall back to the plan's majority provider")
    ap.add_argument("--from-patient", action="store_true", help="fall back to the patient's preferred provider")
    args = ap.parse_args()
    with SessionLocal() as db:
        for tid in _tenants(db, args.tenant):
            stats = run(db, tenant_id=tid, dry_run=args.dry_run,
                        from_plan=args.from_plan, from_patient=args.from_patient)
            if stats:
                print(f"tenant {tid}: {stats}{' (dry run)' if args.dry_run else ''}")


if __name__ == "__main__":
    main()
