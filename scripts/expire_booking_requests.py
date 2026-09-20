"""Flip pending AppointNow requests whose slot has passed to ``expired`` (AN-25).

Run it every 5–15 minutes::

    python -m scripts.expire_booking_requests            # every active office
    python -m scripts.expire_booking_requests --tenant 3 # one tenant

The same sweep runs lazily whenever a staff user lists the inbox **and** on
every public availability computation, and a request's slot *hold* is bounded by
``APPOINTNOW_HOLD_TTL_MINUTES`` regardless — so public availability was already
truthful. What the cron adds is the **status** flip (inbox tab counts, the
``expired`` push event) without waiting for someone to open the inbox.
"""

from __future__ import annotations

import argparse
import json

from app.db.session import SessionLocal
from app.services import appointnow_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Expire stale AppointNow booking requests (AN-25)")
    parser.add_argument("--tenant", type=int, default=None, help="Restrict to one tenant id")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        summary = appointnow_service.expire_all(db, tenant_id=args.tenant)
    finally:
        db.close()
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
