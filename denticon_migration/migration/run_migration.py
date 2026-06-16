#!/usr/bin/env python3
"""
run_migration.py
----------------
Runs all 55 Denticon → Dental PMS migration steps in dependency order.

Usage (from "Dental PMS Backend" directory):
    python migration/run_migration.py                  # Run all 55 steps (all rows)
    python migration/run_migration.py --sample         # Cap at 5000 source rows per table
    python migration/run_migration.py --max-rows 1000  # Custom cap per table
    python migration/run_migration.py --all            # Full load (ignore env limit)
    python migration/run_migration.py --from 19        # Resume from step 19 (patients)
    python migration/run_migration.py --step 28        # Run a single step only
    python migration/run_migration.py --steps 1-10     # Run a range of steps
    python migration/run_migration.py --dry-run        # Parse files, count rows, no DB writes

Requirements:
    1. Run `python migration/run_schema.py` first to build the tables.
    2. Copy migration/.env.example → migration/.env and configure it.
    3. pip install -r migration/requirements.txt

How it works:
    • Each step is a Python module in migration/steps/ with a run(conn, maps) function.
    • Steps return a lookup map (e.g. { "2829": 1 } for tenant_map).
    • Maps are accumulated and passed into every subsequent step so FK resolution
      happens in memory — no repeated DB queries.
    • Every step uses ON CONFLICT DO NOTHING / DO UPDATE, so the full run is
      idempotent. Re-running after a partial failure is always safe.

Adding a new step:
    1. Create migration/steps/sNN_table_name.py with a run(conn, maps) → dict.
    2. Add it to STEPS below in the correct position.
    3. Re-run. Only the new step will do meaningful work (existing rows skip).
"""

import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from migration.config import cfg
from migration.db.connection import get_conn
from migration.utils.logger import MigrationLogger
from migration.utils.map_loader import load_maps_from_db, summarize_maps

# ── Step registry ──────────────────────────────────────────────────────────────
# Each tuple: (step_number, module_path, map_key_returned)
# map_key_returned is the key under which the step's return value is stored in `maps`.
# A step may return {} (no map needed downstream) or a named dict.

from migration.steps import (
    s01_tenants, s02_offices, s03_providers,
    s03b_seed_users, s03c_user_offices,
    s04_operatories,
    s05_employers, s06_insurance_carriers, s07_insurance_plans,
    s08_insurance_coverage_rules, s09_fee_schedules, s10_procedure_codes,
    s11_fee_schedule_entries, s12_chart_materials, s13_note_macros,
    s14_code_bundles, s15_code_bundle_items, s16_prescription_library,
    s17_patients, s18_insurance_subscribers, s19_patient_insurance,
    s20_patient_alerts, s21_account_notes, s22_patient_signatures,
    s23_medical_history_records, s24_referrals, s25_treatment_plans,
    s26_appointments, s27_appointment_procedures,
    s27b_treatment_plan_items,
    s28_patient_procedures, s29_patient_payments,
    s30_insurance_claims, s31_claim_submissions,
    s32_ledger_insurance_details, s33_payment_allocations,
    s34_chart_conditions, s35_progress_notes,
    s36_perio_exams, s37_perio_exam_details,
    s38_prescriptions, s39_sms_messages, s40_time_clock_entries,
    s41_letter_templates, s42_postcard_templates, s43_definitions,
    s44_imaging_templates, s45_perio_chart_settings,
    s46_questionnaire_headers, s47_questionnaire_options,
    s48_chart_colors, s49_codes_view, s50_definition_groups,
    s51_fee_schedule_assignments, s52_empty_tables_stubs,
)

STEPS = [
    # (step_number, module,                       map_key_stored_in_maps)
    # ── Domain 1: Core infrastructure ─────────────────────────────────────
    ( 1,  s01_tenants,                        "tenant_map"),
    ( 2,  s02_offices,                        "office_map"),
    ( 3,  s03_providers,                      "provider_map"),
    ( 4,  s03b_seed_users,                    "user_map"),    # users table (was missing)
    ( 5,  s03c_user_offices,                  None),          # user_offices (was missing)
    ( 6,  s04_operatories,                    "operatory_map"),
    # ── Domain 2: Insurance ────────────────────────────────────────────────
    ( 7,  s05_employers,                      "employer_map"),
    ( 8,  s06_insurance_carriers,             "carrier_map"),
    ( 9,  s07_insurance_plans,                "ins_plan_map"),
    (10,  s08_insurance_coverage_rules,       None),
    (11,  s09_fee_schedules,                  "fee_sched_map"),
    # ── Domain 4: Clinical reference (procedure_codes before fee_entries) ──
    (12,  s10_procedure_codes,                None),          # returns proc_code_set via maps.update()
    (13,  s11_fee_schedule_entries,           None),
    (14,  s12_chart_materials,                "material_map"),
    (15,  s13_note_macros,                    None),
    (16,  s14_code_bundles,                   "bundle_map"),
    (17,  s15_code_bundle_items,              None),
    (18,  s16_prescription_library,           "rx_lib_map"),
    # ── Domain 3: Patients ─────────────────────────────────────────────────
    (19,  s17_patients,                       "patient_map"),
    (20,  s18_insurance_subscribers,          "sub_map"),
    (21,  s19_patient_insurance,              None),
    (22,  s20_patient_alerts,                 None),
    (23,  s21_account_notes,                  None),
    (24,  s22_patient_signatures,             "sig_map"),
    (25,  s23_medical_history_records,        None),
    (26,  s24_referrals,                      None),
    # ── Domain 5/6: Scheduling + Clinical records ──────────────────────────
    (27,  s25_treatment_plans,                "txplan_map"),
    (28,  s26_appointments,                   "appt_map"),
    (29,  s27_appointment_procedures,         None),
    (30,  s27b_treatment_plan_items,          None),          # treatment_plan_items (was missing)
    (31,  s28_patient_procedures,             "procedure_map"),
    (32,  s29_patient_payments,               "payment_map"),
    # ── Domain 7: Billing ──────────────────────────────────────────────────
    (33,  s30_insurance_claims,               "claim_map"),
    (34,  s31_claim_submissions,              None),
    (35,  s32_ledger_insurance_details,       None),
    (36,  s33_payment_allocations,            None),
    # ── Domain 6 (cont.): Clinical records ────────────────────────────────
    (37,  s34_chart_conditions,               None),
    (38,  s35_progress_notes,                 None),
    (39,  s36_perio_exams,                    "perio_exam_map"),
    (40,  s37_perio_exam_details,             None),
    (41,  s38_prescriptions,                  None),
    # ── Domain 8: Communication ────────────────────────────────────────────
    (42,  s39_sms_messages,                   None),
    # ── Domain 9: Staff & ops (needs user_map from step 4) ────────────────
    (43,  s40_time_clock_entries,             None),
    # ── Domain 8 (cont.) ──────────────────────────────────────────────────
    (44,  s41_letter_templates,               None),
    (45,  s42_postcard_templates,             None),
    # ── Domain 10: Config & reference ─────────────────────────────────────
    (46,  s43_definitions,                    None),
    (47,  s44_imaging_templates,              None),
    (48,  s45_perio_chart_settings,           None),          # needs user_map from step 4
    (49,  s46_questionnaire_headers,          "q_map"),
    (50,  s47_questionnaire_options,          None),
    # ── Domain 11: Additional source file coverage ─────────────────────────
    (51,  s48_chart_colors,                   "color_map"),
    (52,  s49_codes_view,                     None),
    (53,  s50_definition_groups,              None),
    (54,  s51_fee_schedule_assignments,       None),
    (55,  s52_empty_tables_stubs,             None),          # verifies 20 schema-only tables
]


# ── Argument parsing ───────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="Run Denticon → Dental PMS data migration")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--from", dest="from_step", type=int, metavar="N",
                       help="Resume from step N (runs N through 55)")
    group.add_argument("--step", dest="single_step", type=int, metavar="N",
                       help="Run only step N")
    group.add_argument("--steps", dest="step_range", metavar="N-M",
                       help="Run steps N through M (e.g. --steps 1-10)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse source files and count rows without writing to DB")
    limit = parser.add_mutually_exclusive_group()
    limit.add_argument("--max-rows", type=int, metavar="N",
                       help="Sample mode: cap source rows per step/table (e.g. 5000)")
    limit.add_argument("--sample", action="store_true",
                       help="Sample mode shorthand for --max-rows 5000")
    limit.add_argument("--all", action="store_true",
                       help="Full migration: process every source row (ignore limits)")
    return parser.parse_args()


def apply_row_limit(args) -> None:
    """Apply CLI/env row limit to cfg.MIGRATION_MAX_ROWS."""
    if args.all:
        cfg.MIGRATION_MAX_ROWS = None
    elif args.max_rows is not None:
        cfg.MIGRATION_MAX_ROWS = args.max_rows
    elif args.sample:
        cfg.MIGRATION_MAX_ROWS = 5000
    # else: keep value loaded from MIGRATION_MAX_ROWS env (or None)


def resolve_steps(args) -> list[tuple]:
    """Return the filtered subset of STEPS to run."""
    if args.single_step:
        return [s for s in STEPS if s[0] == args.single_step]
    if args.from_step:
        return [s for s in STEPS if s[0] >= args.from_step]
    if args.step_range:
        lo, hi = (int(x) for x in args.step_range.split("-"))
        return [s for s in STEPS if lo <= s[0] <= hi]
    return STEPS


# ── Dry-run mode ───────────────────────────────────────────────────────────────

def dry_run(steps_to_run):
    from migration.utils.reader import read_denticon_file, read_folder
    print("\n── DRY RUN — counting source rows ────────────────────────────────")
    if cfg.MIGRATION_MAX_ROWS is not None:
        print(f"  Row limit   : {cfg.MIGRATION_MAX_ROWS:,} per step (sample mode)")
    else:
        print("  Row limit   : none (full migration)")
    SRC_FILES = {
        1:  ("PGroup.txt",),
        2:  ("Office.txt",),
        3:  ("Providers.txt",),
        4:  ("Operatory.txt",),
        5:  ("Employers.txt",),
        6:  ("Carrier.txt",),
        7:  ("InsPlans.txt",),
        8:  ("INSCOVERAGE",),    # folder
        9:  ("FeeScheH.txt",),
        10: ("Codes.txt",),
        11: ("FeeScheD.txt",),
        12: ("ChartMaterials.txt",),
        13: ("ChartNotesMacros.txt",),
        14: ("CODESEXPLOSIONH.txt",),
        15: ("CODESEXPLOSIOND.txt",),
        16: ("PGRX.txt",),
        17: ("RespParty.txt",),
        18: ("RespInsplan.txt",),
        19: ("PatInsPlans.txt",),
        20: ("PatFlashAlerts.txt",),
        21: ("RESPNOTES.txt",),
        22: ("PATSIGNATURE.txt",),
        23: ("PatMedicalHistoryH.txt",),
        24: ("Referrals.txt",),
        25: ("AppointmentDetails.txt",),
        26: ("AppointmentHeader.txt", "APPTH_ARCHIVE"),
        27: ("AppointmentDetails.txt",),
        28: ("LEDGER",),
        29: ("LEDGER",),
        30: ("CLAIMH",),
        31: ("ClaimsDetail.txt",),
        32: ("LedgerInsDetail_Archive.txt",),
        33: ("LedgerPymtAllocation_Archive.txt",),
        34: ("ChartActivity.txt",),
        35: ("ProgressNotes_Archive.txt",),
        36: ("PERIOCHARTHEADER.txt",),
        37: ("PERIOCHARTDETAIL.txt",),
        38: ("PatRx.txt",),
        39: ("SMS.txt",),
        40: ("TCLOCK.txt",),
        41: ("LETTERS.txt",),
        42: ("POSTCARDS.txt",),
        43: ("DEFINITIONS.txt",),
        44: ("IMAGETEMPLATE.txt",),
        45: ("CHARTPERIOSETUP.txt",),
        46: ("QALISTH.txt",),
        47: ("QALISTD.txt",),
    }
    nums = sorted(s[0] for s in steps_to_run)
    for num in nums:
        files = SRC_FILES.get(num, ())
        cfg.begin_step()
        step_count = 0
        for f in files:
            p = cfg.src(f)
            if not p.exists():
                print(f"  Step {num:02d}: {f} — NOT FOUND")
                continue
            if p.is_dir():
                n = sum(1 for _ in read_folder(p))
                label = f"{f}/ (folder)"
            else:
                n = sum(1 for _ in read_denticon_file(p))
                label = f
            step_count += n
            cap = f" (capped)" if cfg.row_budget_exhausted() else ""
            print(f"  Step {num:02d}: {label} — {n:,} rows{cap}")
        if len(files) > 1 and step_count:
            print(f"           → step total: {step_count:,} source rows")
    print()


# ── Post-migration table summary ───────────────────────────────────────────────

# Ordered list of all 75 tables grouped by domain for the final summary
ALL_TABLES = [
    # Domain 1 — Core Infrastructure
    ("tenants",                        "Core"),
    ("users",                          "Core"),
    ("refresh_tokens",                 "Core"),
    ("offices",                        "Core"),
    ("providers",                      "Core"),
    ("operatories",                    "Core"),
    ("user_offices",                   "Core"),
    # Domain 2 — Insurance
    ("employers",                      "Insurance"),
    ("insurance_carriers",             "Insurance"),
    ("insurance_plans",                "Insurance"),
    ("insurance_subscribers",          "Insurance"),
    ("insurance_coverage_rules",       "Insurance"),
    ("fee_schedules",                  "Insurance"),
    ("fee_schedule_entries",           "Insurance"),
    ("fee_schedule_assignments",       "Insurance"),
    ("ins_custom_coverage",            "Insurance"),
    # Domain 3 — Patients
    ("patients",                       "Patients"),
    ("patient_insurance",              "Patients"),
    ("patient_alerts",                 "Patients"),
    ("account_notes",                  "Patients"),
    ("patient_signatures",             "Patients"),
    ("medical_history_records",        "Patients"),
    ("medical_history_details",        "Patients"),
    ("referrals",                      "Patients"),
    ("patient_notes",                  "Patients"),
    ("patient_recalls",                "Patients"),
    ("caries_risk_assessments",        "Patients"),
    ("patient_payment_plans",          "Patients"),
    ("patient_ins_payment_plans",      "Patients"),
    ("patient_sec_ins_payment_plans",  "Patients"),
    ("patient_reg_plans",              "Patients"),
    ("ortho_plans",                    "Patients"),
    # Domain 4 — Clinical Reference
    ("procedure_codes",                "Ref"),
    ("chart_materials",                "Ref"),
    ("note_macros",                    "Ref"),
    ("code_bundles",                   "Ref"),
    ("code_bundle_items",              "Ref"),
    ("prescription_library",           "Ref"),
    ("chart_colors",                   "Ref"),
    ("codes_view",                     "Ref"),
    ("provider_route_slips",           "Ref"),
    ("provider_insurance_ids",         "Ref"),
    # Domain 5 — Scheduling
    ("appointments",                   "Scheduling"),
    ("appointment_procedures",         "Scheduling"),
    # Domain 6 — Clinical Records
    ("treatment_plans",                "Clinical"),
    ("treatment_plan_items",           "Clinical"),
    ("treatment_plan_insurance_details","Clinical"),
    ("patient_procedures",             "Clinical"),
    ("chart_conditions",               "Clinical"),
    ("progress_notes",                 "Clinical"),
    ("perio_exams",                    "Clinical"),
    ("perio_exam_details",             "Clinical"),
    ("perio_chart_activity",           "Clinical"),
    ("prescriptions",                  "Clinical"),
    # Domain 7 — Billing
    ("patient_payments",               "Billing"),
    ("ledger_insurance_details",       "Billing"),
    ("payment_allocations",            "Billing"),
    ("insurance_claims",               "Billing"),
    ("claim_submissions",              "Billing"),
    # Domain 8 — Communication
    ("sms_messages",                   "Comms"),
    ("letter_templates",               "Comms"),
    ("postcard_templates",             "Comms"),
    ("referral_demog_headers",         "Comms"),
    ("referral_demog_details",         "Comms"),
    # Domain 9 — Staff & Ops
    ("time_clock_entries",             "Staff"),
    # Domain 10 — Config & Reference
    ("definitions",                    "Config"),
    ("definition_groups",              "Config"),
    ("imaging_templates",              "Config"),
    ("perio_chart_settings",           "Config"),
    ("questionnaire_headers",          "Config"),
    ("questionnaire_options",          "Config"),
    ("image_groups",                   "Config"),
    ("image_details",                  "Config"),
    ("office_groups",                  "Config"),
    ("collection_agencies",            "Config"),
]


def collect_table_summary(conn) -> list[dict]:
    """
    Query every table's row count and return a list of dicts.
    Also prints the formatted table to stdout (which the logger mirrors to file).
    Returns: [{"table": str, "domain": str, "rows": int}, ...]
    """
    cur = conn.cursor()

    union_parts = " UNION ALL ".join(
        f"SELECT '{t}' AS tbl, '{d}' AS domain, COUNT(*) AS cnt FROM {t}"
        for t, d in ALL_TABLES
    )
    try:
        cur.execute(union_parts)
        db_rows = {r[0]: r[2] for r in cur.fetchall()}
    except Exception as e:
        print(f"  (Could not fetch table counts: {e})")
        return []

    # ── Print formatted summary ───────────────────────────────────────────────
    print("\n" + "─" * 62)
    print(f"  {'TABLE':<42} {'DOMAIN':<12} {'ROWS':>6}")
    print("─" * 62)

    current_domain = None
    total_rows     = 0
    tables_with_data = 0
    result         = []

    for table, domain in ALL_TABLES:
        cnt = db_rows.get(table, 0)
        if domain != current_domain:
            if current_domain is not None:
                print()
            current_domain = domain

        marker = "✓" if cnt > 0 else "·"
        print(f"  {marker} {table:<40} {domain:<12} {cnt:>6,}")
        total_rows += cnt
        if cnt > 0:
            tables_with_data += 1
        result.append({"table": table, "domain": domain, "rows": cnt})

    print("─" * 62)
    print(f"  {'TOTAL':<42} {'':12} {total_rows:>6,}")
    print(f"  {tables_with_data} of {len(ALL_TABLES)} tables have data")

    return result


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    apply_row_limit(args)
    steps_to_run = resolve_steps(args)

    if not steps_to_run:
        print("No steps matched the filter. Exiting.")
        sys.exit(1)

    if args.dry_run:
        print("\n── Dental PMS · Data Migration (DRY RUN) ──────────────────────────")
        print(f"  Data source : {cfg.DATA_SOURCE_PATH}")
        dry_run(steps_to_run)
        return

    # ── Initialise logger (captures all output to timestamped log file) ───────
    logger = MigrationLogger()

    print("\n── Dental PMS · Data Migration ────────────────────────────────────")
    print(f"  Data source : {cfg.DATA_SOURCE_PATH}")
    print(f"  Database    : {cfg.DB_NAME} @ {cfg.DB_HOST}:{cfg.DB_PORT}")
    print(f"  Row limit   : {cfg.row_limit_label()}")
    print(f"  Steps       : {steps_to_run[0][0]} → {steps_to_run[-1][0]}")
    print(f"  Total steps : {len(STEPS)}")

    logger.start(
        db_name     = cfg.DB_NAME,
        db_host     = cfg.DB_HOST,
        db_port     = cfg.DB_PORT,
        data_source = str(cfg.DATA_SOURCE_PATH),
        steps_range = f"{steps_to_run[0][0]}→{steps_to_run[-1][0]}",
    )

    conn = get_conn()
    # Bulk load over a remote DB: skip waiting for WAL flush on each commit.
    # Safe for a re-runnable migration — worst case after a crash is replaying
    # the last batch, which every step already handles idempotently.
    with conn.cursor() as _c:
        _c.execute("SET synchronous_commit TO off")
    conn.commit()

    maps: dict = {}
    if args.from_step and args.from_step > 1:
        print(f"\n  Resuming from step {args.from_step} — loading maps from DB...")
        maps = load_maps_from_db(conn)
        print(f"  Maps loaded : {summarize_maps(maps)}")

    total_start = time.time()
    errors: list[str] = []

    for step_num, module, map_key in steps_to_run:
        step_name  = module.__name__.split(".")[-1]
        step_start = time.time()
        print(f"\nStep {step_num:02d}/{len(STEPS)} — {step_name}")
        cfg.begin_step()
        try:
            result = module.run(conn, maps)
            if map_key is not None:
                maps[map_key] = result if result is not None else {}
            elif result:
                maps.update(result)
            elapsed = time.time() - step_start
            print(f"  ✓ Done in {elapsed:.1f}s")
            if (
                cfg.MIGRATION_MAX_ROWS is not None
                and cfg.step_rows_read() >= cfg.MIGRATION_MAX_ROWS
            ):
                print(
                    f"  ↳ capped at {cfg.MIGRATION_MAX_ROWS:,} source rows "
                    f"(use --all for full load)"
                )
            logger.log_step(step_num, step_name, elapsed, "ok")
        except Exception as exc:
            conn.rollback()
            elapsed = time.time() - step_start
            msg = f"Step {step_num} ({step_name}) FAILED: {exc}"
            print(f"  ✗ {msg}")
            errors.append(msg)
            logger.log_step(step_num, step_name, elapsed, "failed", str(exc))
            logger.log_error(step_num, msg)

    total = time.time() - total_start
    print(f"\n── Migration complete in {total:.0f}s ──────────────────────────────")

    if errors:
        print(f"\n  {len(errors)} step(s) had errors:")
        for e in errors:
            print(f"    ✗ {e}")

    # ── Table row count summary ───────────────────────────────────────────────
    print("\n── Row counts per table ────────────────────────────────────────────")
    summary_conn = get_conn()
    table_counts = collect_table_summary(summary_conn)
    summary_conn.close()

    # ── Finalise log (writes .log + .json, restores stdout) ──────────────────
    logger.finish(table_counts, errors)

    conn.close()

    if errors:
        sys.exit(1)
    else:
        print("\n  All steps completed successfully ✓\n")


if __name__ == "__main__":
    main()
