"""Charge-row rules that must hold whoever is writing (AL-17).

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
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.crud.base import CRUDBase
from app.db.models import PatientProcedure


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
        return super().create(db, data, tenant_id=tenant_id, created_by=created_by)

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
