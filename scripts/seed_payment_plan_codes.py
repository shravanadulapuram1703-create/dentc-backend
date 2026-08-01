"""Seed the contract-billing procedure codes used by payment plans (RPP-2).

The Regular Payment Plan screen's "Billing Code" picker defaults to
``ACBIL : Periodic Contract Billing`` — the code the periodic instalment charge
posts under. ``procedure_codes`` is a global (non-tenant) table, so this runs
once per database. Idempotent: existing codes are left untouched.

    python -m scripts.seed_payment_plan_codes

The ortho billing codes (``D8*``) come from the ADA code set already loaded by
the migration, so only the account-level contract codes are seeded here.
"""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import ProcedureCode
from app.db.session import SessionLocal

# (code, description, category)
_CODES = [
    ("ACBIL", "Periodic Contract Billing", "Account"),
    ("ACBILO", "Periodic Ortho Contract Billing", "Account"),
]


def seed(db) -> int:  # noqa: ANN001
    existing = set(db.execute(select(ProcedureCode.code)).scalars().all())
    added = 0
    for code, description, category in _CODES:
        if code in existing:
            continue
        db.add(ProcedureCode(
            code=code,
            description=description,
            category=category,
            default_fee=0,
            is_active=True,
        ))
        added += 1
    db.commit()
    return added


def main() -> None:
    db = SessionLocal()
    try:
        print(f"seeded {seed(db)} contract-billing procedure codes")
    finally:
        db.close()


if __name__ == "__main__":
    main()
