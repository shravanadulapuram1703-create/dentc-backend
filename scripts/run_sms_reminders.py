"""Send every due automated appointment reminder (SMS-9) — the cron entry point.

Run it every 10–15 minutes::

    python -m scripts.run_sms_reminders            # every tenant with reminders on
    python -m scripts.run_sms_reminders --tenant 3 # one tenant
    python -m scripts.run_sms_reminders --dry-run  # report only, send nothing

Idempotent: a reminder is keyed by ``(appointment_id, 'appointment_reminder',
lead_hours)`` — both checked before sending and enforced by the deterministic
``client_id`` — so overlapping runs never double-text. A reminder whose send-by
moment is older than ``SMS_REMINDER_CATCHUP_HOURS`` is skipped rather than sent
late after an outage. The same logic is reachable per tenant at
``POST /api/v1/sms/reminders/run`` (admin) for a manual kick.
"""

from __future__ import annotations

import argparse
import json

from app.db.session import SessionLocal
from app.services import sms_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Send due SMS appointment reminders (SMS-9)")
    parser.add_argument("--tenant", type=int, default=None, help="Restrict to one tenant id")
    parser.add_argument("--dry-run", action="store_true", help="Report what would be sent")
    parser.add_argument("--verbose", action="store_true", help="Print per-appointment items")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        summary = sms_service.run_reminders(db, tenant_id=args.tenant, dry_run=args.dry_run)
    finally:
        db.close()
    if not args.verbose:
        summary = {k: v for k, v in summary.items() if k != "items"}
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
