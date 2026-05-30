#!/usr/bin/env python3
"""
run_schema.py
-------------
Creates (or recreates) the Dental PMS database schema in local PostgreSQL.

Usage (from "Dental PMS Backend" directory):
    python migration/run_schema.py            # Create all 75 tables (safe, skips existing)
    python migration/run_schema.py --verify   # Check which of the 75 tables exist in DB
    python migration/run_schema.py --drop     # DROP all 75 tables, then recreate
    python migration/run_schema.py --check    # Test DB connection and exit

Requirements:
    pip install -r migration/requirements.txt
    Copy migration/.env.example → migration/.env and fill in your DB credentials.
"""

import sys
import argparse
import psycopg2
import sqlparse
from pathlib import Path

# Allow running as `python migration/run_schema.py` from "Dental PMS Backend"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from migration.config import cfg
from migration.db.connection import get_conn

SCHEMA_SQL = Path(__file__).parent / "db" / "schema.sql"
CONSTRAINTS_SQL = Path(__file__).parent / "db" / "schema_constraints.sql"

# Drop order — reverse dependency order for all 75 tables.
# Every statement uses CASCADE so FK chains are handled automatically,
# but explicit ordering makes the log readable and prevents any
# "still referenced" errors on partial-CASCADE chains.
DROP_ORDER = [
    # ── Domain 11 leaf tables (most dependent, drop first) ─────────────────
    "image_details",                     # → image_groups
    "image_groups",                      # → tenants, offices, patients, imaging_templates
    "referral_demog_details",            # → referrals, tenants, referral_demog_headers
    "referral_demog_headers",            # → tenants
    "treatment_plan_insurance_details",  # → treatment_plan_items, insurance_plans
    "perio_chart_activity",              # → patients, offices
    "provider_route_slips",              # → tenants, providers, procedure_codes
    "codes_view",                        # → tenants, offices, procedure_codes
    "chart_colors",                      # → tenants
    "medical_history_details",           # → medical_history_records
    "patient_recalls",                   # → patients, offices, procedure_codes, users
    "patient_notes",                     # → patients, offices, users
    "caries_risk_assessments",           # → tenants, patients, offices
    "ortho_plans",                       # → tenants, patients, offices, procedure_codes, insurance_plans
    "patient_reg_plans",                 # → tenants, patients, offices
    "patient_sec_ins_payment_plans",     # → tenants, patients
    "patient_ins_payment_plans",         # → tenants, patients
    "patient_payment_plans",             # → tenants, patients, offices
    "provider_insurance_ids",            # → tenants, providers, insurance_carriers
    "ins_custom_coverage",               # → tenants
    "fee_schedule_assignments",          # → tenants, insurance_plans, insurance_carriers, providers, offices, fee_schedules
    "definition_groups",                 # → tenants
    "collection_agencies",               # → tenants
    "office_groups",                     # → tenants
    # ── Domain 10: Config & reference ─────────────────────────────────────
    "questionnaire_options",             # → questionnaire_headers
    "questionnaire_headers",             # → tenants
    "perio_chart_settings",              # → users
    "imaging_templates",                 # → offices
    "definitions",                       # → tenants
    # ── Domain 9: Staff & operations ──────────────────────────────────────
    "time_clock_entries",                # → tenants, offices, users
    # ── Domain 8: Communication ────────────────────────────────────────────
    "postcard_templates",                # → tenants, offices
    "letter_templates",                  # → tenants
    "sms_messages",                      # → tenants, offices, patients, appointments
    # ── Domain 7: Billing ──────────────────────────────────────────────────
    "claim_submissions",                 # → insurance_claims, users
    "payment_allocations",               # → patients, patient_procedures, patient_payments, insurance_claims, insurance_plans, providers
    "ledger_insurance_details",          # → patients, patient_procedures, insurance_claims, offices, insurance_plans
    "insurance_claims",                  # → patients, offices, providers, insurance_carriers, insurance_plans, users
    "patient_payments",                  # → patients, offices, providers, users
    # ── Domain 6: Clinical records ─────────────────────────────────────────
    "prescriptions",                     # → patients, offices, prescription_library, providers, users
    "perio_exam_details",                # → perio_exams
    "perio_exams",                       # → patients, offices, users
    "progress_notes",                    # → patients, offices, users
    "chart_conditions",                  # → patients, offices, procedure_codes, providers, chart_materials
    "patient_procedures",                # → patients, appointments, procedure_codes, providers, offices, insurance_claims, chart_materials, users
    # ── Domain 5: Scheduling ───────────────────────────────────────────────
    "appointment_procedures",            # → appointments, procedure_codes, providers, treatment_plans, chart_materials
    "appointments",                      # → patients, providers, operatories, offices, treatment_plans
    "treatment_plan_insurance_details",  # already listed above (CASCADE handles dupe gracefully)
    "treatment_plan_items",              # → treatment_plans, procedure_codes
    "treatment_plans",                   # → patients, offices, users
    # ── Domain 3: Patients ─────────────────────────────────────────────────
    "referrals",                         # → tenants, offices, patients, users
    "medical_history_records",           # → patients, patient_signatures, users
    "patient_signatures",                # → patients, users
    "account_notes",                     # → patients, users
    "patient_alerts",                    # → patients, users
    "patient_insurance",                 # → patients, insurance_plans, insurance_subscribers
    "patients",                          # → tenants, offices, providers, users
    # ── Domain 4: Clinical reference ───────────────────────────────────────
    "code_bundle_items",                 # → code_bundles, procedure_codes
    "code_bundles",                      # → tenants, users
    "prescription_library",              # → tenants
    "note_macros",                       # → tenants, users
    "chart_materials",                   # → tenants
    "fee_schedule_entries",              # → fee_schedules, procedure_codes
    "procedure_codes",                   # (standalone reference)
    # ── Domain 2: Insurance ────────────────────────────────────────────────
    "insurance_coverage_rules",          # → insurance_plans
    "insurance_subscribers",             # → tenants, insurance_plans, patients, offices
    "insurance_plans",                   # → tenants, insurance_carriers, employers
    "insurance_carriers",                # → tenants
    "fee_schedules",                     # → tenants, insurance_plans, offices
    "employers",                         # → tenants
    # ── Domain 1: Core infrastructure ─────────────────────────────────────
    "user_offices",                      # → users, offices
    "operatories",                       # → offices
    "providers",                         # → tenants, offices
    "offices",                           # → tenants, users
    "refresh_tokens",                    # → users
    "users",                             # → tenants, users (self-ref)
    "tenants",                           # root
]


# All 75 expected tables — used by --verify to confirm every table was created
EXPECTED_TABLES = [t for t in DROP_ORDER if t != "treatment_plan_insurance_details"[1:]]  # dedupe
EXPECTED_TABLES = list(dict.fromkeys(DROP_ORDER))  # ordered, deduplicated


def check_connection():
    print(f"  Host:     {cfg.DB_HOST}:{cfg.DB_PORT}")
    print(f"  Database: {cfg.DB_NAME}")
    print(f"  User:     {cfg.DB_USER}")
    try:
        conn = get_conn()
        conn.close()
        print("  Status:   ✓ Connected successfully")
        return True
    except psycopg2.OperationalError as e:
        print(f"  Status:   ✗ Connection failed — {e}")
        return False


def verify_schema(conn):
    """Check which tables exist in the DB and report any missing ones."""
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    existing = {row[0] for row in cur.fetchall()}
    expected = set(EXPECTED_TABLES)

    present  = sorted(expected & existing)
    missing  = sorted(expected - existing)
    extra    = sorted(existing - expected)   # tables in DB not in our list

    print(f"\n  Tables expected : {len(expected)}")
    print(f"  Tables in DB    : {len(existing)}")
    print(f"  Present         : {len(present)} ✓")

    if missing:
        print(f"\n  MISSING ({len(missing)}) — these were not created:")
        for t in missing:
            print(f"    ✗ {t}")
    else:
        print("  Missing         : 0 ✓  — all 75 tables exist")

    if extra:
        print(f"\n  Extra tables in DB not in schema list ({len(extra)}):")
        for t in extra:
            print(f"    ? {t}")

    return len(missing) == 0


def drop_all(conn):
    conn.autocommit = True        # each DROP commits immediately
    cur = conn.cursor()
    print("  Dropping all tables...")
    # Drop deferred FK constraints first so parent drops don't fail on them
    for stmt in [
        "ALTER TABLE IF EXISTS patient_procedures DROP CONSTRAINT IF EXISTS fk_proc_claim;",
        "ALTER TABLE IF EXISTS insurance_subscribers DROP CONSTRAINT IF EXISTS fk_ins_sub_patient;",
    ]:
        try:
            cur.execute(stmt)
        except Exception:
            pass    # constraint may not exist yet
    for table in DROP_ORDER:
        try:
            cur.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE;')
            print(f"    dropped {table}")
        except Exception as e:
            print(f"    skipped {table}: {e}")
    conn.autocommit = False
    print("  Done.")


def split_sql(sql: str) -> list[str]:
    """
    Split a SQL file into individual executable statements using sqlparse.
    Handles: DO $$ ... $$ blocks, multi-line CREATE TABLE, comments, etc.
    psycopg2 >= 2.9 forbids multi-statement strings in cursor.execute(),
    so we MUST split and execute one statement at a time.
    """
    statements = []
    for stmt in sqlparse.split(sql):
        stmt = stmt.strip()
        if stmt and stmt != ";":
            statements.append(stmt)
    return statements


def apply_sql_file(conn, path: Path, label: str):
    """Execute a SQL file statement-by-statement with autocommit."""
    sql = path.read_text(encoding="utf-8")
    statements = split_sql(sql)

    conn.autocommit = True
    cur = conn.cursor()

    ok = skipped = errors = 0
    for i, stmt in enumerate(statements, 1):
        try:
            cur.execute(stmt)
            ok += 1
        except psycopg2.errors.DuplicateTable:
            skipped += 1
        except psycopg2.errors.DuplicateObject:
            skipped += 1
        except Exception as e:
            errors += 1
            preview = stmt.replace("\n", " ")[:120]
            print(f"  ✗ {label} statement {i} failed: {e}")
            print(f"    SQL: {preview}...")

    conn.autocommit = False

    print(f"  {label}: {ok} executed, {skipped} skipped, {errors} errors")
    if errors:
        raise RuntimeError(f"{errors} {label} statement(s) failed — see output above")


def create_schema(conn):
    """Execute schema.sql then apply idempotent constraint patches."""
    apply_sql_file(conn, SCHEMA_SQL, "Schema")
    if CONSTRAINTS_SQL.exists():
        apply_sql_file(conn, CONSTRAINTS_SQL, "Constraints")


def main():
    parser = argparse.ArgumentParser(description="Build Dental PMS schema in PostgreSQL")
    parser.add_argument("--drop", action="store_true",
                        help="DROP all tables before creating (destructive!)")
    parser.add_argument("--check", action="store_true",
                        help="Test connection and exit")
    parser.add_argument("--verify", action="store_true",
                        help="List which of the 75 expected tables exist in the DB")
    args = parser.parse_args()

    print("\n── Dental PMS · Schema Builder ───────────────────────────")
    print("\n[1/3] Checking connection...")
    ok = check_connection()
    if not ok:
        sys.exit(1)

    if args.check:
        sys.exit(0)

    conn = get_conn()

    if args.verify:
        print("\n[2/2] Verifying schema tables in DB...")
        ok = verify_schema(conn)
        conn.close()
        sys.exit(0 if ok else 1)

    if args.drop:
        print("\n[2/3] Dropping existing tables (--drop flag set)...")
        confirm = input("  ⚠ This will DELETE all data. Type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            print("  Aborted.")
            conn.close()
            sys.exit(0)
        drop_all(conn)
    else:
        print("\n[2/3] Skipping drop (run with --drop to wipe first)")

    print("\n[3/3] Creating schema...")
    try:
        create_schema(conn)
    except Exception as e:
        conn.rollback()
        print(f"\n  ✗ Schema creation failed: {e}")
        conn.close()
        sys.exit(1)

    conn.close()
    print("\n✓ Schema ready. Run `python migration/run_migration.py` to load data.\n")


if __name__ == "__main__":
    main()
