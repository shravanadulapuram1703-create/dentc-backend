"""Insurance business logic that supplements generated CRUD.

INS-PT-5 — eligibility "Update Status": stamp a subscriber's verification
(``elig_status`` / ``elig_verified_on`` / ``elig_verified_by``) server-side. There
is no clearinghouse integration yet, so this records a *manual* verification; the
response reports whether the carrier advertises real-time eligibility
(``insurance_carriers.supports_realtime_eligibility``) for when that lands.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models import (
    InsuranceCarrier,
    InsurancePlan,
    InsuranceSubscriber,
    User,
)


def _display_name(user: User | None) -> str | None:
    if user is None:
        return None
    full = " ".join(p for p in (user.first_name, user.last_name) if p).strip()
    return full or user.username


def verify_eligibility(
    db: Session, subscriber_id: int, tenant_id: int, actor: User,
    *, elig_status: str | None = None, notes: str | None = None,
) -> dict:
    sub = db.get(InsuranceSubscriber, subscriber_id)
    if sub is None or sub.tenant_id != tenant_id:
        raise NotFoundError(f"InsuranceSubscriber '{subscriber_id}' was not found")

    realtime_supported: bool | None = None
    if sub.ins_plan_id is not None:
        plan = db.get(InsurancePlan, sub.ins_plan_id)
        if plan is not None:
            carrier = db.get(InsuranceCarrier, plan.carrier_id)
            if carrier is not None:
                realtime_supported = carrier.supports_realtime_eligibility

    sub.elig_status = elig_status or "verified"
    sub.elig_verified_on = datetime.now(timezone.utc)
    sub.elig_verified_by = _display_name(actor)
    if notes is not None:
        sub.elig_notes = notes
    db.commit()
    db.refresh(sub)

    return {
        "subscriber_id": sub.id,
        "elig_status": sub.elig_status,
        "elig_verified_on": sub.elig_verified_on,
        "elig_verified_by": sub.elig_verified_by,
        "realtime_supported": realtime_supported,
        # No clearinghouse wired yet → always a manual stamp.
        "method": "manual",
    }
