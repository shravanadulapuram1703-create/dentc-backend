"""Re-price historical charges with the v2 engine and compare to what was posted
(pricing R1 step 6 — the R2 sign-off signal).

What it does
------------
For a sample of non-void charges in a year (default 2025), it re-prices each one
through ``pricing_service.resolve_procedure_fee`` **with PRICING_ENGINE_V2 on**, at
the charge's own ``date_of_service`` and with its patient / office / provider, and
compares the resolved fee to the fee actually stored on the charge.

Why compare to the stored fee, not ``procedure_fee_provenance``
---------------------------------------------------------------
The plan's ideal reference is ``procedure_fee_provenance`` (the migrated
``LEDGERINSD.FEEID`` snapshot). That table is **empty** on the dev DB — the
provenance backfill (section 8) has not been run — so the ground truth available
in-app is the charge's own stored ``fee``, which *is* the historical posted amount.
When the provenance table is later loaded, ``--against provenance`` switches the
comparison.

Reachable vs unreachable
------------------------
A charge is **reachable** when v2 returns a real fee (some tier priced it) and
**unreachable** when it falls through to ``unpriced``. On a tenant where the office
UCR / default and carrier bindings have not yet been backfilled (they move live
prices, so R1 holds them), the patient's own list is the main tier that fires — so
the reachable-subset match rate measures how well the patient list alone reproduces
history, and the unreachable count plus the "mismatch, patient has a carrier"
bucket size the work the held backfill sections would do. The §5 target
(>= 97 % on the reachable subset) is expected only once those sections are applied.

Read-only. Nothing is written; the session is rolled back.

Usage
-----
    python -m scripts.validate_pricing_against_history                 # 2025, 2000-charge sample
    python -m scripts.validate_pricing_against_history --sample 10000
    python -m scripts.validate_pricing_against_history --all           # every charge in the year (slow)
    python -m scripts.validate_pricing_against_history --year 2024 --tenant 3
    python -m scripts.validate_pricing_against_history --against provenance
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict
from decimal import Decimal

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - not all streams support it
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services import pricing_service  # noqa: E402
from sqlalchemy import text  # noqa: E402

_CENTS = Decimal("0.01")


def _money(value) -> Decimal | None:  # noqa: ANN001
    if value is None:
        return None
    return Decimal(str(value)).quantize(_CENTS)


def _pct(part: int, whole: int) -> str:
    return f"{(100.0 * part / whole):5.1f}%" if whole else "  n/a"


def _fetch(db, *, year: int | None, tenant_id: int | None, sample: int | None):  # noqa: ANN001
    sql = (
        "SELECT pp.id, pp.patient_id, pp.office_id, pp.provider_id, pp.procedure_code, "
        "       pp.date_of_service, pp.fee, p.tenant_id "
        "FROM patient_procedures pp JOIN patients p ON p.id = pp.patient_id "
        "WHERE pp.is_void = false AND pp.fee IS NOT NULL "
    )
    params: dict = {}
    if year is not None:
        sql += "  AND pp.date_of_service >= :start AND pp.date_of_service < :end "
        params["start"], params["end"] = f"{year}-01-01", f"{year + 1}-01-01"
    if tenant_id is not None:
        sql += "  AND p.tenant_id = :tenant "
        params["tenant"] = tenant_id
    if sample is not None:
        # A reproducible spread across the whole year (ordering by id or date would
        # sample one week of it). ``patient_procedures.id`` is a string, so md5 of
        # it is a stable pseudo-random key.
        sql += "ORDER BY md5(pp.id) LIMIT :lim "
        params["lim"] = sample
    else:
        sql += "ORDER BY pp.id "
    return db.execute(text(sql), params).mappings().all()


def _provenance_map(db, procedure_ids: list[str]) -> dict:  # noqa: ANN001
    """{procedure_id -> {fee_schedule_id, contracted_amount}} for the sampled
    charges — the schedule Denticon actually priced each with (``FEEID``)."""
    out: dict[str, dict] = {}
    for start in range(0, len(procedure_ids), 5000):
        chunk = procedure_ids[start:start + 5000]
        for r in db.execute(
            text("SELECT procedure_id, fee_schedule_id, contracted_amount "
                 "FROM procedure_fee_provenance WHERE procedure_id = ANY(:ids)"),
            {"ids": chunk},
        ):
            out[r.procedure_id] = {"fee_schedule_id": r.fee_schedule_id,
                                   "contracted_amount": r.contracted_amount}
    return out


def _schedule_names(db) -> dict:  # noqa: ANN001
    return {r.id: r.name for r in db.execute(text("SELECT id, name FROM fee_schedules"))}


def validate(db, *, year: int, tenant_id: int | None, sample: int | None, against: str) -> int:  # noqa: ANN001
    # The whole point of the run is to exercise v2; force it on regardless of .env.
    settings.PRICING_ENGINE_V2 = True

    rows = _fetch(db, year=year, tenant_id=tenant_id, sample=sample)
    total = len(rows)
    print(f"year={year or 'all'}  tenant={tenant_id or 'all'}  charges sampled={total}  compare against={against}")
    if not total:
        print("no charges matched — nothing to validate")
        return 0

    provmap = _provenance_map(db, [r["id"] for r in rows]) if against == "provenance" else {}
    if against == "provenance":
        print(f"provenance rows for the sample: {len(provmap)}")

    reachable = defaultdict(lambda: [0, 0])   # fee_source -> [total, matched]  (stored_fee)
    unreachable = defaultdict(int)            # reason -> count
    sched = [0, 0]                            # [comparable, matched]           (provenance)
    diff_pattern: Counter = Counter()         # (v2_source, denticon_schedule) -> count
    no_provenance = 0                         # v2 priced it, no LEDGERINSD row
    prov_unmapped = 0                         # provenance FEEID maps to no schedule
    errors = 0
    posted_zero = 0                           # v2 priced it, but it posted at $0
    mismatch_examples: list[tuple] = []
    ctx_cache: dict[tuple, object] = {}
    names = _schedule_names(db) if against == "provenance" else {}

    for r in rows:
        try:
            key = (r["patient_id"], r["office_id"], r["provider_id"])
            ctx = ctx_cache.get(key)
            if ctx is None:
                ctx = pricing_service.build_context(
                    db, patient_id=r["patient_id"], office_id=r["office_id"],
                    provider_id=r["provider_id"], date_of_service=r["date_of_service"],
                )
                ctx_cache[key] = ctx
            quote = pricing_service.resolve_procedure_fee(
                db, r["tenant_id"], r["procedure_code"], ctx=ctx,
                date_of_service=r["date_of_service"],
            )
        except Exception as exc:  # noqa: BLE001 - a bad row must not stop the sweep
            errors += 1
            if len(mismatch_examples) < 25:
                mismatch_examples.append((r["procedure_code"], "ERROR", str(exc)[:40], ""))
            continue

        source = quote.get("fee_source") or "unpriced"
        if quote.get("is_unpriced") or source == "unpriced":
            unreachable[_unreachable_reason(ctx)] += 1
            continue

        if against == "provenance":
            # Definitive test: did the precedence card pick the *same schedule*
            # Denticon recorded on this charge (LEDGERINSD.FEEID)?
            prov = provmap.get(r["id"])
            if prov is None:
                no_provenance += 1
                continue
            denticon_schedule = prov["fee_schedule_id"]
            if denticon_schedule is None:
                prov_unmapped += 1
                continue
            sched[0] += 1
            if quote.get("fee_schedule_id") == denticon_schedule:
                sched[1] += 1
            else:
                diff_pattern[(source, names.get(denticon_schedule, str(denticon_schedule)))] += 1
                if len(mismatch_examples) < 25:
                    mismatch_examples.append((
                        r["procedure_code"], names.get(denticon_schedule, str(denticon_schedule))[:22],
                        source, str(quote.get("fee_schedule_id"))))
            continue

        # stored_fee: a charge posted at $0 (19 % of the migrated year — bundled /
        # written-off lines) is not a fair test of a *priced* fee, so it is
        # reported on its own rather than counted as a mismatch.
        reference = _money(r["fee"])
        if reference is None or reference == Decimal("0"):
            posted_zero += 1
            continue
        got = _money(quote.get("fee"))
        bucket = reachable[source]
        bucket[0] += 1
        if got == reference:
            bucket[1] += 1
        elif len(mismatch_examples) < 25:
            mismatch_examples.append((r["procedure_code"], str(reference), str(got), source))

    if against == "provenance":
        _report_provenance(total, unreachable, errors, no_provenance, prov_unmapped,
                           sched, diff_pattern, mismatch_examples)
    else:
        _report(total, reachable, unreachable, errors, posted_zero, mismatch_examples)
    return 0


def _unreachable_reason(ctx) -> str:  # noqa: ANN001
    """A cheap attribution for a charge v2 could not price: usually a binding the
    R1 backfill held (office pointers / carrier lists)."""
    if getattr(ctx, "carrier_id", None):
        return "no_carrier_binding (held backfill)"
    if not getattr(ctx, "patient_fee_schedule_id", None):
        return "patient_has_no_list"
    if not getattr(ctx, "office_id", None):
        return "no_office"
    return "code_missing_on_reachable_list"


def _report_provenance(total, unreachable, errors, no_provenance, prov_unmapped,  # noqa: ANN001
                       sched, diff_pattern, examples) -> None:
    unreach_total = sum(unreachable.values())
    comparable, matched = sched
    priced = comparable + prov_unmapped + no_provenance

    print("\n== outcome (schedule match vs Denticon's per-charge FEEID) ==")
    print(f"  priced by v2             : {priced:7d}  ({_pct(priced, total)})")
    print(f"    - schedule-comparable  : {comparable:7d}  (has a provenance FEEID -> schedule)")
    print(f"    - no provenance row    : {no_provenance:7d}")
    print(f"    - FEEID maps to no sched:{prov_unmapped:7d}")
    print(f"  unreachable (unpriced)   : {unreach_total:7d}  ({_pct(unreach_total, total)})")
    print(f"  errors                   : {errors:7d}")

    print("\n== SCHEDULE MATCH (did v2 pick the schedule Denticon used?) ==")
    print(f"  matched {matched} / {comparable}   ({_pct(matched, comparable)})")

    if diff_pattern:
        print("\n== when v2 differs: v2 tier  ->  Denticon's schedule (count) ==")
        for (source, dent), n in diff_pattern.most_common(15):
            print(f"  {source:22s} -> {dent[:34]:34s} {n:6d}")

    if examples:
        print("\n== sample divergences (code | denticon sched | v2 tier | v2 sched id) ==")
        for code, dent, source, v2sid in examples:
            print(f"  {code:8s} {dent:24s} {source:20s} {v2sid}")

    print("\nread-only: nothing was written")


def _report(total, reachable, unreachable, errors, posted_zero, examples) -> None:  # noqa: ANN001
    reach_total = sum(v[0] for v in reachable.values())
    reach_match = sum(v[1] for v in reachable.values())
    unreach_total = sum(unreachable.values())
    priced = reach_total + posted_zero

    print("\n== outcome ==")
    print(f"  priced by v2             : {priced:7d}  ({_pct(priced, total)})")
    print(f"    - comparable (ref > 0) : {reach_total:7d}")
    print(f"    - posted at $0         : {posted_zero:7d}  (excluded from match rate)")
    print(f"  unreachable (unpriced)   : {unreach_total:7d}  ({_pct(unreach_total, total)})")
    print(f"  errors                   : {errors:7d}")

    print("\n== reachable fee match, by tier ==")
    print(f"  {'fee_source':26s} {'priced':>8s} {'match':>8s} {'rate':>7s}")
    for source in sorted(reachable, key=lambda s: -reachable[s][0]):
        tot, match = reachable[source]
        print(f"  {source:26s} {tot:8d} {match:8d} {_pct(match, tot)}")
    print(f"  {'OVERALL':26s} {reach_total:8d} {reach_match:8d} {_pct(reach_match, reach_total)}")

    if unreachable:
        print("\n== unreachable, by likely cause ==")
        for reason in sorted(unreachable, key=lambda r: -unreachable[r]):
            print(f"  {reason:36s} {unreachable[reason]:7d}")

    if examples:
        print("\n== sample mismatches (code | reference | v2 | tier) ==")
        for code, ref, got, source in examples:
            print(f"  {code:8s} {ref:>10s} {got:>10s}  {source}")

    print("\nread-only: nothing was written")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--all-years", action="store_true", help="sample across every year")
    parser.add_argument("--tenant", type=int, default=None, help="limit to one tenant id")
    parser.add_argument("--sample", type=int, default=2000, help="max charges to price (default 2000)")
    parser.add_argument("--all", action="store_true", help="price every charge in the year (slow)")
    parser.add_argument("--against", choices=("stored_fee", "provenance"), default="stored_fee",
                        help="compare v2 to the charge's stored fee (default) or procedure_fee_provenance")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        return validate(
            db, year=None if args.all_years else args.year, tenant_id=args.tenant,
            sample=None if args.all else args.sample, against=args.against,
        )
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
