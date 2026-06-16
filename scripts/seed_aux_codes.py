"""Seed the standard CMS Place-of-Service list per tenant (AUX-3).

Gives each practice a ready-to-edit POS catalog (Tax ID / office_id left blank to
fill in). Idempotent — skips rows that already exist ``(tenant_id, code)``.

    python -m scripts.seed_aux_codes            # all active tenants
    python -m scripts.seed_aux_codes --tenant 1 # one tenant

ICD codes (AUX-4) are a large external set and are NOT seeded here — load them from
the practice's ICD source via the CRUD/bulk endpoints.
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db.models import PlaceOfServiceCode, Tenant
from app.db.session import SessionLocal

# (code, type/name) — CMS Place-of-Service. type == name for the standard list.
POS_CODES: list[tuple[str, str]] = [
    ("02", "Telehealth"),
    ("03", "School"),
    ("04", "Homeless Shelter"),
    ("11", "Office"),
    ("12", "Home"),
    ("13", "Assisted Living Facility"),
    ("20", "Urgent Care Facility"),
    ("21", "Inpatient Hospital"),
    ("22", "On Campus-Outpatient Hospital"),
    ("23", "Emergency Room - Hospital"),
    ("24", "Ambulatory Surgical Center"),
    ("31", "Skilled Nursing Facility"),
    ("32", "Nursing Facility"),
    ("49", "Independent Clinic"),
    ("50", "Federally Qualified Health Center"),
    ("51", "Inpatient Psychiatric Facility"),
    ("71", "Public Health Clinic"),
    ("81", "Independent Laboratory"),
    ("99", "Other Place of Service"),
]


def seed_for_tenant(db, tenant_id: int) -> int:  # noqa: ANN001
    existing = {
        code for (code,) in db.execute(
            select(PlaceOfServiceCode.code).where(PlaceOfServiceCode.tenant_id == tenant_id)
        ).all()
    }
    added = 0
    for code, name in POS_CODES:
        if code in existing:
            continue
        db.add(PlaceOfServiceCode(tenant_id=tenant_id, code=code, type=name, name=name, is_active=True))
        added += 1
    db.commit()
    return added


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
            n = seed_for_tenant(db, tid)
            print(f"tenant {tid}: seeded {n} place-of-service codes")
    finally:
        db.close()


if __name__ == "__main__":
    main()
