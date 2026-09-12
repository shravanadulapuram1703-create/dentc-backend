"""Patient-specific CRUD rules.

The Add-Patient screen leaves Chart No blank and the UI implies it is
auto-generated (GAP-AP-14). ``PatientCRUD`` fills it server-side on create when
omitted, so the persisted record carries a real ``chart_no`` instead of null (the
Overview previously fell back to displaying the numeric id).

``PatientCRUD`` is also where the Add/Edit Patient checkbox-integrity rules are
enforced on the generic resource — see ``patient_rules_service`` for the rule
table and the reasoning. ``PatientInsuranceCRUD`` does the same for the Coverage
Type panel's slots.

MH-9/MH-10 — making the patient picker usable
---------------------------------------------
``GET /patients?search=`` had no relevance ranking, so searching ``Rob`` for the
patient *Rob, Leo* returned hundreds of ``Robert*`` surnames paged
alphabetically and the exact match was not in the first fifty rows — unreachable
through any picker a user would tolerate, which is why the Copy Medical History
dialog had to re-implement resolution on the client. :meth:`PatientCRUD._search_order`
ranks exact chart/id and exact-name matches ahead of prefix matches ahead of
substring matches; the caller's own ``sort`` still decides ties *within* a tier,
so ``sort=last_name`` keeps meaning what it meant.

``_extra_search_clauses`` additionally understands the ``"Last, First"`` form
staff actually type — the plain column ilikes could never match it, because no
single column contains the comma.

MH-10: ``?phone=`` compared ``patients.phone`` only, and most patients in the
migrated data carry a cell number and no home number, so the filter returned
nothing for them. It now spans ``phone``/``cell_phone``/``work_phone``.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import and_, case, false, func, literal, or_, select
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
    # MH-10: ``phone`` is resolved by this class, not by the generic equality
    # pass, so one query param can reach all three number columns.
    custom_filter_fields = ("phone", "legacy_id")

    def _extra_list_clauses(self, filters: dict[str, Any]) -> list:
        clauses: list = []
        # PT-SEARCH-1: Legacy ID is an exact match on the pre-import id. It is
        # resolved here rather than by the generic equality pass only so that a
        # pasted value with stray whitespace still hits; the stored column holds
        # no padding (0 of 83,861 live values), so the compare stays a plain
        # ``=`` and rides the unique index.
        legacy = filters.get("legacy_id")
        if legacy is not None:
            legacy = str(legacy).strip()
            if legacy:
                clauses.append(Patient.legacy_id == legacy)
            else:
                # An explicit blank means "match nothing", never "unfiltered":
                # the FE detects an ignored filter by rows that do not carry the
                # requested value, and a random page is the bug being fixed.
                clauses.append(false())
        raw = (filters.get("phone") or "").strip()
        if not raw:
            return clauses
        digits = re.sub(r"\D", "", raw)
        columns = (Patient.phone, Patient.cell_phone, Patient.work_phone)
        phone_clauses = []
        for column in columns:
            phone_clauses.append(column == raw)
            if digits:
                # Migrated numbers are stored unformatted, so a digits-only
                # contains match is what finds them; a formatted stored value
                # still matches the verbatim comparison above.
                phone_clauses.append(column.ilike(f"%{digits}%"))
        clauses.append(or_(*phone_clauses))
        return clauses

    def _extra_search_clauses(self, search: str) -> list:
        """MH-9: recognise ``"Last, First"`` — the form the legacy pickers show
        and staff therefore type. No single column contains it, so the generic
        per-column ilike can never match."""
        term = (search or "").strip()
        clauses: list = []
        # PT-SEARCH-1: the Dashboard Quick Search box has no mode selector, so a
        # typed legacy id has to resolve through free text too. Exact only (an
        # index probe) — a substring ilike on a numeric column would drown a
        # name search in unrelated ids.
        if term:
            clauses.append(Patient.legacy_id == term)
        if "," not in term:
            return clauses
        last, _, first = term.partition(",")
        last, first = last.strip(), first.strip()
        if not last:
            return clauses
        clause = Patient.last_name.ilike(f"{last}%")
        if first:
            clause = and_(clause, Patient.first_name.ilike(f"{first}%"))
        clauses.append(clause)
        return clauses

    def _search_order(self, search: str) -> list:
        """Rank exact matches ahead of prefix ahead of substring (MH-9)."""
        term = (search or "").strip()
        if not term:
            return []
        lowered = term.lower()
        last, _, first = term.partition(",")
        last, first = last.strip().lower(), first.strip().lower()

        exact = [func.lower(Patient.chart_no) == lowered, Patient.legacy_id == term]
        if term.isdigit():
            exact.append(Patient.id == int(term))
        name_exact = or_(
            func.lower(Patient.last_name) == lowered,
            func.lower(Patient.first_name) == lowered,
        )
        prefix = or_(
            func.lower(Patient.last_name).like(f"{lowered}%"),
            func.lower(Patient.first_name).like(f"{lowered}%"),
        )
        branches = [(or_(*exact), literal(0)), (name_exact, literal(1))]
        if "," in term and last:
            pair = func.lower(Patient.last_name).like(f"{last}%")
            if first:
                pair = and_(pair, func.lower(Patient.first_name).like(f"{first}%"))
            branches.append((pair, literal(2)))
        branches.append((prefix, literal(3)))
        return [case(*branches, else_=literal(4)).asc()]

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
        # GAP-AP-21: the same duplicate guard (and the same override) as
        # /patients/register — the plain create was the unguarded back door.
        force_create = bool(payload.pop("force_create", False))
        if tenant_id is not None:
            from app.services.patient_extra_service import raise_if_duplicate

            raise_if_duplicate(db, tenant_id, payload, force_create=force_create)
        if tenant_id is not None and hasattr(self.model, "tenant_id"):
            payload.setdefault("tenant_id", tenant_id)
        if created_by is not None and self._is_int_col("created_by"):
            payload.setdefault("created_by", created_by)
        obj = self.model(**payload)
        db.add(obj)
        self._flush(db)  # obtain the SERIAL id before deriving chart_no
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
        payload.pop("force_create", None)  # create-only; never a column
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
