"""Load per-charge pricing provenance from ``LEDGERINSD/*.txt`` (pricing R1
section 8 — the reference the parity script's ``--against provenance`` needs).

The Denticon migration's ``s32`` read only the 12k-row ``LedgerInsDetail_Archive``
into ``ledger_insurance_details`` (the remittance table); the full 1.45M-row
``LEDGERINSD`` export — which carries, per charge, the **``FEEID``** (the fee
schedule Denticon actually priced that charge with), the effective date and the
per-tier estimates — was never loaded. This fills ``procedure_fee_provenance``,
whose one load-bearing column is ``fee_schedule_id``: it lets the parity script
ask the definitive question, *does the precedence card pick the same schedule
Denticon used on this charge?* (``PRIMCONTRACTEDAMT`` is blank on almost every
row, so the amount is not the useful signal — the schedule is.)

Link: ``LEDGERINSD.LEDGERID == patient_procedures.legacy_id`` (the charge id is
``PROC-{LEDGERID}``). ``FEEID`` is a ``fee_schedules.legacy_id``.

Scoped by ``--year`` (default 2025 — the validation set, ~63k charges) so the load
is bounded and fast; ``--all-years`` loads the lot. Dry-run by default; ``--apply``
writes. Idempotent (``ON CONFLICT (procedure_id) DO NOTHING``).

Usage
-----
    python -m scripts.load_procedure_fee_provenance                 # dry run, 2025
    python -m scripts.load_procedure_fee_provenance --apply
    python -m scripts.load_procedure_fee_provenance --apply --all-years
"""

from __future__ import annotations

import argparse
from datetime import datetime

from psycopg2.extras import execute_values
from sqlalchemy import text

# Reuse the backfill's export reader + source-root + parsers (same scripts/ dir).
from scripts.backfill_pricing_hierarchy import _money, _read_many, _s, _source_root
from app.db.session import SessionLocal

_INSERT_COLS = (
    "procedure_id", "legacy_ledger_id", "fee_schedule_legacy_id", "fee_schedule_id",
    "fee_effective_date", "contracted_amount", "prim_ins_plan_legacy_id",
    "prim_estimated", "prim_deductible", "sec_estimated", "sec_deductible",
    "ter_estimated", "ter_deductible", "quad_estimated", "quad_deductible",
)


def _eff_date(raw):  # noqa: ANN001, ANN202
    text_val = _s(raw)
    if not text_val:
        return None
    try:
        return datetime.strptime(text_val[:10], "%m/%d/%Y").date()
    except ValueError:
        return None


def _charge_map(db, *, year: int | None, tenant_id: int | None) -> dict:  # noqa: ANN001
    """{LEDGERID -> (procedure_id, tenant_id)} for the target charges."""
    sql = (
        "SELECT pp.legacy_id, pp.id, p.tenant_id "
        "FROM patient_procedures pp JOIN patients p ON p.id = pp.patient_id "
        "WHERE pp.legacy_id IS NOT NULL "
    )
    params: dict = {}
    if year is not None:
        sql += "AND pp.date_of_service >= :start AND pp.date_of_service < :end "
        params["start"], params["end"] = f"{year}-01-01", f"{year + 1}-01-01"
    if tenant_id is not None:
        sql += "AND p.tenant_id = :tenant "
        params["tenant"] = tenant_id
    return {r.legacy_id: (r.id, r.tenant_id) for r in db.execute(text(sql), params)}


def _schedule_map(db) -> dict:  # noqa: ANN001
    return {
        (r.tenant_id, _s(r.legacy_id)): r.id
        for r in db.execute(
            text("SELECT id, tenant_id, legacy_id FROM fee_schedules WHERE legacy_id IS NOT NULL")
        )
    }


def load(*, year: int | None, tenant_id: int | None, apply: bool) -> int:
    root = _source_root()
    # The LEDGERINSD scan takes minutes; do not hold a DB connection across it
    # (the idle SSL connection drops). Read the maps, release the connection,
    # scan the files, then open a fresh session only for the write.
    db = SessionLocal()
    try:
        charges = _charge_map(db, year=year, tenant_id=tenant_id)
        schedules = _schedule_map(db)
    finally:
        db.close()
    print(f"scope: {'all years' if year is None else year}  tenant={tenant_id or 'all'}")
    print(f"target charges: {len(charges)}  schedules mapped: {len(schedules)}")

    # Stream the scan in bounded batches: at ~1.37M charges the whole set will not
    # sit in memory, and flushing every batch keeps the write connection active so
    # the idle SSL connection does not drop across a multi-minute scan. A charge is
    # effectively 1:1 with a LEDGERINSD row (verified on 2025), so per-batch dedup
    # + ON CONFLICT DO NOTHING is enough; the rare cross-batch dupe keeps the first.
    flush_every = 50_000
    batch: dict[str, dict] = {}
    scanned = matched = written = with_schedule = 0
    unresolved: set[str] = set()

    def _flush() -> None:
        nonlocal written, with_schedule
        if not batch:
            return
        values = list(batch.values())
        with_schedule += sum(1 for r in values if r["fee_schedule_id"] is not None)
        written += len(values)
        if apply:
            _flush_batch(values)
        batch.clear()

    for src in _read_many(root, "LEDGERINSD"):
        scanned += 1
        ledger_id = _s(src.get("LEDGERID"))
        hit = charges.get(ledger_id)
        if hit is None:
            continue
        matched += 1
        procedure_id, tenant = hit
        feeid = _s(src.get("FEEID"))
        existing = batch.get(procedure_id)
        if existing is not None and not feeid and existing["fee_schedule_legacy_id"]:
            continue  # keep the earlier row that at least named a schedule
        sched_id = schedules.get((tenant, feeid)) if feeid else None
        if feeid and sched_id is None:
            unresolved.add(feeid)
        batch[procedure_id] = {
            "procedure_id": procedure_id,
            "legacy_ledger_id": ledger_id,
            "fee_schedule_legacy_id": feeid or None,
            "fee_schedule_id": sched_id,
            "fee_effective_date": _eff_date(src.get("EFFECTIVEDATE")),
            "contracted_amount": _money(src.get("PRIMCONTRACTEDAMT")),
            "prim_ins_plan_legacy_id": _s(src.get("PRIMINSPLANID")) or None,
            "prim_estimated": _money(src.get("PRIMEST")),
            "prim_deductible": _money(src.get("PRIMDED")),
            "sec_estimated": _money(src.get("SECEST")),
            "sec_deductible": _money(src.get("SECDED")),
            "ter_estimated": _money(src.get("TEREST")),
            "ter_deductible": _money(src.get("TERDED")),
            "quad_estimated": _money(src.get("QUADEST")),
            "quad_deductible": _money(src.get("QUADDED")),
        }
        if len(batch) >= flush_every:
            _flush()
    _flush()

    print(f"scanned LEDGERINSD rows: {scanned}  matched to a target charge: {matched}")
    print(f"provenance rows {'written' if apply else 'to write'}: {written}  "
          f"(with a resolved schedule: {with_schedule})")
    if unresolved:
        u = sorted(unresolved)
        print(f"FEEIDs that map to no schedule: {u[:20]}" + (" ..." if len(u) > 20 else ""))

    if not apply:
        print("\ndry run — nothing written; re-run with --apply")
        return 0

    db = SessionLocal()
    try:
        total = db.execute(text("SELECT count(*) FROM procedure_fee_provenance")).scalar()
    finally:
        db.close()
    print(f"\nCOMMITTED — procedure_fee_provenance now holds {total} rows")
    return 0


def _flush_batch(rows: list[dict]) -> None:
    """Insert one batch on its own short-lived session (kept brief so the SSL
    connection never idles long enough to drop during the file scan)."""
    if not rows:
        return
    db = SessionLocal()
    try:
        _bulk_insert(db, rows)
        db.commit()
    finally:
        db.close()


def _bulk_insert(db, rows: list[dict]) -> None:  # noqa: ANN001
    """Fast batched INSERT via psycopg2 execute_values (executemany would be one
    round trip per row). Runs on the session's own connection, inside its txn."""
    if not rows:
        return
    raw = db.connection().connection  # the psycopg2 connection under the session
    cur = raw.cursor()
    cols = ", ".join(_INSERT_COLS)
    sql = (
        f"INSERT INTO procedure_fee_provenance ({cols}) VALUES %s "
        "ON CONFLICT (procedure_id) DO NOTHING"
    )
    values = [tuple(r[c] for c in _INSERT_COLS) for r in rows]
    execute_values(cur, sql, values, page_size=1000)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write (default: report only)")
    parser.add_argument("--year", type=int, default=2025, help="charge year to load (default 2025)")
    parser.add_argument("--all-years", action="store_true", help="load every year (~1.45M rows)")
    parser.add_argument("--tenant", type=int, default=None)
    args = parser.parse_args()
    return load(year=None if args.all_years else args.year,
                tenant_id=args.tenant, apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
