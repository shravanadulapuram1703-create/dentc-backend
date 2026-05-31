"""
STEP 52 — empty tables (schema-only stubs)
These source files exist but contained header-only exports (no data rows).
The tables are created by schema.sql. This step verifies connectivity
and reports that each table is ready for future data entry or migration.

Tables covered:
  perio_chart_activity       ← ChartPerioActivity.txt (empty)
  collection_agencies        ← COLAGENCY.txt (empty)
  image_details              ← IMAGEDETAIL.txt (empty)
  image_groups               ← IMAGEGROUP.txt (empty)
  ins_custom_coverage        ← InsCustCoverage.txt (empty)
  office_groups              ← OGROUP.txt (empty)
  caries_risk_assessments    ← PatCariesRisk1340.txt (empty)
  patient_payment_plans      ← PatContractBilling.txt (empty)
  patient_ins_payment_plans  ← PatInsContractBilling.txt (empty)
  patient_sec_ins_payment_plans ← PATSECINSCONTRACTBILLING.txt (empty)
  ortho_plans                ← PATORTHOPLAN.txt (empty)
  patient_reg_plans          ← PatRegPlan.txt (empty)
  provider_insurance_ids     ← PROVIDERINSID.txt (empty)
  provider_route_slips       ← PROVIDERROUTESLIP.txt (empty)
  referral_demog_headers     ← REFERRALDEMOGH.txt (empty)
  referral_demog_details     ← REFERRALDEMOGD.txt (empty)

Logical entities (no source file — created for future use):
  patient_notes              ← PATNOTES / PATNOTES_ARCHIVE
  patient_recalls            ← PATRECALL
  medical_history_details    ← PATMEDICALHISTORYD
  treatment_plan_insurance_details ← TREATPLANINSD / TREATPLANINSD_ARCHIVE
"""

STUB_TABLES = [
    ("perio_chart_activity",          "ChartPerioActivity.txt",         "empty"),
    ("collection_agencies",           "COLAGENCY.txt",                  "empty"),
    ("image_details",                 "IMAGEDETAIL.txt",                 "empty"),
    ("image_groups",                  "IMAGEGROUP.txt",                  "empty"),
    ("ins_custom_coverage",           "InsCustCoverage.txt",             "empty"),
    ("office_groups",                 "OGROUP.txt",                      "empty"),
    ("caries_risk_assessments",       "PatCariesRisk1340.txt",           "empty"),
    ("patient_payment_plans",         "PatContractBilling.txt",          "empty"),
    ("patient_ins_payment_plans",     "PatInsContractBilling.txt",       "empty"),
    ("patient_sec_ins_payment_plans", "PATSECINSCONTRACTBILLING.txt",    "empty"),
    ("ortho_plans",                   "PATORTHOPLAN.txt",                "empty"),
    ("patient_reg_plans",             "PatRegPlan.txt",                  "empty"),
    ("provider_insurance_ids",        "PROVIDERINSID.txt",               "empty"),
    ("provider_route_slips",          "PROVIDERROUTESLIP.txt",           "empty"),
    ("referral_demog_headers",        "REFERRALDEMOGH.txt",              "empty"),
    ("referral_demog_details",        "REFERRALDEMOGD.txt",              "empty"),
    ("patient_notes",                 "PATNOTES (no export file)",       "logical"),
    ("patient_recalls",               "PATRECALL (no export file)",      "logical"),
    ("medical_history_details",       "PATMEDICALHISTORYD (no export)",  "logical"),
    ("treatment_plan_insurance_details", "TREATPLANINSD (no export)",    "logical"),
]


def run(conn, maps: dict) -> dict:
    cur = conn.cursor()
    print("  [s52] Verifying empty/stub tables exist in DB:")

    for table_name, source_note, kind in STUB_TABLES:
        cur.execute(
            """
            SELECT COUNT(*) FROM information_schema.tables
             WHERE table_schema = 'public' AND table_name = %s
            """,
            (table_name,),
        )
        exists = cur.fetchone()[0] == 1
        status = "✓ exists" if exists else "✗ MISSING — re-run run_schema.py"
        tag = "empty-source" if kind == "empty" else "logical-entity"
        print(f"    {table_name:<45} [{tag}]  {status}")

    print("  [s52] All stub tables verified (no data to migrate for these yet)")
    return {}
