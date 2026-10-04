"""Move migrated time-clock rows from office wall clock to real UTC (TC-BE-9).

The Denticon export stored each punch as the office's *wall clock* with a ``Z``
suffix (``legacy_id 4341192``: ``2023-12-08T09:25:00Z`` = 9:25 AM at the
office), while DentC punches are true UTC. The migration marked every legacy row
``clock_basis='wall_clock'``; this script converts them with the office's
``offices.timezone`` (``09:25 America/New_York -> 14:25Z``) and marks them
``utc_converted`` so it is idempotent **and** revertible::

    python -m scripts.backfill_time_clock_utc                 # dry run (default)
    python -m scripts.backfill_time_clock_utc --apply
    python -m scripts.backfill_time_clock_utc --revert --apply

A row with no office (103 on the dev DB) uses the user's primary office, then
``--default-tz`` (America/New_York). ``total_hours`` is unchanged by
construction except across a DST switch inside the shift, where it is
recomputed from the converted pair (the wall-clock difference was off by an hour).

Coordinate with the frontend: rows are safe to render per ``clock_basis`` at
any time, so the FE can drop its ``LEGACY_WALL_CLOCK_ZONE`` branch as soon as it
reads ``clock_basis`` instead of ``legacy_id``. ``original_clock_in/out`` and the
edit log are deliberately untouched — this is a representation change, not an edit.
"""

from __future__ import annotations

import argparse
import json

from sqlalchemy import select

from app.core.datetimes import DEFAULT_TIMEZONE
from app.db.models import Office, TimeClockEntry, UserOffice
from app.db.session import SessionLocal
from app.services.time_clock_service import hours_between, utc_to_wall, wall_to_utc

BATCH = 2000


def _zones(db, tenant_id: int | None) -> tuple[dict[int, str], dict[int, int]]:  # noqa: ANN001
    stmt = select(Office.id, Office.timezone)
    if tenant_id is not None:
        stmt = stmt.where(Office.tenant_id == tenant_id)
    office_tz = {oid: tz or DEFAULT_TIMEZONE for oid, tz in db.execute(stmt).all()}
    primary = {
        uid: oid for uid, oid in db.execute(
            select(UserOffice.user_id, UserOffice.office_id).where(UserOffice.is_primary.is_(True))
        ).all()
    }
    return office_tz, primary


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert legacy wall-clock punches to UTC (TC-BE-9)")
    parser.add_argument("--apply", action="store_true", help="Write the changes (default: dry run)")
    parser.add_argument("--revert", action="store_true", help="utc_converted -> wall_clock")
    parser.add_argument("--tenant", type=int, default=None)
    parser.add_argument("--default-tz", default=DEFAULT_TIMEZONE)
    args = parser.parse_args()

    source_basis, target_basis = ("utc_converted", "wall_clock") if args.revert else ("wall_clock", "utc_converted")
    convert = utc_to_wall if args.revert else wall_to_utc

    db = SessionLocal()
    stats = {"mode": "revert" if args.revert else "convert", "applied": args.apply, "rows": 0,
             "by_zone": {}, "no_office_fallback": 0, "dst_hours_recomputed": 0, "sample": []}
    try:
        office_tz, primary = _zones(db, args.tenant)
        last_id = 0
        while True:
            stmt = (
                select(TimeClockEntry)
                .where(TimeClockEntry.clock_basis == source_basis, TimeClockEntry.id > last_id)
                .order_by(TimeClockEntry.id).limit(BATCH)
            )
            if args.tenant is not None:
                stmt = stmt.where(TimeClockEntry.tenant_id == args.tenant)
            rows = db.execute(stmt).scalars().all()
            if not rows:
                break
            for e in rows:
                last_id = e.id
                office_id = e.office_id if e.office_id is not None else primary.get(e.user_id)
                if e.office_id is None:
                    stats["no_office_fallback"] += 1
                tz = office_tz.get(office_id, args.default_tz) if office_id is not None else args.default_tz
                new_in, new_out = convert(e.clock_in, tz), convert(e.clock_out, tz)
                new_total = hours_between(new_in, new_out) if new_out is not None else e.total_hours
                if new_out is not None and e.total_hours is not None and new_total != e.total_hours:
                    stats["dst_hours_recomputed"] += 1
                if len(stats["sample"]) < 5:
                    stats["sample"].append({"id": e.id, "tz": tz, "clock_in": [str(e.clock_in), str(new_in)]})
                stats["by_zone"][tz] = stats["by_zone"].get(tz, 0) + 1
                stats["rows"] += 1
                if args.apply:
                    e.clock_in, e.clock_out, e.clock_basis = new_in, new_out, target_basis
                    if new_out is not None:
                        e.total_hours = new_total
            if args.apply:
                db.commit()
            else:
                db.rollback()
    finally:
        db.close()
    print(json.dumps(stats, indent=2, default=str))


if __name__ == "__main__":
    main()
