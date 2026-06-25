"""Seed restorative-charting reference data (REST-5 + ADA-finding codes).

Resolves:
- **REST-5** — `chart_materials` crown materials with real colors/patterns
  (zircon/metal-ceramic/emax/gold/acrylic) + condition `chart_colors`, so
  material-aware overlays render true colours instead of a default tint.
- **Capability §4.3 / task 1** — seeds the condition/finding codes into the global
  `procedure_codes` catalog (`chart_category='finding'`, `draw_as` set) so every
  charting action — including pure findings (Watch, Decay, …) — can carry a real
  `procedure_code`. Query them with `GET /procedure-codes?chart_category=finding`.

Idempotent. ``procedure_codes`` is a global catalog (no tenant); materials/colors
are tenant-scoped.

    python -m scripts.seed_restorative            # all active tenants
    python -m scripts.seed_restorative --tenant 1 # one tenant
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db.models import ChartColor, ChartMaterial, ProcedureCode, Tenant
from app.db.session import SessionLocal

# (name, color, pattern) — crown/bridge materials referenced by the FE templates.
_MATERIALS = [
    ("zircon", "#ECECEC", "solid"),
    ("metal-ceramic", "#C7CBD1", "solid"),
    ("emax", "#F1EAD8", "solid"),
    ("gold", "#E7C24B", "solid"),
    ("acrylic", "#F6E4CE", "solid"),
    ("amalgam", "#9AA0A6", "solid"),
    ("composite", "#DCEAF5", "solid"),
]

# (name, fill_color, stroke_color) — condition overlay colours.
_COLORS = [
    ("DECAY", "#D7263D", "#7A0010"),
    ("FILLING", "#2E6CC7", "#143A73"),
    ("CROWN", "#E7C24B", "#9A7B12"),
    ("MISSING", "#9AA0A6", "#5F6368"),
    ("RCT", "#7E57C2", "#4A2E86"),
    ("IMPLANT", "#455A64", "#263238"),
    ("WATCH", "#F39C12", "#9C5A00"),
    ("BRIDGE_PONTIC", "#8D6E63", "#4E342E"),
    ("SEALANT", "#26A69A", "#00695C"),
    ("RECURRENT_DECAY", "#C2185B", "#7A0E3A"),
]

# (code, description, draw_as) — chart findings with no native ADA procedure code.
_FINDING_CODES = [
    ("FND-WATCH", "Watch / monitor finding", "watch"),
    ("FND-DECAY", "Decay (caries) finding", "decay"),
    ("FND-INCIPIENT", "Incipient decay finding", "incipient_decay"),
    ("FND-RECURRENT", "Recurrent decay finding", "recurrent_decay"),
    ("FND-MOBILITY", "Mobility finding", "mobility"),
    ("FND-RECESSION", "Gingival recession finding", "recession"),
    ("FND-ABRASION", "Abrasion finding", "abrasion"),
    ("FND-ABFRACTION", "Abfraction finding", "abfraction"),
    ("FND-CHIPPED", "Chipped tooth finding", "chipped"),
    ("FND-CRACKED", "Cracked tooth finding", "cracked"),
    ("FND-FRACTURE", "Fracture finding", "fracture"),
    ("FND-CALCULUS", "Calculus finding", "calculus"),
    ("FND-INFLAMMATION", "Inflammation finding", "inflammation"),
    ("FND-DRIFT", "Drift finding", "drift"),
    ("FND-IMPACTED", "Impacted tooth finding", "impacted"),
    ("FND-OPEN-CONTACT", "Open contact finding", "open_contact"),
    ("FND-POOR-MARGIN", "Poor margin finding", "poor_margin"),
    ("FND-HYPERSENS", "Hypersensitivity finding", "hypersensitivity"),
    ("FND-ABSCESS", "Periapical abscess finding", "abscess"),
    ("FND-LESION", "Lesion finding", "lesions"),
    ("FND-NOTE", "Per-tooth note marker", "note"),
]


def _seed_global_findings(db) -> int:  # noqa: ANN001
    existing = set(db.execute(select(ProcedureCode.code)).scalars().all())
    added = 0
    for code, desc, draw_as in _FINDING_CODES:
        if code in existing:
            continue
        db.add(ProcedureCode(
            code=code, description=desc, category="Finding",
            chart_category="finding", draw_as=draw_as, default_fee=0, is_active=True,
        ))
        added += 1
    return added


def _seed_materials(db, tenant_id: int) -> int:  # noqa: ANN001
    rows = {
        m.name.lower(): m
        for m in db.execute(
            select(ChartMaterial).where(ChartMaterial.tenant_id == tenant_id)
        ).scalars()
    }
    changed = 0
    for name, color, pattern in _MATERIALS:
        existing = rows.get(name.lower())
        if existing is None:
            db.add(ChartMaterial(tenant_id=tenant_id, name=name, color=color, pattern=pattern))
            changed += 1
        elif existing.color is None:  # REST-5: backfill null colours only
            existing.color = color
            existing.pattern = existing.pattern or pattern
            changed += 1
    return changed


def _seed_colors(db, tenant_id: int) -> int:  # noqa: ANN001
    existing = {
        c.name
        for c in db.execute(
            select(ChartColor).where(ChartColor.tenant_id == tenant_id)
        ).scalars()
    }
    added = 0
    for name, fill, stroke in _COLORS:
        if name in existing:
            continue
        db.add(ChartColor(tenant_id=tenant_id, name=name, fill_color=fill,
                          stroke_color=stroke, fill_type="solid"))
        added += 1
    return added


def run(tenant_id: int | None = None) -> None:
    db = SessionLocal()
    try:
        findings = _seed_global_findings(db)
        db.commit()
        print(f"  procedure_codes findings: {findings} added")

        tenants = (
            [db.get(Tenant, tenant_id)] if tenant_id is not None
            else db.execute(select(Tenant).where(Tenant.is_active.is_(True))).scalars().all()
        )
        for tenant in tenants:
            if tenant is None:
                continue
            mats = _seed_materials(db, tenant.id)
            cols = _seed_colors(db, tenant.id)
            db.commit()
            print(f"  tenant {tenant.id}: materials {mats}, colors {cols}")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", type=int, default=None, help="seed a single tenant id")
    args = parser.parse_args()
    run(args.tenant)
