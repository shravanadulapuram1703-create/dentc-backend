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
    # Insurance Setup -> Plans/Coverage (dev-report INS-10): label the opaque codes.
    # ``insurance_plans.coverage_type`` (Denticon COVERAGETYPE, single char).
    "coverage_type": [
        ("I", "Indemnity"), ("P", "PPO"), ("H", "HMO"), ("C", "Capitation"),
        ("M", "Medicaid"), ("S", "Self Pay"), ("O", "Other"),
    ],
    # ``insurance_coverage_rules.category`` (Denticon INSCATEGORYID → ADA group;
    # see denticon_migration/migration_mapping.md). key1 = the raw stored code.
    "coverage_category": [
        ("0", "Other"), ("1", "Diagnostic"), ("2", "Preventive"), ("3", "Restorative"),
        ("4", "Endodontics"), ("5", "Periodontics"), ("6", "Prosthodontics (Removable)"),
        ("7", "Maxillofacial Prosthetics"), ("8", "Implant Services"),
        ("9", "Prosthodontics (Fixed)"), ("10", "Oral & Maxillofacial Surgery"),
        ("11", "Orthodontics"), ("12", "Adjunctive General Services"),
    ],
    # Security -> Users module (gaps #2/#5)
    "user_role": [
        ("admin", "Administrator"), ("provider", "Provider"), ("front_desk", "Front Desk"),
        ("staff", "Staff"), ("super_admin", "Super Admin"),
    ],
    "patient_access_level": [
        ("full", "Full Access"), ("limited", "Limited"), ("read_only", "Read Only"),
        ("none", "No Access"),
    ],
    "overtime_method": [
        ("none", "None"), ("weekly_40", "Weekly (40h)"), ("daily_8", "Daily (8h)"),
        ("california", "California"),
    ],
    # Scheduler module (gaps #4/#10) — appt_status carries a color (3rd element).
    "appt_status": [
        ("scheduled", "Scheduled", "#6B7280"),
        ("confirmed", "Confirmed", "#10B981"),
        ("in_reception", "In Reception", "#3B82F6"),
        ("in_chair", "In Chair", "#8B5CF6"),
        ("checked_out", "Checked Out", "#0EA5E9"),
        ("completed", "Completed", "#22C55E"),
        ("cancelled", "Cancelled", "#EF4444"),
        ("no_show", "No Show", "#F59E0B"),
        ("missed", "Missed", "#DC2626"),
        ("rescheduled", "Rescheduled", "#A855F7"),
    ],
    "appt_type": [
        ("recall", "Recall"), ("new_patient", "New Patient"), ("emergency", "Emergency"),
        ("consultation", "Consultation"), ("treatment", "Treatment"), ("hygiene", "Hygiene"),
        ("follow_up", "Follow Up"),
    ],
    "procedure_type": [
        ("cleaning", "Cleaning"), ("exam", "Exam"), ("filling", "Filling"),
        ("crown", "Crown"), ("extraction", "Extraction"), ("root_canal", "Root Canal"),
        ("ortho", "Ortho"),
    ],
    # Patients module dropdowns (replaces the legacy /patients/metadata surface)
    "gender": [("M", "Male"), ("F", "Female"), ("O", "Other"), ("U", "Unknown")],
    "title": [("mr", "Mr."), ("mrs", "Mrs."), ("ms", "Ms."), ("dr", "Dr."), ("mx", "Mx.")],
    "marital_status": [
        ("single", "Single"), ("married", "Married"), ("divorced", "Divorced"),
        ("widowed", "Widowed"), ("separated", "Separated"),
    ],
    "referral_type": [
        ("patient", "Existing Patient"), ("doctor", "Doctor"), ("insurance", "Insurance"),
        ("online", "Online"), ("walk_in", "Walk-in"), ("other", "Other"),
    ],
    # Referral Setup -> Referral Sources (referral dev-report): the referrals
    # ``referral_type`` column is a direction code, not the above lead-source list.
    "referral_direction": [("0", "Referred By"), ("1", "Referred To")],
    # ── Auxiliary code tables (Setup -> Procedure Codes), AUX-1 / AUX-2 ──────────
    # Modifier Codes — standard CPT/HCPCS modifiers (key1 = code, description = label).
    "MODIFIER": [
        ("21", "Prolonged Evaluation and Management Services"),
        ("22", "Increased Procedural Services"),
        ("23", "Unusual Anesthesia"),
        ("24", "Unrelated E/M Service During a Postoperative Period"),
        ("25", "Significant, Separately Identifiable E/M Service"),
        ("26", "Professional Component"),
        ("27", "Multiple Outpatient Hospital E/M Encounters"),
        ("32", "Mandated Services"),
        ("50", "Bilateral Procedure"),
        ("51", "Multiple Procedures"),
        ("52", "Reduced Services"),
        ("53", "Discontinued Procedure"),
        ("54", "Surgical Care Only"),
        ("55", "Postoperative Management Only"),
        ("56", "Preoperative Management Only"),
        ("57", "Decision for Surgery"),
        ("58", "Staged or Related Procedure"),
        ("59", "Distinct Procedural Service"),
        ("62", "Two Surgeons"),
        ("76", "Repeat Procedure by Same Physician"),
        ("77", "Repeat Procedure by Another Physician"),
        ("78", "Unplanned Return to the Operating Room"),
        ("79", "Unrelated Procedure During the Postoperative Period"),
        ("80", "Assistant Surgeon"),
        ("90", "Reference (Outside) Laboratory"),
        ("91", "Repeat Clinical Diagnostic Laboratory Test"),
        ("99", "Multiple Modifiers"),
    ],
    # Type of Service — standard CMS TOS codes.
    "TYPEOFSERVICE": [
        ("01", "Medical Care"),
        ("02", "Surgery"),
        ("03", "Consultation"),
        ("04", "Diagnostic Radiology"),
        ("05", "Diagnostic Laboratory"),
        ("06", "Therapeutic Radiology"),
        ("07", "Anesthesia"),
        ("08", "Assistant at Surgery"),
        ("09", "Other Medical Items or Services"),
        ("10", "Whole Blood"),
        ("11", "Used Durable Medical Equipment (DME)"),
        ("12", "DME Purchase"),
        ("13", "Ambulatory Surgical Center (ASC) Facility"),
        ("99", "Other"),
    ],
    "pronoun": [("he_him", "He/Him"), ("she_her", "She/Her"), ("they_them", "They/Them")],
    "contact_pref": [
        ("phone", "Phone"), ("email", "Email"), ("sms", "Text/SMS"), ("mail", "Mail"),
    ],
    "resp_party_rel": [
        ("self", "Self"), ("spouse", "Spouse"), ("parent", "Parent"),
        ("guardian", "Guardian"), ("child", "Child"), ("other", "Other"),
        # PO-9: legacy single-letter subscriber-relationship codes on
        # patient_insurance.relationship (e.g. "S" -> "Self") so they expand.
        ("S", "Self"), ("SP", "Spouse"), ("P", "Parent"), ("G", "Guardian"),
        ("C", "Child"), ("D", "Dependent"), ("O", "Other"),
    ],
    # PE-2: the 8 legacy patient-type codes (multi-select on patients.patient_types),
    # exposed as a lookup so a tenant can rename/retire one without a FE release.
    "patient_type": [
        ("CH", "Child"), ("CP", "Collection Problem"), ("EF", "Employee Family"),
        ("OR", "Ortho"), ("SN", "Short Notice"), ("SR", "Senior"),
        ("SS", "Spanish Speaking"), ("UP", "Update Information"),
    ],
    # LEG-13: Responsible-Party *Type* (drives statement/collection behaviour).
    # Provisional — CA/CO/DI are from the legacy screenshot; confirm the full
    # authoritative list with the product owner and extend here.
    "resp_party_type": [
        ("CA", "Cash"), ("CO", "Collection"), ("DI", "Discount"),
        ("IN", "Insurance"), ("ST", "Standard"), ("WO", "Write Off"),
    ],
    # PP-8: the payment-plan discriminator, exposed as a lookup so the FE renders
    # labels from the backend. The write schemas enforce the same two values.
    "plan_type": [("regular", "Regular Payment Plan"), ("ortho", "Ortho Payment Plan")],
    # OPP-3: Ortho "Insert Class" dropdown (legacy default is None).
    "insert_class": [
        ("NONE", "None"), ("CL1", "Class I"), ("CL2", "Class II"), ("CL3", "Class III"),
    ],
    # OPP-5 / RPP-3: which disclosure text prints on the contract report.
    # `description` is the label; the printed body comes from the same row, so
    # replace these placeholders with the practice's approved wording.
    "financial_disclosure": [
        ("STD", "Standard Truth-in-Lending disclosure"),
        ("NOFIN", "No finance charge — interest-free contract"),
        ("ORTHO", "Orthodontic contract disclosure"),
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
        for idx, option in enumerate(options):
            key1, label = option[0], option[1]
            color = option[2] if len(option) > 2 else None  # optional 3rd element
            if (group_code, key1) in existing:
                continue
            db.add(Definition(
                tenant_id=tenant_id, group_code=group_code, key1=key1,
                description=label, color=color, sort_order=idx, is_active=True,
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
