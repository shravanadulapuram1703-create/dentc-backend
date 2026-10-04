"""Flag / close time-clock shifts left open past the practice threshold (TC-BE-10).

Run it hourly::

    python -m scripts.auto_close_time_clock --dry-run     # report only
    python -m scripts.auto_close_time_clock               # every tenant
    python -m scripts.auto_close_time_clock --tenant 1

Per practice (``time_clock_settings``): ``flag`` (default) marks the row a
missing clock-out — 0 paid hours, never a guessed time; ``office_close`` closes
it at the office's scheduled end time that day (flagged ``auto_closed``) when
one exists; ``off`` skips the practice. The same rule runs lazily on the next
clock-in / clock-out of the affected user, so the cron only keeps the report
and the punch button honest between punches.
"""

from __future__ import annotations

import argparse
import json

from app.db.session import SessionLocal
from app.services import time_clock_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-close stale time-clock shifts (TC-BE-10)")
    parser.add_argument("--tenant", type=int, default=None, help="Restrict to one tenant id")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change; write nothing")
    parser.add_argument("--policy", choices=time_clock_service.AUTO_CLOSE_POLICIES, default=None,
                        help="Override every practice's policy for this run")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        summary = time_clock_service.auto_close_stale(
            db, tenant_id=args.tenant, dry_run=args.dry_run, force_policy=args.policy,
        )
    finally:
        db.close()
    summary["entry_ids"] = summary["entry_ids"][:50]
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
