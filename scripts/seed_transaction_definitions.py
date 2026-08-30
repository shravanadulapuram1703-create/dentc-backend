"""Seed ``key2`` (type / group) on the payment and adjustment code pickers, and
widen both catalogs (CHG-10).

Why this exists
---------------
The legacy Payments picker filters payment codes by **type**, and the
Adjustments picker filters adjustment codes by **group** (Production /
Collection). Both filters are carried on ``definitions.key2``. Live, every one
of the 5 ``payment_method`` rows and all 3 ``adjustment`` rows has ``key2``
NULL across every tenant, so there is nothing to group by — which is why the
frontend hides the filters rather than rendering an "All"-only dropdown that
does nothing. The groups themselves work fine; only ``key2`` was missing.

The second half of CHG-10 is that "three adjustment codes is far short of a real
practice's expense-code list". The catalogs below are a **starting set**, not a
claim about this practice: every row is an ordinary ``definitions`` row, so the
office adds, renames and retires codes through ``/api/v1/definitions`` without a
release. What matters is that ``key2`` is populated and consistent, because that
is what the pickers group on.

What ``key2`` means
-------------------
* ``payment_method.key2`` — **who paid**: ``patient`` or ``insurance``. That is
  the split the Payments tab's Type column shows, and the one that decides
  whether a payment lands against the patient or the carrier side of the ledger.
* ``adjustment.key2`` — **production** (the adjustment changes what was
  produced: write-offs, courtesies, discounts) or **collection** (it changes
  money collected: bad debt, NSF, agency transfers). Getting a code into the
  wrong group misstates the practice's production and collection totals on the
  dashboard, so unknown codes are left NULL rather than guessed into one.

Unlike ``scripts/seed_account_definitions.py`` — which is add-only and therefore
can never fix a row that already exists — this script also **patches ``key2`` on
existing rows**, which is the whole point. It never rewrites a ``description`` a
practice has edited, and never touches a ``key2`` that is already set unless
``--overwrite`` is passed.

Usage
-----
Dry-run by default::

    python -m scripts.seed_transaction_definitions                 # report only
    python -m scripts.seed_transaction_definitions --apply
    python -m scripts.seed_transaction_definitions --apply --tenant 1
    python -m scripts.seed_transaction_definitions --apply --overwrite
"""

from __future__ import annotations

import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Definition, Tenant
from app.db.session import SessionLocal

# (key1, label, key2)
PAYMENT_METHODS: list[tuple[str, str, str]] = [
    # Patient-side tenders.
    ("cash", "Cash", "patient"),
    ("check", "Check", "patient"),
    ("credit_card", "Credit Card", "patient"),
    ("debit_card", "Debit Card", "patient"),
    ("money_order", "Money Order", "patient"),
    ("ach", "ACH / Bank Draft", "patient"),
    ("care_credit", "CareCredit / Patient Financing", "patient"),
    ("eft", "EFT", "patient"),
    # Carrier-side remittances.
    ("insurance", "Insurance", "insurance"),
    ("insurance_check", "Insurance Check", "insurance"),
    ("insurance_eft", "Insurance EFT", "insurance"),
]

ADJUSTMENTS: list[tuple[str, str, str]] = [
    # Production — changes what was produced.
    ("write_off", "Write Off", "production"),
    ("courtesy", "Courtesy", "production"),
    ("discount", "Discount", "production"),
    ("contractual", "Contractual Write Off", "production"),
    ("senior_discount", "Senior Discount", "production"),
    ("employee_discount", "Employee / Family Discount", "production"),
    ("prompt_pay_discount", "Prompt Pay Discount", "production"),
    ("charge_correction", "Charge Correction", "production"),
    # Collection — changes money collected.
    ("bad_debt", "Bad Debt", "collection"),
    ("nsf", "NSF / Returned Check", "collection"),
    ("collection_agency", "Collection Agency Transfer", "collection"),
    ("account_transfer", "Account Transfer", "collection"),
]

CATALOGS: dict[str, list[tuple[str, str, str]]] = {
    "payment_method": PAYMENT_METHODS,
    "adjustment": ADJUSTMENTS,
}


def seed_for_tenant(
    db: Session, tenant_id: int, *, apply: bool, overwrite: bool
) -> tuple[int, int]:
    """``(added, patched)`` for one tenant."""
    added = patched = 0

    for group_code, catalog in CATALOGS.items():
        rows = {
            row.key1: row
            for row in db.execute(
                select(Definition).where(
                    Definition.tenant_id == tenant_id,
                    Definition.group_code == group_code,
                )
            ).scalars()
        }
        for idx, (key1, label, key2) in enumerate(catalog):
            row = rows.get(key1)
            if row is None:
                if apply:
                    db.add(Definition(
                        tenant_id=tenant_id, group_code=group_code, key1=key1,
                        key2=key2, description=label, sort_order=idx, is_active=True,
                    ))
                added += 1
                continue
            # Existing row: fill in key2 only. The description may have been
            # edited by the practice and is not ours to overwrite.
            if row.key2 == key2:
                continue
            if row.key2 and not overwrite:
                continue
            if apply:
                row.key2 = key2
            patched += 1

    if apply:
        db.commit()
    return added, patched


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the changes")
    parser.add_argument("--overwrite", action="store_true",
                        help="also replace a key2 that is already set")
    parser.add_argument("--tenant", type=int, help="one tenant (default: all active)")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.tenant is not None:
            tenant_ids = [args.tenant]
        else:
            tenant_ids = list(
                db.execute(select(Tenant.id).where(Tenant.is_active.is_(True))).scalars().all()
            )

        total_added = total_patched = 0
        for tid in tenant_ids:
            added, patched = seed_for_tenant(
                db, tid, apply=args.apply, overwrite=args.overwrite
            )
            total_added += added
            total_patched += patched
            if added or patched:
                verb = "" if args.apply else "would "
                print(f"tenant {tid:>3}: {verb}add {added} definition(s), "
                      f"{verb}set key2 on {patched}")

        print(f"\n{len(tenant_ids)} tenant(s): "
              f"{total_added} added, {total_patched} key2 patched")
        if not args.apply:
            print("Dry run — nothing written. Re-run with --apply.")


if __name__ == "__main__":
    main()
