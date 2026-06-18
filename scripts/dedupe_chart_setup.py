"""Collapse duplicate chart_materials / chart_colors per (tenant_id, legacy_id).

Background: like ``code_bundles``, neither table had a unique key, so the Denticon
importer's ``ON CONFLICT DO NOTHING`` was a no-op and migration re-runs produced
duplicate rows (chart_materials 4x, chart_colors 5x per legacy_id). This keeps the
lowest ``id`` in each (tenant_id, legacy_id) group and removes the rest.

``chart_materials`` is referenced by four FK columns (patient_procedures,
chart_conditions, appointment_procedures.material_id and
procedure_codes.default_material_id); those are **repointed to the survivor** before
the duplicates are deleted so nothing is orphaned. ``chart_colors`` has no inbound FKs.

Idempotent. Run before/after the uniqueness migration (the migration performs the
same SQL dedupe), or on demand / per tenant.

    python -m scripts.dedupe_chart_setup            # both tables, all tenants
    python -m scripts.dedupe_chart_setup --tenant 1 # one tenant
    python -m scripts.dedupe_chart_setup --dry-run  # report only
"""

from __future__ import annotations

import argparse

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.models import (
    AppointmentProcedure,
    ChartColor,
    ChartCondition,
    ChartMaterial,
    PatientProcedure,
    ProcedureCode,
)
from app.db.session import SessionLocal

# (model, attr) pairs whose column points at chart_materials.id and must be
# repointed to the surviving row before its duplicates are deleted.
_MATERIAL_FK_COLUMNS = (
    (PatientProcedure, "material_id"),
    (ChartCondition, "material_id"),
    (AppointmentProcedure, "material_id"),
    (ProcedureCode, "default_material_id"),
)


def _duplicate_groups(db: Session, model, tenant_id: int | None):
    """Yield (keep_id, [dupe_ids]) for each (tenant_id, legacy_id) group with >1 row."""
    survivors = select(model.tenant_id, model.legacy_id, func.min(model.id)).where(
        model.legacy_id.is_not(None)
    )
    if tenant_id is not None:
        survivors = survivors.where(model.tenant_id == tenant_id)
    survivors = survivors.group_by(model.tenant_id, model.legacy_id).having(func.count() > 1)

    for tid, legacy_id, keep_id in db.execute(survivors).all():
        dupe_ids = db.execute(
            select(model.id).where(
                model.tenant_id == tid,
                model.legacy_id == legacy_id,
                model.id != keep_id,
            )
        ).scalars().all()
        if dupe_ids:
            yield keep_id, dupe_ids


def dedupe_chart_materials(db: Session, tenant_id: int | None = None, *, dry_run: bool = False) -> int:
    removed = 0
    for keep_id, dupe_ids in _duplicate_groups(db, ChartMaterial, tenant_id):
        removed += len(dupe_ids)
        if dry_run:
            continue
        for fk_model, attr in _MATERIAL_FK_COLUMNS:
            col = getattr(fk_model, attr)
            db.execute(update(fk_model).where(col.in_(dupe_ids)).values({attr: keep_id}))
        db.execute(ChartMaterial.__table__.delete().where(ChartMaterial.id.in_(dupe_ids)))
    if not dry_run:
        db.commit()
    return removed


def dedupe_chart_colors(db: Session, tenant_id: int | None = None, *, dry_run: bool = False) -> int:
    removed = 0
    for _keep_id, dupe_ids in _duplicate_groups(db, ChartColor, tenant_id):
        removed += len(dupe_ids)
        if dry_run:
            continue
        db.execute(ChartColor.__table__.delete().where(ChartColor.id.in_(dupe_ids)))
    if not dry_run:
        db.commit()
    return removed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", type=int, default=None, help="Tenant id (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Report counts without deleting")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        verb = "would remove" if args.dry_run else "removed"
        mats = dedupe_chart_materials(db, args.tenant, dry_run=args.dry_run)
        cols = dedupe_chart_colors(db, args.tenant, dry_run=args.dry_run)
        print(f"dedupe_chart_setup: {verb} {mats} chart_material(s), {cols} chart_color(s)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
