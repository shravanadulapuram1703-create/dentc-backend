"""Reconstruct the office → fee-schedule linkage from the charges it produced
(FEE-2).

Why this exists
---------------
The migrated charges show each office charging from its own schedule::

    posted charge                             entry that produced it
    office 14  D0120  fee 44.00               fs 24 patient_fee 44.00
    office 4   D0120  fee 47.00               fs 25 patient_fee 47.00
    office 3   D0120  fee 25.41               fs 28 patient_fee 25.41

**None of that is represented.** Those offices have no
``default_fee_schedule_id`` and there are no office-scoped
``fee_schedule_assignments`` rows — tenant-wide there are 9 assignments, 8 of
them with every key null. So two conflicting practice-wide defaults (fs 26 at
28.00 and fs 4 at 145.00 for ``D0120``) are all most patients resolve to, and a
charge posted at an office is priced with another office's fee.

The linkage was never exported, but it is **recoverable from the evidence**: a
schedule that priced an office's charges will match those charges
column-for-column. This script scores every active schedule against each
office's own posting history — how many charges have a ``(procedure_code,
fee)`` pair that exactly equals one of the schedule's ``patient_fee`` entries —
and proposes the best-scoring schedule as that office's default. The same pass
scores ``ucr_fee`` against the schedules to propose
``default_ucr_fee_schedule_id``.

Why it is a proposal and not an assertion
-----------------------------------------
Two schedules can share a fee for a code, and an office that only ever posted a
handful of codes has thin evidence. So:

* nothing is written without ``--apply``;
* a winner must clear ``--min-share`` (default 0.60 — 60 % of the office's
  matchable charges) *and* ``--min-charges`` (default 25), otherwise the office
  is reported as **inconclusive** and left alone. Guessing here would be worse
  than the current NULL: a wrong default silently mis-prices every future
  charge at that office, where a NULL at least falls through to the code
  default and is visibly $0.
* an office that already has a default is skipped unless ``--overwrite`` —
  a value a human set outranks one inferred from history.
* the runner-up and its share are always printed, so a close call is visible
  rather than buried.

Usage
-----
    python -m scripts.backfill_office_fee_schedules                 # report only
    python -m scripts.backfill_office_fee_schedules --apply
    python -m scripts.backfill_office_fee_schedules --apply --overwrite
    python -m scripts.backfill_office_fee_schedules --office-id 4 --min-share 0.4
"""

from __future__ import annotations

import argparse

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal

# One pass per fee column. ``charges`` is the distinct (office, code, fee) set
# with a count, so the join runs against ~thousands of rows instead of 1.37M.
_SCORE_SQL = """
WITH charges AS (
    SELECT office_id, procedure_code, {fee_col} AS fee, COUNT(*) AS n
      FROM patient_procedures
     WHERE {fee_col} IS NOT NULL
       AND {fee_col} > 0
       AND COALESCE(is_archived, false) = false
       AND office_id IS NOT NULL
       {office_filter}
     GROUP BY 1, 2, 3
),
totals AS (
    SELECT office_id, SUM(n) AS total FROM charges GROUP BY 1
),
scored AS (
    SELECT c.office_id,
           e.fee_schedule_id,
           SUM(c.n) AS matched
      FROM charges c
      JOIN fee_schedule_entries e
        ON e.procedure_code = c.procedure_code
       AND e.patient_fee = c.fee
      JOIN fee_schedules s
        ON s.id = e.fee_schedule_id
       AND s.is_active
     GROUP BY 1, 2
)
SELECT s.office_id, s.fee_schedule_id, f.name, s.matched, t.total
  FROM scored s
  JOIN totals t ON t.office_id = s.office_id
  JOIN fee_schedules f ON f.id = s.fee_schedule_id
 ORDER BY s.office_id, s.matched DESC, s.fee_schedule_id
"""


def _score(session: Session, fee_col: str, office_id: int | None) -> dict[int, list[tuple]]:
    """``{office_id: [(schedule_id, name, matched, total), …]}`` best first."""
    sql = _SCORE_SQL.format(
        fee_col=fee_col,
        office_filter="AND office_id = :office_id" if office_id else "",
    )
    params = {"office_id": office_id} if office_id else {}
    out: dict[int, list[tuple]] = {}
    for oid, sched_id, name, matched, total in session.execute(text(sql), params):
        out.setdefault(oid, []).append((sched_id, name, int(matched), int(total)))
    return out


def _pick(
    ranked: list[tuple], *, min_share: float, min_charges: int
) -> tuple[tuple | None, str]:
    """The winner, or ``(None, reason)`` when the evidence is too thin."""
    if not ranked:
        return None, "no charge history matches any active schedule"
    best = ranked[0]
    _sid, _name, matched, total = best
    if total < min_charges:
        return None, f"only {total} matchable charges (< {min_charges})"
    share = matched / total
    if share < min_share:
        return None, f"best schedule explains {share:.0%} of charges (< {min_share:.0%})"
    return best, ""


def run(
    session: Session,
    *,
    apply: bool,
    overwrite: bool,
    office_id: int | None,
    min_share: float,
    min_charges: int,
    top: int,
) -> None:
    plans = (
        ("default_fee_schedule_id", "fee", "contracted"),
        ("default_ucr_fee_schedule_id", "ucr_fee", "UCR"),
    )

    for column, fee_col, label in plans:
        print(f"\n=== {label} schedule -> offices.{column} ===")
        scores = _score(session, fee_col, office_id)
        if not scores:
            print("  no evidence found (no charges carry this fee column)")
            continue

        current = dict(
            session.execute(
                text(f"SELECT id, {column} FROM offices")
            ).all()
        )

        set_count = 0
        for oid in sorted(scores):
            ranked = scores[oid]
            winner, reason = _pick(ranked, min_share=min_share, min_charges=min_charges)
            runner = ranked[1] if len(ranked) > 1 else None
            runner_txt = (
                f"  runner-up fs {runner[0]} ({runner[2]}/{runner[3]} = {runner[2]/runner[3]:.0%})"
                if runner else "  runner-up none"
            )

            if winner is None:
                print(f"  office {oid:>3}: inconclusive — {reason}")
                # Print the evidence anyway: an office that buys from several
                # plan schedules will never clear the bar, but the ranking is
                # still the answer to "which schedule priced these charges".
                for sid, name, matched, total in ranked[:top]:
                    print(f"      fs {sid:>3} {name[:38]:<38} {matched}/{total} = {matched/total:.0%}")
                continue

            sid, name, matched, total = winner
            share = matched / total
            existing = current.get(oid)
            if existing == sid:
                print(f"  office {oid:>3}: already fs {sid} ({share:.0%}) — unchanged")
                continue
            if existing and not overwrite:
                print(
                    f"  office {oid:>3}: has fs {existing}, history says fs {sid} "
                    f"'{name}' ({share:.0%}) — left alone (no --overwrite)"
                )
                continue

            verb = "set" if apply else "would set"
            print(
                f"  office {oid:>3}: {verb} fs {sid} '{name}' "
                f"— {matched}/{total} charges ({share:.0%})\n{runner_txt}"
            )
            if apply:
                session.execute(
                    text(f"UPDATE offices SET {column} = :sid WHERE id = :oid"),
                    {"sid": sid, "oid": oid},
                )
            set_count += 1

        if apply:
            session.commit()
        print(f"  -> {set_count} office(s) {'updated' if apply else 'would be updated'}")

    if not apply:
        print("\nDry run — nothing written. Re-run with --apply.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the changes")
    parser.add_argument("--overwrite", action="store_true",
                        help="also replace a default an office already carries")
    parser.add_argument("--office-id", type=int, help="restrict to one office")
    parser.add_argument("--min-share", type=float, default=0.60,
                        help="minimum share of charges the winning schedule must explain")
    parser.add_argument("--min-charges", type=int, default=25,
                        help="minimum matchable charges before a winner is accepted")
    parser.add_argument("--top", type=int, default=3,
                        help="how many candidate schedules to list for an inconclusive office")
    args = parser.parse_args()

    with SessionLocal() as session:
        run(
            session,
            apply=args.apply,
            overwrite=args.overwrite,
            office_id=args.office_id,
            min_share=args.min_share,
            min_charges=args.min_charges,
            top=args.top,
        )


if __name__ == "__main__":
    main()
