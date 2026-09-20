"""Report 1 — pricing data completeness: is every data point the fee-schedule
calculation needs present in the DB, and what is in the export folder but not
ingested? (Read-only; produces a report + a CSV of un-priceable patients.)

For each pricing input the resolver / split engine reads, it compares the count in
the Denticon export folder against what landed in the DB, and flags the gap. Then,
per patient with a ledger, it checks whether the pieces needed to price that
patient's charges are present (a home office with a UCR pointer, the patient's fee
schedule or an office default, and — for the insurance split — an active plan with
coverage rules), and writes the patients that are missing a piece to a CSV.

Nothing is written to the DB.

Usage
-----
    python -m scripts.report_pricing_data_completeness
    python -m scripts.report_pricing_data_completeness --csv out.csv
"""

from __future__ import annotations

import argparse
import csv as _csv

from sqlalchemy import text

from scripts.backfill_pricing_hierarchy import _read, _read_many, _s, _source_root
from app.db.session import SessionLocal


def _folder_rows(root, name: str) -> int:  # noqa: ANN001
    """Parsed row count for a file or a folder of N.txt (via the export reader, so
    quoting/embedded newlines are handled the same way ingestion sees them)."""
    path = root / name
    n = 0
    if path.is_dir():
        for part in sorted(path.glob("*.txt")):
            n += sum(1 for _ in _read(part))
    elif path.exists():
        n += sum(1 for _ in _read(path))
    return n


def _folder_rows_where(root, name: str, predicate) -> int:  # noqa: ANN001
    path = root / name
    files = sorted(path.glob("*.txt")) if path.is_dir() else ([path] if path.exists() else [])
    n = 0
    for part in files:
        for row in _read(part):
            if predicate(row):
                n += 1
    return n


def _scalar(db, sql: str) -> int:  # noqa: ANN001
    return int(db.execute(text(sql)).scalar() or 0)


def _line(name: str, folder: int, db_count: int, note: str = "") -> dict:
    gap = folder - db_count
    return {"input": name, "folder": folder, "db": db_count, "gap": gap, "note": note}


def _ledger_charge_counts(root) -> dict:  # noqa: ANN001
    """Single pass over LEDGER: charge rows (LTYPE='C'), and how many of those have
    a zero/blank AMOUNT in the source (the fee is only in the free-text note)."""
    charges = zero_amt = 0
    p = root / "LEDGER"
    files = sorted(p.glob("*.txt")) if p.is_dir() else ([p] if p.exists() else [])
    for part in files:
        for r in _read(part):
            if _s(r.get("LTYPE")).upper() != "C":
                continue
            charges += 1
            if _s(r.get("AMOUNT")) in ("", "0", "0.0000", "0.00"):
                zero_amt += 1
    return {"ledger": charges, "ledger_zero_amt": zero_amt}


def folder_metrics(root) -> dict:  # noqa: ANN001
    """All the export-side counts, computed with NO DB connection open (the scans
    take minutes; an idle DB connection held across them drops)."""
    def _set(name, col):  # noqa: ANN001
        return _folder_rows_where(root, name, lambda r: _s(r.get(col)) not in ("", "0", "0.0000"))

    # single-pass the multi-metric big files
    pat_total = pat_fs = 0
    p = root / "PATIENT"
    for part in (sorted(p.glob("*.txt")) if p.is_dir() else []):
        for r in _read(part):
            pat_total += 1
            if _s(r.get("FEESCHEDULE")) not in ("", "0"):
                pat_fs += 1

    pins_total = pins_sec = pins_ded = 0
    pp = root / "PatInsPlans.txt"
    if pp.exists():
        for r in _read(pp):
            pins_total += 1
            if _s(r.get("INSTYPE")).upper() == "S":
                pins_sec += 1
            if _s(r.get("INDDEDREM")) not in ("", "0", "0.0000"):
                pins_ded += 1

    return {
        "feeH": _folder_rows(root, "FeeScheH.txt"),
        "feeD": _folder_rows(root, "FeeScheD.txt"),
        "feeA": _folder_rows(root, "FeeScheA.txt"),
        "off_feeid": _set("Office.txt", "FEEID"),
        "off_pat": _set("Office.txt", "PATIENTFEEID"),
        "pat_total": pat_total, "pat_fs": pat_fs,
        "car_feeid": _set("Carrier.txt", "FEEID"),
        "insplans": _folder_rows(root, "InsPlans.txt"),
        "inscov": _folder_rows(root, "INSCOVERAGE"),
        "pins_total": pins_total, "pins_sec": pins_sec, "pins_ded": pins_ded,
        # LEDGER single pass: only LTYPE='C' rows are charges (payments/adjustments
        # are P/I/A). Old charges carry AMOUNT=0 in the *source* (the fee lives only
        # in the free-text note, e.g. "$30 ..."), so split them out.
        **_ledger_charge_counts(root),
        "ledgerinsd": _folder_rows(root, "LEDGERINSD"),
        "codes": _folder_rows(root, "Codes.txt"),
    }


def build_report(db, f: dict) -> list[dict]:  # noqa: ANN001
    return [
        _line("fee_schedule headers (FeeScheH)", f["feeH"],
              _scalar(db, "SELECT count(*) FROM fee_schedules"), "one per practice fee list"),
        _line("fee_schedule entries (FeeScheD)", f["feeD"],
              _scalar(db, "SELECT count(*) FROM fee_schedule_entries"),
              "the per-code price rows the resolver reads"),
        _line("fee_schedule assignments (FeeScheA)", f["feeA"],
              _scalar(db, "SELECT count(*) FROM fee_schedule_assignments"),
              "payer/provider bindings (+ office/carrier backfill)"),
        _line("offices with a UCR list (Office.FEEID)", f["off_feeid"],
              _scalar(db, "SELECT count(*) FROM offices WHERE default_ucr_fee_schedule_id IS NOT NULL"),
              "tier 6 - office UCR pointer"),
        _line("offices with a default list (Office.PATIENTFEEID)", f["off_pat"],
              _scalar(db, "SELECT count(*) FROM offices WHERE default_fee_schedule_id IS NOT NULL"),
              "tier 5 - office default patient list"),
        _line("patients with a fee schedule (PATIENT.FEESCHEDULE)", f["pat_fs"],
              _scalar(db, "SELECT count(*) FROM patients WHERE fee_schedule_id IS NOT NULL"),
              "tier 3 - the patient's own list"),
        _line("carriers with a fee list (Carrier.FEEID)", f["car_feeid"],
              _scalar(db, "SELECT count(*) FROM fee_schedule_assignments WHERE carrier_id IS NOT NULL"),
              "tier 2 - carrier binding"),
        _line("insurance plans (InsPlans)", f["insplans"],
              _scalar(db, "SELECT count(*) FROM insurance_plans"), "the plan the split % comes from"),
        _line("coverage rules (INSCOVERAGE)", f["inscov"],
              _scalar(db, "SELECT count(*) FROM insurance_coverage_rules"),
              "the coverage % bands per plan"),
        _line("patient insurance slots (PatInsPlans)", f["pins_total"],
              _scalar(db, "SELECT count(*) FROM patient_insurance"), "which plan(s) a patient is on"),
        _line("  ...secondary slots (INSTYPE=S)", f["pins_sec"],
              _scalar(db, "SELECT count(*) FROM patient_insurance WHERE lower(insurance_type)='secondary'"),
              "COB - s19 read the wrong column"),
        _line("  ...remaining deductible (INDDEDREM>0)", f["pins_ded"],
              _scalar(db, "SELECT count(*) FROM patient_insurance WHERE deductible_remaining IS NOT NULL AND deductible_remaining>0"),
              "reduces insured base; 0/NULL falls back to plan"),
        _line("charges (LEDGER, LTYPE=C only)", f["ledger"],
              _scalar(db, "SELECT count(*) FROM patient_procedures"),
              "charge rows only (payments/adjustments excluded)"),
        _line("  ...of which AMOUNT=0 in the SOURCE", f["ledger_zero_amt"],
              _scalar(db, "SELECT count(*) FROM patient_procedures WHERE fee=0"),
              "source has no structured fee (only in note text) - not an ingest gap"),
        _line("per-charge provenance (LEDGERINSD)", f["ledgerinsd"],
              _scalar(db, "SELECT count(*) FROM procedure_fee_provenance"),
              "the schedule Denticon used per charge (FEEID)"),
        _line("procedure codes (Codes)", f["codes"],
              _scalar(db, "SELECT count(*) FROM procedure_codes"), "the code catalog"),
        _line("  ...codes with a coverage_category", -1,
              _scalar(db, "SELECT count(*) FROM procedure_codes WHERE coverage_category IS NOT NULL"),
              "FEE-1 band key; derived (no direct folder column)"),
    ]


def priceability(db, csv_path: str | None) -> dict:  # noqa: ANN001
    """Per patient with a ledger: are the pieces to price present? Writes the
    patients missing a piece to CSV."""
    sql = text("""
        WITH charged AS (
            SELECT DISTINCT pp.patient_id AS pid
            FROM patient_procedures pp
            WHERE pp.is_void = false
        )
        SELECT p.id, p.tenant_id, p.home_office_id, p.fee_schedule_id,
               o.default_ucr_fee_schedule_id AS office_ucr,
               o.default_fee_schedule_id AS office_default,
               (SELECT count(*) FROM patient_insurance pi
                  WHERE pi.patient_id = p.id AND pi.is_active = true
                        AND pi.ins_plan_id IS NOT NULL) AS active_slots,
               (SELECT count(*) FROM patient_insurance pi
                  JOIN insurance_coverage_rules r ON r.ins_plan_id = pi.ins_plan_id
                  WHERE pi.patient_id = p.id AND pi.is_active = true) AS coverage_rules
        FROM patients p
        JOIN charged c ON c.pid = p.id
        LEFT JOIN offices o ON o.id = p.home_office_id
    """)
    total = 0
    has_fee_source = 0     # patient list OR office default OR office UCR → a fee can resolve
    has_office = 0
    insured = 0
    insured_with_rules = 0
    missing_rows: list[dict] = []
    for r in db.execute(sql):
        total += 1
        can_fee = bool(r.fee_schedule_id or r.office_default or r.office_ucr)
        if can_fee:
            has_fee_source += 1
        if r.home_office_id:
            has_office += 1
        if r.active_slots:
            insured += 1
            if r.coverage_rules:
                insured_with_rules += 1
        if not can_fee or not r.home_office_id or (r.active_slots and not r.coverage_rules):
            reasons = []
            if not r.home_office_id:
                reasons.append("no_home_office")
            if not can_fee:
                reasons.append("no_fee_source (no patient list / office default / office UCR)")
            if r.active_slots and not r.coverage_rules:
                reasons.append("insured_but_no_coverage_rules")
            missing_rows.append({"patient_id": r.id, "home_office_id": r.home_office_id or "",
                                 "fee_schedule_id": r.fee_schedule_id or "",
                                 "active_slots": r.active_slots, "reasons": "; ".join(reasons)})

    if csv_path and missing_rows:
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            w = _csv.DictWriter(fh, fieldnames=list(missing_rows[0].keys()))
            w.writeheader()
            w.writerows(missing_rows)

    return {"patients_with_charges": total, "have_a_fee_source": has_fee_source,
            "have_home_office": has_office, "insured": insured,
            "insured_with_coverage_rules": insured_with_rules,
            "missing_a_piece": len(missing_rows), "csv": csv_path if missing_rows else None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="pricing_unpriceable_patients.csv",
                        help="where to write the per-patient gaps CSV")
    args = parser.parse_args()

    root = _source_root()
    print(f"Denticon export: {root}\n")
    print("REPORT 1 - PRICING DATA COMPLETENESS (folder vs DB)\n")
    # Folder scans first, with NO DB connection open (they take minutes; an idle
    # connection held across them drops with 'SSL connection closed').
    f = folder_metrics(root)
    db = SessionLocal()
    try:
        rows = build_report(db, f)
        print(f"  {'pricing input':44s} {'folder':>10s} {'db':>10s} {'gap':>10s}  note")
        for r in rows:
            folder = "n/a" if r["folder"] < 0 else f"{r['folder']:,}"
            gap = "" if r["folder"] < 0 else f"{r['gap']:,}"
            print(f"  {r['input']:44s} {folder:>10s} {r['db']:>10,d} {gap:>10s}  {r['note']}")

        print("\nPER-PATIENT PRICEABILITY (patients with at least one charge)\n")
        p = priceability(db, args.csv)
        for k, v in p.items():
            print(f"  {k:32s}: {v}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
