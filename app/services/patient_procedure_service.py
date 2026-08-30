"""Charge-row rules that must hold whoever is writing (AL-17, FEE-3).

**Hold Claim.** ``patient_procedures.hold_claim`` is the legacy per-procedure hold:
the charge is deliberately kept back from insurance. The ledger renders a red **H**
in the Bill column and disables the row's ``Prn`` checkbox, and the Create Claim
flow is `POST /insurance-claims` followed by a `PATCH /patient-procedures/{id}`
that stamps ``claim_id`` — so *the only thing standing between a held charge and a
claim was one disabled checkbox in one screen*. Any other caller (a second screen,
a script, a direct API call, a stale page) could claim it.

That is the same shape as the Add/Edit-Patient flag rules: a rule the office relies
on belongs on every write path, not on the one client that happens to know about
it. So assigning a ``claim_id`` to a held charge is a **422**, not a silent write.

Deliberately narrow:

* Only an *assignment* is blocked. Clearing ``claim_id``, editing the fee, voiding —
  all unaffected.
* The hold is evaluated against the **merge of payload and stored row**, so a PATCH
  that lifts the hold and stamps the claim in one call succeeds. Un-holding and
  claiming is a normal thing to do; doing it by accident is not.
* Nothing rewrites history: the 297,624 migrated charges that gained a ``claim_id``
  from the source export are untouched, hold or no hold.

**Server-side pricing (FEE-3).** Fee resolution used to exist only in the
frontend, so nothing stopped a charge being posted with an arbitrary amount —
and a client that fell back to ``procedure_codes.default_fee`` posted ``0.00``,
which is ``default_fee`` on every migrated code. A create that omits ``fee``
is now priced through :func:`pricing_service.resolve_procedure_fee`, the same
resolver behind ``GET /patients/{id}/fee`` and the estimate engine. An
explicitly supplied fee always wins: the office is allowed to charge what it
decides to charge, and refusing the write would break every legitimate
off-schedule adjustment.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.crud.base import CRUDBase
from app.db.models import PatientProcedure
from app.services import pricing_service


def _truthy(value: Any) -> bool:  # noqa: ANN401
    """`hold_claim` arrives as a bool from the ORM but as anything JSON can hold
    from a PATCH body."""
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "on")
    return bool(value)


def _reject_held_claim(held: bool, claim_id: Any) -> None:  # noqa: ANN401
    if claim_id and held:
        raise ValidationError(
            "This procedure is on Hold Claim and cannot be added to a claim",
            details={
                "code": "procedure_on_hold_claim",
                "hint": "Clear hold_claim first — the same PATCH may do both.",
            },
        )


class PatientProcedureCRUD(CRUDBase[PatientProcedure]):
    """Generic CRUD plus the Hold Claim guard (AL-17)."""

    def create(self, db: Session, data: dict, *, tenant_id=None, created_by=None):  # noqa: ANN001, ANN201
        _reject_held_claim(_truthy(data.get("hold_claim")), data.get("claim_id"))
        payload = self._price(db, dict(data), tenant_id)
        return super().create(db, payload, tenant_id=tenant_id, created_by=created_by)

    @staticmethod
    def _price(db: Session, data: dict, tenant_id: int | None) -> dict:
        """Fill ``fee`` (and the fee provenance) when the caller omitted it."""
        if data.get("fee") is not None or tenant_id is None:
            return data
        code = data.get("procedure_code")
        if not code:
            return data
        quote = pricing_service.resolve_procedure_fee(
            db, tenant_id, code,
            patient_id=data.get("patient_id"),
            office_id=data.get("office_id"),
            provider_id=data.get("provider_id"),
        )
        data["fee"] = quote["fee"]
        # Provenance only where the caller left it blank — never overwrite an
        # explicit value.
        if data.get("fee_schedule_id") is None and quote["fee_schedule_id"]:
            data["fee_schedule_id"] = quote["fee_schedule_id"]
        if data.get("ucr_fee") is None and quote["ucr_fee"] is not None:
            data["ucr_fee"] = quote["ucr_fee"]
        return data

    def update(self, db: Session, obj_id, data: dict, *, tenant_id=None, updated_by=None):  # noqa: ANN001, ANN201
        if data.get("claim_id"):
            # A PATCH may carry claim_id alone, so the hold to check is the
            # payload's when it says, else the one already on the row.
            current = self.get(db, obj_id, tenant_id=tenant_id)
            held = _truthy(
                data["hold_claim"] if "hold_claim" in data else current.hold_claim
            )
            _reject_held_claim(held, data["claim_id"])
        return super().update(db, obj_id, data, tenant_id=tenant_id, updated_by=updated_by)
