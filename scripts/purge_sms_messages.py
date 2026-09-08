"""Enforce SMS body retention (SMS-10).

Message bodies are PHI-adjacent. This blanks ``sent_text`` / ``reply_text`` on
rows older than the retention window and keeps the row itself (delivery
metadata, timestamps, who sent it, the Twilio sid) so the ledger of *that a text
was sent* survives. Dry-run by default::

    python -m scripts.purge_sms_messages                 # report, using SMS_RETENTION_DAYS
    python -m scripts.purge_sms_messages --days 730      # override the window
    python -m scripts.purge_sms_messages --apply         # actually blank the bodies

Twilio retains its own message logs independently — decide separately whether
to delete there (Console → Messaging → Logs, or the REST DELETE per message).
"""

from __future__ import annotations

import argparse
import json

from app.db.session import SessionLocal
from app.services import sms_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Blank SMS bodies past the retention window (SMS-10)")
    parser.add_argument("--days", type=int, default=None, help="Retention in days (default SMS_RETENTION_DAYS)")
    parser.add_argument("--apply", action="store_true", help="Write changes (default is a dry run)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = sms_service.purge_expired(db, days=args.days, dry_run=not args.apply)
    finally:
        db.close()
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
