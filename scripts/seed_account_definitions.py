"""Seed canonical ``definitions`` group_codes for Account Information dropdowns.

Resolves backend dev-report gap #9: the FE binds each dropdown to a `group_code`,
but the values were undocumented. This script defines them authoritatively and
seeds them per tenant. Idempotent — skips rows that already exist
``(tenant_id, group_code, key1)``.

    python -m scripts.seed_account_definitions            # all active tenants
    python -m scripts.seed_account_definitions --tenant 1 # one tenant

`DefinitionRead.key1` = option value, `description` = option label (per the FE
contract). `business_industry` is intentionally a free-text field, not seeded.
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db.models import Definition, Tenant
from app.db.session import SessionLocal

_STATES = [
    ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"), ("AR", "Arkansas"),
    ("CA", "California"), ("CO", "Colorado"), ("CT", "Connecticut"), ("DE", "Delaware"),
    ("DC", "District of Columbia"), ("FL", "Florida"), ("GA", "Georgia"), ("HI", "Hawaii"),
    ("ID", "Idaho"), ("IL", "Illinois"), ("IN", "Indiana"), ("IA", "Iowa"), ("KS", "Kansas"),
    ("KY", "Kentucky"), ("LA", "Louisiana"), ("ME", "Maine"), ("MD", "Maryland"),
    ("MA", "Massachusetts"), ("MI", "Michigan"), ("MN", "Minnesota"), ("MS", "Mississippi"),
    ("MO", "Missouri"), ("MT", "Montana"), ("NE", "Nebraska"), ("NV", "Nevada"),
    ("NH", "New Hampshire"), ("NJ", "New Jersey"), ("NM", "New Mexico"), ("NY", "New York"),
    ("NC", "North Carolina"), ("ND", "North Dakota"), ("OH", "Ohio"), ("OK", "Oklahoma"),
    ("OR", "Oregon"), ("PA", "Pennsylvania"), ("RI", "Rhode Island"), ("SC", "South Carolina"),
    ("SD", "South Dakota"), ("TN", "Tennessee"), ("TX", "Texas"), ("UT", "Utah"),
    ("VT", "Vermont"), ("VA", "Virginia"), ("WA", "Washington"), ("WV", "West Virginia"),
    ("WI", "Wisconsin"), ("WY", "Wyoming"),
]

# group_code -> [(key1 value, description label), ...]
GROUPS: dict[str, list[tuple[str, str]]] = {
    "state": _STATES,
    "country": [("US", "United States"), ("CA", "Canada")],
    "culture": [("en-US", "English (US)"), ("es-US", "Spanish (US)"), ("fr-CA", "French (Canada)")],
    "theme": [("blue", "Blue (Default)"), ("green", "Green"), ("teal", "Teal"), ("dark", "Dark")],
    "charting_option": [("sub_menu", "Sub Menu (Default)"), ("tool_bar", "Tool Bar")],
    "charting_tab": [("pre_existing", "Pre-existing"), ("treatment_plan", "Treatment Plan"), ("completed", "Completed")],
    "edi_vendor": [("EHG", "EHG"), ("DXC", "DentalXChange"), ("TESIA", "Tesia")],
    "holiday_status": [("CLOSED", "Closed"), ("OPEN", "Open"), ("HALF_DAY", "Half Day")],
    "holiday_type": [("FEDERAL", "Federal"), ("CUSTOM", "Custom")],
    "business_type": [
        ("sole_proprietor", "Sole Proprietor"), ("partnership", "Partnership"),
        ("llc", "LLC"), ("corporation", "Corporation"), ("non_profit", "Non-Profit"),
    ],
    "company_status": [("private", "Private"), ("public", "Public")],
    "stock_exchange": [("NYSE", "NYSE"), ("NASDAQ", "NASDAQ"), ("AMEX", "AMEX"), ("OTC", "OTC")],
    "required_field_mode": [
        ("any", "Any"), ("required", "Required"), ("not_required", "Not Required"),
        ("pat_reg_only", "Pat Reg Only"),
    ],
    "ortho_claim_fee_mode": [
        ("total_ortho", "Total Ortho Amount"), ("monthly", "Monthly Amount"), ("banding", "Banding Fee"),
    ],
    "default_treatment_plan_filter": [
        ("show_all", "Show All"), ("active", "Active"), ("proposed", "Proposed"),
    ],
    "pronoun_field_visible": [("YES", "Yes"), ("NO", "No")],
    "comm_number_type": [("toll_free", "Toll-Free"), ("local_text", "Local Text")],
    "payment_method": [
        ("cash", "Cash"), ("check", "Check"), ("credit_card", "Credit Card"),
        ("eft", "EFT"), ("insurance", "Insurance"),
    ],
    "adjustment": [("write_off", "Write Off"), ("courtesy", "Courtesy"), ("discount", "Discount")],
    "claim_status": [
        ("draft", "Draft"), ("submitted", "Submitted"), ("paid", "Paid"),
        ("denied", "Denied"), ("closed", "Closed"),
    ],
}


def seed_for_tenant(db, tenant_id: int) -> int:  # noqa: ANN001
    existing = {
        (g, k)
        for g, k in db.execute(
            select(Definition.group_code, Definition.key1).where(Definition.tenant_id == tenant_id)
        ).all()
    }
    added = 0
    for group_code, options in GROUPS.items():
        for key1, label in options:
            if (group_code, key1) in existing:
                continue
            db.add(Definition(
                tenant_id=tenant_id, group_code=group_code, key1=key1,
                description=label, is_active=True,
            ))
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
            print(f"tenant {tid}: seeded {n} definitions ({len(GROUPS)} groups)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
