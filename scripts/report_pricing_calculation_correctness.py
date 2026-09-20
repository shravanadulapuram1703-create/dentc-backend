"""Report 2 — pricing calculation correctness on the legacy ledger (full dataset).

For every non-void charge it asks: does the ingested fee-schedule data reproduce
the fee actually posted, using the schedule Denticon recorded for that charge
(``procedure_fee_provenance.fee_schedule_id`` = ``LEDGERINSD.FEEID``)? It looks up
that schedule's entry for the code, in force on the charge's date of service, and
compares its ``patient_fee`` to the posted ``fee``. Every charge lands in one
bucket:

* ``match``              — the schedule's fee equals the posted fee (correct)
* ``mismatch``          — data present but the fee differs (a real discrepancy)
* ``posted_zero``       — the charge posted at $0 (bundled / written-off)
* ``entry_missing``     — the recorded schedule has no entry for that code/date
                          (an INGESTION gap — the price row was not loaded)
* ``schedule_unmapped`` — the recorded FEEID maps to no fee_schedule
* ``feeid_zero``        — Denticon recorded no schedule (FEEID 0/blank)
* ``no_provenance``     — no LEDGERINSD row loaded for the charge

This is the schedule the resolver *should* pick (v2's precedence-card fidelity to
that choice is measured separately by ``validate_pricing_against_history.py
--against provenance``); together they answer "is the legacy fee calculation
correct, and where does it break?" at 100 % coverage.

Read-only. Writes a per-patient summary + a CSV of charges that do not reproduce.

Usage
-----
    python -m scripts.report_pricing_calculation_correctness
    python -m scripts.report_pricing_calculation_correctness --year 2025 --csv out.csv
"""

from __future__ import annotations

import argparse
import csv as _csv
from collections import Counter, defaultdict
from decimal import Decimal

from sqlalchemy import text

from app.db.session import SessionLocal

_CENTS = Decimal("0.01")


def _money(v):  # noqa: ANN001, ANN202
    return None if v is None else Decimal(str(v)).quantize(_CENTS)


_SQL = """
SELECT pp.id, pp.patient_id, pp.procedure_code, pp.fee,
       pfp.procedure_id IS NOT NULL AS has_prov,
       pfp.fee_schedule_legacy_id AS feeid,
       pfp.fee_schedule_id AS sched_id,
       e.patient_fee AS sched_fee
FROM patient_procedures pp
LEFT JOIN procedure_fee_provenance pfp ON pfp.procedure_id = pp.id
LEFT JOIN LATERAL (
    SELECT fe.patient_fee
    FROM fee_schedule_entries fe
    WHERE fe.fee_schedule_id = pfp.fee_schedule_id
      AND fe.procedure_code = pp.procedure_code
      AND fe.effective_date <= pp.date_of_service
    ORDER BY fe.effective_date DESC
    LIMIT 1
) e ON true
WHERE pp.is_void = false
{year_clause}
"""


def _classify(r) -> str:  # noqa: ANN001
    if _money(r.fee) == Decimal("0"):
        return "posted_zero"
    if not r.has_prov:
        return "no_provenance"
    if not r.feeid or r.feeid == "0":
        return "feeid_zero"
    if r.sched_id is None:
        return "schedule_unmapped"
    if r.sched_fee is None:
        return "entry_missing"
    return "match" if _money(r.sched_fee) == _money(r.fee) else "mismatch"


def run(db, *, year: int | None, csv_path: str | None) -> int:  # noqa: ANN001
    year_clause = ""
    params: dict = {}
    if year is not None:
        year_clause = "AND pp.date_of_service >= :start AND pp.date_of_service < :end"
        params = {"start": f"{year}-01-01", "end": f"{year + 1}-01-01"}
    sql = _SQL.format(year_clause=year_clause)

    buckets: Counter = Counter()
    # per patient: [total, reproduced(match)]
    per_patient: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    csv_rows: list[dict] = []
    stmt = text(sql).execution_options(stream_results=True, yield_per=20000)
    result = db.execute(stmt, params)

    total = 0
    for r in result:
        total += 1
        b = _classify(r)
        buckets[b] += 1
        pp = per_patient[r.patient_id]
        pp[0] += 1
        if b == "match":
            pp[1] += 1
        elif b in ("mismatch", "entry_missing", "schedule_unmapped") and len(csv_rows) < 100000:
            csv_rows.append({
                "procedure_id": r.id, "patient_id": r.patient_id,
                "procedure_code": r.procedure_code, "posted_fee": r.fee,
                "recorded_feeid": r.feeid or "", "recorded_schedule_id": r.sched_id or "",
                "schedule_fee": r.sched_fee if r.sched_fee is not None else "",
                "bucket": b,
            })

    _report(total, buckets, per_patient, year)
    if csv_path and csv_rows:
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            w = _csv.DictWriter(fh, fieldnames=list(csv_rows[0].keys()))
            w.writeheader()
            w.writerows(csv_rows)
        print(f"\nwrote {len(csv_rows)} non-reproducing charges to {csv_path}"
              + (" (capped at 100k)" if len(csv_rows) >= 100000 else ""))
    return 0


def _report(total, buckets, per_patient, year) -> None:  # noqa: ANN001
    print(f"REPORT 2 - PRICING CALCULATION CORRECTNESS (legacy ledger)"
          f"  scope={'all years' if year is None else year}\n")
    print(f"  non-void charges: {total:,}\n")
    print(f"  {'bucket':20s} {'count':>12s} {'share':>8s}")
    order = ["match", "mismatch", "posted_zero", "entry_missing",
             "schedule_unmapped", "feeid_zero", "no_provenance"]
    for b in order:
        n = buckets.get(b, 0)
        pct = f"{100.0 * n / total:5.1f}%" if total else "  n/a"
        print(f"  {b:20s} {n:12,d} {pct:>8s}")

    priced = sum(buckets.get(b, 0) for b in ("match", "mismatch"))
    print("\n  -- of charges with a resolvable recorded schedule + entry --")
    print(f"  reproduced (match)   : {buckets.get('match', 0):,} / {priced:,} "
          f"({(100.0 * buckets.get('match', 0) / priced):.1f}%)" if priced else "  n/a")

    # per-patient rollup
    n_patients = len(per_patient)
    fully = sum(1 for t, m in per_patient.values() if t == m)
    none = sum(1 for t, m in per_patient.values() if m == 0)
    partial = n_patients - fully - none
    print("\n  -- per patient (patients with >=1 charge) --")
    print(f"  patients                : {n_patients:,}")
    print(f"  every charge reproduced : {fully:,}  ({(100.0*fully/n_patients):.1f}%)")
    print(f"  some charges reproduced : {partial:,}")
    print(f"  none reproduced         : {none:,}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=None, help="limit to one year (default: all)")
    parser.add_argument("--csv", default="pricing_nonreproducing_charges.csv")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        return run(db, year=args.year, csv_path=args.csv)
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
