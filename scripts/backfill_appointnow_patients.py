"""Link a patient to every AppointNow booking approved without one (AN-33).

Before AN-32, ``POST /appointnow/requests/{id}/approve`` with neither
``patient_id`` nor ``create_patient`` booked ``appointments.patient_id = NULL``
and kept the contact only in the appointment note. This finds those rows
(request **or** appointment unlinked) and repairs them through the same
``appointnow_service.link_patient`` the AN-30 endpoint uses::

    python -m scripts.backfill_appointnow_patients               # dry run: list only
    python -m scripts.backfill_appointnow_patients --apply       # register/match + link
    python -m scripts.backfill_appointnow_patients --apply --tenant 3

Per row, on ``--apply``:

- one side already has a patient → the other side is set to it (no new patient);
- else the registration identity rule decides: exactly one *strong* match (full
  name + DOB/phone/e-mail) is linked, none creates a patient from the contact,
  several are **skipped** and reported (``duplicate_patient``) for staff to pick
  in the inbox (``link-patient {patient_id}``).

Each row commits on its own, so one refusal never undoes the others.
"""

from __future__ import annotations

import argparse
import json
from types import SimpleNamespace

from sqlalchemy import or_, select

from app.core.exceptions import AppError
from app.db.models import Appointment, BookingRequest
from app.db.session import SessionLocal
from app.services import appointnow_service


def _candidates(db, tenant_id: int | None) -> list[tuple[BookingRequest, Appointment]]:
    stmt = (
        select(BookingRequest, Appointment)
        .join(Appointment, Appointment.id == BookingRequest.appointment_id)
        .where(
            BookingRequest.status == "approved",
            or_(BookingRequest.patient_id.is_(None), Appointment.patient_id.is_(None)),
        )
        .order_by(BookingRequest.id.asc())
    )
    if tenant_id is not None:
        stmt = stmt.where(BookingRequest.tenant_id == tenant_id)
    return list(db.execute(stmt).all())


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill patients on approved AppointNow bookings (AN-33)")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    parser.add_argument("--tenant", type=int, default=None, help="Restrict to one tenant id")
    args = parser.parse_args()

    db = SessionLocal()
    report: list[dict] = []
    try:
        rows = _candidates(db, args.tenant)
        targets = [
            {
                "request_id": req.id,
                "tenant_id": req.tenant_id,
                "office_id": req.office_id,
                "appointment_id": appt.id,
                "contact": " ".join(x for x in (req.first_name, req.last_name) if x),
                "date_of_birth": req.date_of_birth,
                "request_patient_id": req.patient_id,
                "appointment_patient_id": appt.patient_id,
            }
            for req, appt in rows
        ]
        if not args.apply:
            print(json.dumps({"dry_run": True, "count": len(targets), "rows": targets},
                             indent=2, default=str))
            return
        body = SimpleNamespace(patient_id=None, create_patient=True, force_create=False,
                               link_existing_match=True)
        for t in targets:
            try:
                req = appointnow_service.link_patient(
                    db, t["tenant_id"], t["request_id"], body, actor_id=None
                )
                report.append({**t, "result": "linked", "patient_id": req.patient_id})
            except AppError as exc:
                db.rollback()
                report.append({**t, "result": "skipped", "code": exc.code, "message": exc.message})
    finally:
        db.close()
    summary = {
        "count": len(report),
        "linked": sum(1 for r in report if r["result"] == "linked"),
        "skipped": sum(1 for r in report if r["result"] == "skipped"),
        "rows": report,
    }
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
