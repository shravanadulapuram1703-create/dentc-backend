"""Charge-row rules that must hold whoever is writing (AL-17, FEE-3, PROC-INT-1/2/3/8).

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

**Tooth / surface / quadrant rules (PROC-INT-8).** Every create, and every
update that touches ``procedure_code``/``tooth``/``surface``/``quadrant``, runs
:func:`procedure_rules_service.apply_entry_rules`: the surface is canonicalised
(``"d,o m"`` → ``"MOD"``), a legacy quadrant-in-tooth is mirrored into
``quadrant``, and the code's ``requires_*`` / surface-count / ``valid_teeth``
rules return a 422 naming the field. A PATCH that only re-prices a migrated
charge never trips them.

**Planned → completed (PROC-INT-1/2).** ``treatment_plan_item_id`` is the item
this charge fulfils. Setting it on create/PATCH validates the item against the
charge's patient and plan, lets the charge inherit the item's tooth/surface/
quadrant/material where the payload left them blank, and — in the **same
transaction** — flips the item to ``status='completed'``. Voiding the charge
(``is_void`` or DELETE) or re-pointing it releases the item back to
``accepted`` unless another live charge still fulfils it. Un-voiding re-binds.

**Push (PROC-INT-3).** Every write announces ``procedures.changed`` after its commit.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.crud.base import CRUDBase
from app.db.models import PatientProcedure
from app.services import pricing_service, procedure_events, treatment_service
from app.services.claim_form_service import attach_procedure_to_claim, normalise_claim_line
from app.services.procedure_rules_service import apply_entry_rules

CHARGE_SOURCE = "patient_procedures"
_INHERITED_FROM_ITEM = ("tooth", "surface", "quadrant", "material_id")


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
    """Generic CRUD plus the Hold Claim guard (AL-17), server-side pricing (FEE-3),
    the entry rules (PROC-INT-8) and the plan-item link (PROC-INT-1/2)."""

    def create(self, db: Session, data: dict, *, tenant_id=None, created_by=None):  # noqa: ANN001, ANN201
        payload = dict(data)
        _reject_held_claim(_truthy(payload.get("hold_claim")), payload.get("claim_id"))

        item = None
        if payload.get("treatment_plan_item_id"):
            item = treatment_service.resolve_item_for_charge(
                db, payload["treatment_plan_item_id"],
                patient_id=payload.get("patient_id"),
                treatment_plan_id=payload.get("treatment_plan_id"),
            )
            payload.setdefault("treatment_plan_id", item.plan_id)
            for field in _INHERITED_FROM_ITEM:
                if payload.get(field) is None and getattr(item, field) is not None:
                    payload[field] = getattr(item, field)

        payload = apply_entry_rules(db, payload)
        payload = normalise_claim_line(payload)  # ADA-BE-3/4
        payload = self._price(db, payload, tenant_id)

        # Same steps as CRUDBase.create, inlined so the item flip lands in the
        # same transaction as the charge (a half-applied Post to Ledger is
        # exactly the failure the FK exists to remove).
        if created_by is not None and self._is_int_col("created_by"):
            payload.setdefault("created_by", created_by)
        obj = self.model(**payload)
        db.add(obj)
        if item is not None:
            db.flush()
            treatment_service.bind_item_to_charge(db, item, obj)
        if obj.claim_id:
            self._attach_claim(db, obj)
        self._commit(db)
        db.refresh(obj)
        procedure_events.announce(
            tenant_id, obj.patient_id, source=CHARGE_SOURCE,
            action="posted" if item is not None else "created", entity_id=obj.id,
            treatment_plan_id=obj.treatment_plan_id,
            treatment_plan_item_id=obj.treatment_plan_item_id, actor_user_id=created_by,
        )
        return obj

    @staticmethod
    def _attach_claim(db: Session, proc: PatientProcedure) -> None:
        """ADA-BE-12: the ledger builds a claim as POST + per-line PATCH, so the
        claim's treating / billing provider and service dates are filled from
        the first line that lands on it (never overwritten once set)."""
        from app.db.models import InsuranceClaim  # noqa: PLC0415

        claim = db.get(InsuranceClaim, proc.claim_id)
        if claim is not None:
            attach_procedure_to_claim(db, claim, proc)

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
        current = self.get(db, obj_id, tenant_id=tenant_id)
        payload = dict(data)
        if payload.get("claim_id"):
            # A PATCH may carry claim_id alone, so the hold to check is the
            # payload's when it says, else the one already on the row.
            held = _truthy(payload["hold_claim"] if "hold_claim" in payload else current.hold_claim)
            _reject_held_claim(held, payload["claim_id"])
        payload = apply_entry_rules(db, payload, current)
        payload = normalise_claim_line(payload, current)  # ADA-BE-3/4
        claim_changed = bool(payload.get("claim_id")) and payload["claim_id"] != current.claim_id

        # ── plan-item link transitions ─────────────────────────────────────
        old_item_id = current.treatment_plan_item_id
        new_item = None
        item_changed = "treatment_plan_item_id" in payload and payload["treatment_plan_item_id"] != old_item_id
        if item_changed and payload["treatment_plan_item_id"]:
            new_item = treatment_service.resolve_item_for_charge(
                db, payload["treatment_plan_item_id"],
                patient_id=payload.get("patient_id", current.patient_id),
                treatment_plan_id=payload.get("treatment_plan_id"),
            )
            if "treatment_plan_id" not in payload:
                payload["treatment_plan_id"] = new_item.plan_id
        was_void = bool(current.is_void)
        will_be_void = _truthy(payload["is_void"]) if "is_void" in payload else was_void

        for key, value in payload.items():
            setattr(current, key, value)
        if updated_by is not None and self._is_int_col("updated_by"):
            current.updated_by = updated_by
        if claim_changed:
            self._attach_claim(db, current)

        if item_changed:
            treatment_service.release_item(db, old_item_id, exclude_procedure_id=current.id)
        if will_be_void and not was_void:
            treatment_service.release_item(
                db, current.treatment_plan_item_id, exclude_procedure_id=current.id
            )
        elif not will_be_void:
            if new_item is not None:
                treatment_service.bind_item_to_charge(db, new_item, current)
            elif was_void and current.treatment_plan_item_id:
                # un-void: the charge is live again, so the item it fulfils is completed again
                item = treatment_service.resolve_item_for_charge(
                    db, current.treatment_plan_item_id,
                    patient_id=current.patient_id, treatment_plan_id=None,
                )
                treatment_service.bind_item_to_charge(db, item, current)

        self._commit(db)
        db.refresh(current)
        procedure_events.announce(
            tenant_id, current.patient_id, source=CHARGE_SOURCE,
            action="voided" if (will_be_void and not was_void) else "updated",
            entity_id=current.id, treatment_plan_id=current.treatment_plan_id,
            treatment_plan_item_id=current.treatment_plan_item_id, actor_user_id=updated_by,
        )
        return current

    def delete(self, db: Session, obj_id, *, tenant_id=None) -> None:  # noqa: ANN001
        """A charge delete is a void (``is_void``), and voiding releases the item."""
        obj = self.get(db, obj_id, tenant_id=tenant_id)
        if self.soft_delete_field:
            setattr(obj, self.soft_delete_field, self.soft_delete_value)
            treatment_service.release_item(db, obj.treatment_plan_item_id, exclude_procedure_id=obj.id)
        else:  # pragma: no cover - the registry always configures is_void
            treatment_service.release_item(db, obj.treatment_plan_item_id, exclude_procedure_id=obj.id)
            db.delete(obj)
        self._commit(db)
        procedure_events.announce(
            tenant_id, obj.patient_id, source=CHARGE_SOURCE, action="voided",
            entity_id=obj.id, treatment_plan_id=obj.treatment_plan_id,
            treatment_plan_item_id=obj.treatment_plan_item_id,
        )


#: Shared instance for service callers (Post to Ledger). The registry builds its
#: own for the routes; the class holds no per-instance state beyond config.
patient_procedure_crud = PatientProcedureCRUD(
    PatientProcedure, soft_delete_field="is_void", soft_delete_value=True, default_sort="created_at"
)
