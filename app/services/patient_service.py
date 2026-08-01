"""Patient-specific CRUD rules.

The Add-Patient screen leaves Chart No blank and the UI implies it is
auto-generated (GAP-AP-14). ``PatientCRUD`` fills it server-side on create when
omitted, so the persisted record carries a real ``chart_no`` instead of null (the
Overview previously fell back to displaying the numeric id).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crud.base import CRUDBase
from app.db.models import Patient


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
        payload = dict(data)
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
