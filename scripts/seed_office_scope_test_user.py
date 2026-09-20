"""Seed a restricted test account for verifying office scoping end-to-end (§D).

The only dev account is a ``super_admin`` with zero ``user_offices`` — privileged
*and* ungated, so no OFF-SCOPE-1/2/6/11 refusal path is reachable with it. This
creates a **non-privileged** user that can actually be refused:

* a ``front_desk`` user assigned to a **subset** of the tenant's offices (the
  first two by default, ``--offices 1,4`` to choose), **without**
  ``office_scope_view_all_offices``;
* it also reports a patient whose ``home_office_id`` is an office the user is
  **not** assigned to (to exercise ``patient_not_in_office``) — creating a
  placeholder one only if none exists.

Idempotent. Default credentials ``frontdesk`` / ``frontdesk`` (override with
``--username`` / ``--password``).

    python -m scripts.seed_office_scope_test_user
    python -m scripts.seed_office_scope_test_user --tenant 1 --offices 1,4
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import Office, Patient, Tenant, User, UserOffice
from app.db.session import SessionLocal


def main() -> None:
    ap = argparse.ArgumentParser(description="Seed a restricted office-scope test user")
    ap.add_argument("--tenant", type=int, default=None, help="tenant id (default: first)")
    ap.add_argument("--offices", type=str, default=None,
                    help="comma-separated office ids to assign (default: first two of the tenant)")
    ap.add_argument("--username", default="frontdesk")
    ap.add_argument("--password", default="frontdesk")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        tenant_id = args.tenant
        if tenant_id is None:
            tenant_id = db.execute(select(Tenant.id).order_by(Tenant.id.asc())).scalars().first()
        if tenant_id is None:
            print("No tenant found — run scripts.seed first.")
            return

        office_ids = [o for o in db.execute(
            select(Office.id).where(Office.tenant_id == tenant_id, Office.is_active.is_(True))
            .order_by(Office.id.asc())
        ).scalars().all()]
        if len(office_ids) < 1:
            print(f"Tenant {tenant_id} has no active offices — seed offices first.")
            return

        if args.offices:
            assigned = [int(x) for x in args.offices.split(",") if x.strip()]
            assigned = [o for o in assigned if o in office_ids]
        else:
            assigned = office_ids[:2]
        if not assigned:
            print("No valid offices to assign.")
            return
        unassigned = [o for o in office_ids if o not in assigned]

        # The restricted user.
        user = db.execute(
            select(User).where(User.tenant_id == tenant_id, User.username == args.username)
        ).scalar_one_or_none()
        if user is None:
            user = User(
                tenant_id=tenant_id, username=args.username,
                email=f"{args.username}@dev.local",
                password_hash=hash_password(args.password),
                first_name="Front", last_name="Desk", role="front_desk", is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"Created user id={user.id} username={args.username} role=front_desk")
        else:
            user.password_hash = hash_password(args.password)  # reset so it is loggable
            user.role = "front_desk"
            db.commit()
            print(f"User already exists id={user.id} - password reset")

        # Its office assignments (idempotent, primary = the first).
        existing = set(db.execute(
            select(UserOffice.office_id).where(UserOffice.user_id == user.id)
        ).scalars().all())
        for i, oid in enumerate(assigned):
            if oid not in existing:
                db.add(UserOffice(user_id=user.id, office_id=oid, is_primary=(i == 0)))
        db.commit()

        # A patient homed at an office the user is NOT assigned to (for
        # patient_not_in_office). Prefer an existing one; else make a placeholder.
        cross_patient_id = None
        if unassigned:
            cross_patient_id = db.execute(
                select(Patient.id).where(
                    Patient.tenant_id == tenant_id,
                    Patient.home_office_id.in_(unassigned),
                    Patient.is_active.is_(True),
                ).limit(1)
            ).scalars().first()
            if cross_patient_id is None:
                p = Patient(
                    tenant_id=tenant_id, first_name="Cross", last_name="Office",
                    home_office_id=unassigned[0], chart_no=f"XO-{unassigned[0]}", is_active=True,
                )
                db.add(p)
                db.commit()
                db.refresh(p)
                cross_patient_id = p.id
                print(f"Created cross-office patient id={p.id} home_office_id={unassigned[0]}")

        print("-- Office-scope test account ready --")
        print(f"  login:            {args.username} / {args.password}")
        print(f"  role:             front_desk (NOT office_scope_view_all_offices)")
        print(f"  assigned offices: {assigned}")
        print(f"  other offices:    {unassigned or '(none — tenant has only the assigned ones)'}")
        if cross_patient_id is not None:
            print(f"  cross-office chart (expect patient_not_in_office): patient id={cross_patient_id}")
        print("  Try: switch to an unassigned office (403 office_not_assigned);")
        print("       GET /patients?all_offices=true (403); open the cross-office chart (403).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
