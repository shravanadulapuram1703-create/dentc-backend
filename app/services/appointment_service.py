"""Appointment-side half of the plan-item <-> appointment link (PLAN-APPT-1/2).

``treatment_service`` owns the item state machine (``schedule_item`` /
``release_scheduled_item``); this module is every appointment write path that
has to call it:

* ``AppointmentProcedureCRUD`` — a line created with ``treatment_plan_item_id``
  is validated against the appointment's patient / plan, inherits what the item
  knows (code, tooth, surface, fee, estimate, duration, provider) where the
  payload left it blank, and books the item. Re-pointing or archiving the line
  releases it.
* ``AppointmentCRUD`` — a PATCH that cancels / archives the appointment (or a
  DELETE, which is a soft archive) releases every item it books; un-cancelling
  / restoring books them again; a date move keeps ``scheduled_date`` honest.

``scheduler_service.update_status`` / ``restore_appointment`` call the same two
helpers, so the status endpoint and the generic PATCH cannot disagree.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.crud.base import CRUDBase
from app.db.models import Appointment, AppointmentProcedure, Office, Operatory
from app.services import lab_tracking_service, treatment_service


def apply_operatory_rules(
    db: Session, payload: dict, current: Appointment | None = None, *, tenant_id: int | None = None
) -> dict:
    """OFF-SCOPE-12: an appointment's operatory and office must agree.

    * an operatory pins the office — when the payload omits ``office_id`` it is
      derived from the operatory;
    * an operatory whose office differs from a supplied ``office_id`` is a 422
      ``operatory_office_mismatch`` (a chair belongs to exactly one office, so a
      cross-office booking is a data error, not a coverage decision);
    * ``provider_id`` defaults to the operatory's column-header provider when the
      payload leaves it blank.

    Judged against the merge of payload + stored row so a PATCH that touches only
    one of the three still validates the trio.
    """
    def _merged(field: str):
        if field in payload:
            return payload[field]
        return getattr(current, field, None) if current is not None else None

    op_id = _merged("operatory_id")
    if not op_id:
        return payload
    op = db.get(Operatory, op_id)
    if op is None:
        raise ValidationError(
            f"Operatory '{op_id}' was not found",
            # FE-OFF-4: the machine code is at ``error.code`` (uniform with the
            # other office errors); ``details.code`` is kept for the appointment
            # domain's existing readers.
            code="operatory_not_found",
            details={"code": "operatory_not_found", "field": "operatory_id"},
        )
    office_id = _merged("office_id")
    if office_id is None:
        payload["office_id"] = op.office_id
    elif op.office_id != office_id:
        raise ValidationError(
            "The operatory belongs to a different office than the appointment",
            code="operatory_office_mismatch",
            details={
                "code": "operatory_office_mismatch",
                "field": "operatory_id",
                "operatory_office_id": op.office_id,
                "office_id": office_id,
            },
        )
    if not _merged("provider_id") and op.provider_id:
        payload["provider_id"] = op.provider_id
    return payload

_INHERITED_FROM_ITEM = (
    ("procedure_code", "procedure_code"),
    ("tooth", "tooth"),
    ("surface", "surface"),
    ("description", "description"),
    ("provider_id", "provider_id"),
    ("billing_order", "billing_order"),
    ("material_id", "material_id"),
    ("duration_minutes", "duration_minutes"),
)


def _truthy(value: Any) -> bool:  # noqa: ANN401
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "on")
    return bool(value)


def _require_appointment(db: Session, appt_id: Any, tenant_id: int | None) -> Appointment:  # noqa: ANN401
    appt = db.get(Appointment, appt_id) if appt_id else None
    if appt is None:
        raise ValidationError(
            f"Appointment '{appt_id}' was not found",
            details={"code": "appointment_not_found", "field": "appointment_id"},
        )
    if tenant_id is not None:
        office = db.get(Office, appt.office_id)
        if office is None or office.tenant_id != tenant_id:
            raise ValidationError(
                f"Appointment '{appt_id}' was not found",
                details={"code": "appointment_not_found", "field": "appointment_id"},
            )
    return appt


def sync_appointment_items(db: Session, appt: Appointment, *, was_live: bool) -> None:
    """Book / release the appointment's items after its liveness changed. No commit."""
    now_live = treatment_service.appointment_is_live(appt)
    if was_live and not now_live:
        treatment_service.unschedule_items_for_appointment(db, appt)
    elif now_live and not was_live:
        treatment_service.schedule_items_for_appointment(db, appt)


class AppointmentProcedureCRUD(CRUDBase[AppointmentProcedure]):
    def create(self, db: Session, data: dict, *, tenant_id=None, created_by=None):  # noqa: ANN001, ANN201
        payload = dict(data)
        appt = _require_appointment(db, payload.get("appointment_id"), tenant_id)
        item = None
        if payload.get("treatment_plan_item_id"):
            item = treatment_service.resolve_item_for_appointment(
                db, payload["treatment_plan_item_id"],
                patient_id=appt.patient_id, treatment_plan_id=payload.get("treatment_plan_id"),
            )
            payload.setdefault("treatment_plan_id", item.plan_id)
            for line_field, item_field in _INHERITED_FROM_ITEM:
                if payload.get(line_field) is None and getattr(item, item_field) is not None:
                    payload[line_field] = getattr(item, item_field)
            if payload.get("fee") is None:
                payload["fee"] = item.fee
            if payload.get("insurance_estimate") is None:
                payload["insurance_estimate"] = item.insurance_estimate
            if payload.get("duration_minutes") is None:
                payload["duration_minutes"] = treatment_service.item_duration_minutes(db, item)
        if created_by is not None and self._is_int_col("created_by"):
            payload.setdefault("created_by", created_by)
        obj = self.model(**payload)
        db.add(obj)
        if item is not None and treatment_service.appointment_is_live(appt) and not _truthy(payload.get("is_archived")):
            db.flush()
            treatment_service.schedule_item(db, item, appt)
        self._commit(db)
        db.refresh(obj)
        self._audit(obj, after=dict(payload))
        return obj

    def update(self, db: Session, obj_id, data: dict, *, tenant_id=None, updated_by=None):  # noqa: ANN001, ANN201
        current = self.get(db, obj_id, tenant_id=tenant_id)
        payload = dict(data)
        appt = db.get(Appointment, payload.get("appointment_id") or current.appointment_id)
        old_item_id = current.treatment_plan_item_id
        new_item = None
        item_changed = (
            "treatment_plan_item_id" in payload and payload["treatment_plan_item_id"] != old_item_id
        )
        if item_changed and payload["treatment_plan_item_id"]:
            new_item = treatment_service.resolve_item_for_appointment(
                db, payload["treatment_plan_item_id"],
                patient_id=appt.patient_id if appt else None,
                treatment_plan_id=payload.get("treatment_plan_id"),
            )
            if "treatment_plan_id" not in payload:
                payload["treatment_plan_id"] = new_item.plan_id
        was_archived = bool(current.is_archived)
        will_be_archived = _truthy(payload["is_archived"]) if "is_archived" in payload else was_archived

        for key, value in payload.items():
            setattr(current, key, value)
        if updated_by is not None and self._is_int_col("updated_by"):
            current.updated_by = updated_by

        if item_changed:
            treatment_service.release_scheduled_item(db, old_item_id, exclude_line_id=current.id)
        if will_be_archived and not was_archived:
            treatment_service.release_scheduled_item(
                db, current.treatment_plan_item_id, exclude_line_id=current.id
            )
        elif not will_be_archived and appt is not None and treatment_service.appointment_is_live(appt):
            target = new_item
            if target is None and was_archived and current.treatment_plan_item_id:
                target = treatment_service.resolve_item_for_appointment(
                    db, current.treatment_plan_item_id,
                    patient_id=appt.patient_id, treatment_plan_id=None,
                )
            if target is not None:
                treatment_service.schedule_item(db, target, appt)
        self._commit(db)
        db.refresh(current)
        return current

    def delete(self, db: Session, obj_id, *, tenant_id=None) -> None:  # noqa: ANN001
        """A line delete is a soft archive (APPT-PROC-4) and releases the item."""
        obj = self.get(db, obj_id, tenant_id=tenant_id)
        if self.soft_delete_field:
            setattr(obj, self.soft_delete_field, self.soft_delete_value)
        else:  # pragma: no cover - the registry always configures is_archived
            db.delete(obj)
        treatment_service.release_scheduled_item(db, obj.treatment_plan_item_id, exclude_line_id=obj.id)
        self._commit(db)


class AppointmentCRUD(CRUDBase[Appointment]):
    """Plan-item sync (PLAN-APPT-1) + the Lab Tracking write rules (LAB-1/8/9)
    on every generic create / update, so no client can route around them.

    ``lab_status`` (LAB-2) is a declared list filter that is not a column — it
    is the SQL twin of the status the read field reports, evaluated against
    UTC "today" (the ``/appointments/lab-cases`` view is office-timezone aware).
    """

    custom_filter_fields = ("lab_status",)

    def _extra_list_clauses(self, filters: dict) -> list:
        status = filters.get("lab_status")
        if not status:
            return []
        return [lab_tracking_service.lab_status_clause(status, lab_tracking_service.utc_today())]

    def create(self, db: Session, data: dict, *, tenant_id=None, created_by=None):  # noqa: ANN001, ANN201
        payload = apply_operatory_rules(db, dict(data), None, tenant_id=tenant_id)
        payload = lab_tracking_service.apply_lab_rules(db, payload, None, tenant_id=tenant_id)
        return super().create(db, payload, tenant_id=tenant_id, created_by=created_by)

    def update(self, db: Session, obj_id, data: dict, *, tenant_id=None, updated_by=None):  # noqa: ANN001, ANN201
        current = self.get(db, obj_id, tenant_id=tenant_id)
        was_live = treatment_service.appointment_is_live(current)
        old_date = current.date
        data = apply_operatory_rules(db, dict(data), current, tenant_id=tenant_id)
        data = lab_tracking_service.apply_lab_rules(db, data, current, tenant_id=tenant_id)
        obj = super().update(db, obj_id, data, tenant_id=tenant_id, updated_by=updated_by)
        now_live = treatment_service.appointment_is_live(obj)
        if was_live != now_live:
            sync_appointment_items(db, obj, was_live=was_live)
            db.commit()
        elif now_live and obj.date != old_date:
            treatment_service.resync_items_for_appointment(db, obj)
            db.commit()
        return obj

    def delete(self, db: Session, obj_id, *, tenant_id=None) -> None:  # noqa: ANN001
        obj = self.get(db, obj_id, tenant_id=tenant_id)
        was_live = treatment_service.appointment_is_live(obj)
        if self.soft_delete_field:
            setattr(obj, self.soft_delete_field, self.soft_delete_value)
            sync_appointment_items(db, obj, was_live=was_live)
        else:  # pragma: no cover - the registry always configures is_archived
            if was_live:
                treatment_service.unschedule_items_for_appointment(db, obj)
            db.delete(obj)
        self._commit(db)
