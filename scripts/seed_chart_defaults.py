"""Seed the standard restorative-charting defaults per tenant (CHART-2c / CHART-3d).

Gives a fresh practice a ready-to-edit Restorative Charting Color set (the legacy
condition palette) and Material set (name + fill-pattern key) so the Setup screens
aren't empty. Idempotent — skips rows that already exist by ``(tenant_id, name)``.
Seeded rows have ``legacy_id = NULL`` (these are app defaults, not migrated).

    python -m scripts.seed_chart_defaults            # all active tenants
    python -m scripts.seed_chart_defaults --tenant 1 # one tenant
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db.models import ChartColor, ChartMaterial, Tenant
from app.db.session import SessionLocal

# (condition, stroke_color, fill_color) — legacy Restorative Charting Color Setup.
CHART_COLORS: list[tuple[str, str, str]] = [
    ("Pre-existing", "Blue", "Blue"),
    ("Completed", "Green", "DarkGreen"),
    ("Treatment Plans", "Firebrick", "Firebrick"),
    ("Defective", "Red", "Red"),
    ("Infection", "Red", "Red"),
    ("Decay/Caries", "Red", "Red"),
    ("Abrasion", "LightGreen", "HotPink"),
    ("Lesions", "SpringGreen", "Pink"),
    ("Referred Out", "Black", "Purple"),
    ("Cracked/Fractured", "Black", "Black"),
]

# (material name, fill-pattern key) — legacy Restorative Charting Materials Setup.
# Pattern keys are the bare catalog keys the renderer expects (see CHART-3e).
CHART_MATERIALS: list[tuple[str, str | None]] = [
    ("Amalgam", "hash"),
    ("Arestin", "arestin"),
    ("Ceramic", "round"),
    ("Composite", "r5hash"),
    ("Gold", "r6hash"),
    ("Gutta-percha", "crosshash"),
    ("High Noble Metal", "round"),
    ("Metal", "r2hash"),
    ("Other", "r3hash"),
    ("Plastic", "hash"),
    ("Porcelain", "r4hash"),
    ("Porcelain Fused to Gold", "r6hash"),
    ("Porcelain Fused to High Noble Metal", "r4hash"),
    ("Porcelain Fused to Metal", "r2hash"),
    ("Porcelain Fused to Titanium", "round1"),
    ("Resin", "round1"),
    ("Resin on High Noble Metal", "r3hash"),
    ("Resin on Metal", "crosshash"),
    ("Sealant", "sealant"),
    ("Stainless Steel", "r5hash"),
    ("Titanium", "hash"),
    ("Veneer", "veneer"),
]


def seed_for_tenant(db, tenant_id: int) -> tuple[int, int]:  # noqa: ANN001
    existing_colors = {
        n for (n,) in db.execute(
            select(ChartColor.name).where(ChartColor.tenant_id == tenant_id)
        ).all()
    }
    colors_added = 0
    for name, stroke, fill in CHART_COLORS:
        if name in existing_colors:
            continue
        db.add(ChartColor(tenant_id=tenant_id, name=name, stroke_color=stroke, fill_color=fill))
        colors_added += 1

    existing_materials = {
        n for (n,) in db.execute(
            select(ChartMaterial.name).where(ChartMaterial.tenant_id == tenant_id)
        ).all()
    }
    materials_added = 0
    for name, pattern in CHART_MATERIALS:
        if name in existing_materials:
            continue
        db.add(ChartMaterial(tenant_id=tenant_id, name=name, pattern=pattern))
        materials_added += 1

    db.commit()
    return colors_added, materials_added


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", type=int, default=None, help="Tenant id (default: all active)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.tenant is not None:
            tenant_ids = [args.tenant]
        else:
            tenant_ids = list(db.execute(select(Tenant.id).where(Tenant.is_active.is_(True))).scalars().all())
        for tid in tenant_ids:
            colors, materials = seed_for_tenant(db, tid)
            print(f"tenant {tid}: seeded {colors} chart colors, {materials} chart materials")
    finally:
        db.close()


if __name__ == "__main__":
    main()
