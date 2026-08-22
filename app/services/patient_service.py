"""Patient-specific CRUD rules.

The Add-Patient screen leaves Chart No blank and the UI implies it is
auto-generated (GAP-AP-14). ``PatientCRUD`` fills it server-side on create when
omitted, so the persisted record carries a real ``chart_no`` instead of null (the
Overview previously fell back to displaying the numeric id).

``PatientCRUD`` is also where the Add/Edit Patient checkbox-integrity rules are
enforced on the generic resource — see ``patient_rules_service`` for the rule
table and the reasoning. ``PatientInsuranceCRUD`` does the same for the Coverage
Type panel's slots.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.db.models import Patient, PatientInsurance
from app.services import patient_rules_service as rules


def assign_chart_no(db: Session, obj: Patient) -> None:
    """Assign a chart number if the row has none. Called after the id is known
    (post-flush). ``chart_no`` is globally unique; the patient id is a safe
    default that matches the legacy Overview fallback.

    The migrated table can already hold a numeric ``chart_no`` equal to a future
    id, so probe for a free value (``{id}``, then ``{id}-1``, ``{id}-2`` …) rather
    than blindly assigning and risking a unique-constraint 500 on a real tenant.
    """
    if (obj.chart_no or "").strip():
        return
    base = str(obj.id)
    candidate = base
    suffix = 0
    while db.execute(
        select(Patient.id).where(Patient.chart_no == candidate, Patient.id != obj.id)
    ).scalar_one_or_none() is not None:
        suffix += 1
        candidate = f"{base}-{suffix}"
    obj.chart_no = candidate


class PatientCRUD(CRUDBase[Patient]):
    def create(
        self,
        db: Session,
        data: dict[str, Any],
        *,
        tenant_id: int | None = None,
        created_by: int | None = None,
    ) -> Patient:
        # Contradictory Patient Status / Patient Type selections are resolved or
        # rejected before anything is written.
        payload = rules.normalize_patient_payload(data)
        if tenant_id is not None and hasattr(self.model, "tenant_id"):
            payload.setdefault("tenant_id", tenant_id)
        if created_by is not None and self._is_int_col("created_by"):
            payload.setdefault("created_by", created_by)
        obj = self.model(**payload)
        db.add(obj)
        db.flush()  # obtain the SERIAL id before deriving chart_no
        assign_chart_no(db, obj)
        self._commit(db)
        db.refresh(obj)
        return obj

    def update(
        self,
        db: Session,
        obj_id: Any,
        data: dict[str, Any],
        *,
        tenant_id: int | None = None,
        updated_by: int | None = None,
    ) -> Patient:
        # A PATCH sends only the boxes the user touched, so the rules are applied
        # against the merge of the payload and the stored row — ticking "No
        # Correspondence" alone still has to reach the e-mail/SMS flags already
        # sitting true in the database.
        existing = self.get(db, obj_id, tenant_id=tenant_id)
        payload = rules.normalize_patient_payload(data, existing=existing)
        return super().update(
            db, obj_id, payload, tenant_id=tenant_id, updated_by=updated_by
        )


class PatientInsuranceCRUD(CRUDBase[PatientInsurance]):
    """Coverage Type panel: a slot may not outrank the coverage beneath it."""

    def create(
        self,
        db: Session,
        data: dict[str, Any],
        *,
        tenant_id: int | None = None,
        created_by: int | None = None,
    ) -> PatientInsurance:
        rules.validate_coverage_slot(
            db,
            patient_id=data.get("patient_id"),
            legacy_plan_type=data.get("legacy_plan_type"),
            insurance_type=data.get("insurance_type"),
            is_active=bool(data.get("is_active", True)),
        )
        return super().create(db, data, tenant_id=tenant_id, created_by=created_by)

    def update(
        self,
        db: Session,
        obj_id: Any,
        data: dict[str, Any],
        *,
        tenant_id: int | None = None,
        updated_by: int | None = None,
    ) -> PatientInsurance:
        existing = self.get(db, obj_id, tenant_id=tenant_id)

        def _merged(field: str, fallback: Any = None) -> Any:
            return data[field] if field in data else getattr(existing, field, fallback)

        rules.validate_coverage_slot(
            db,
            patient_id=_merged("patient_id"),
            legacy_plan_type=_merged("legacy_plan_type"),
            insurance_type=_merged("insurance_type"),
            is_active=bool(_merged("is_active", True)),
            exclude_id=existing.id,
        )
        return super().update(
            db, obj_id, data, tenant_id=tenant_id, updated_by=updated_by
        )
