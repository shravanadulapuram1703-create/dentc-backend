"""Procedure Code Setup DTOs (procedure-code dev-report PROC-2/3/5/6)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, create_model

from app.db.models import PrescriptionLibrary, ProcedureCode, ProcedureInsuranceRule
from app.schemas.factory import build_schemas

# ── PROC-3: per-code insurance rules ─────────────────────────────────────────
ProcedureInsuranceRuleCreate, ProcedureInsuranceRuleUpdate, ProcedureInsuranceRuleRead = build_schemas(
    ProcedureInsuranceRule, "ProcedureInsuranceRule",
    create_exclude=("procedure_code", "created_by", "updated_by"),
    update_exclude=("procedure_code", "created_by", "updated_by"),
)

# ── PROC-2: provider↔procedure permission set ────────────────────────────────
AssignedProcedureCodeRead = build_schemas(ProcedureCode, "AssignedProviderProcedureCode")[2]


class ProcedureCodesSet(BaseModel):
    codes: list[str] = Field(default_factory=list, description="Full assigned code set (replaces existing)")


# ── PROC-5: KPI stats ────────────────────────────────────────────────────────
class ProcedureCodeStats(BaseModel):
    total: int = 0
    active: int = 0
    inactive: int = 0
    ortho: int = 0
    by_category: dict[str, int] = Field(default_factory=dict, description="category → count")


# ── APPT-10: procedure-code category taxonomy ────────────────────────────────
class ProcedureCodeCategory(BaseModel):
    """One row of the category taxonomy behind the Quick Add category buttons.

    The picker used to derive its categories by paging the whole 1,100-code
    catalog; this is the taxonomy on its own.
    """

    category: str
    code_count: int = 0
    active_code_count: int = 0


# ── PROC-6: lightweight fee-schedule id→name projection ──────────────────────
class FeeScheduleOption(BaseModel):
    id: int
    name: str
    fee_type: str | None = None


# ── Prescriptions Setup (RX-1/2/4, pick_list_setup_backend_devreport §4) ─────
_RxCreate, _RxUpdate, _RxReadBase = build_schemas(PrescriptionLibrary, "PrescriptionLibraryBase")


class PrescriptionLibraryCreate(_RxCreate):  # type: ignore[valid-type, misc]
    """RX-4: an active row with the same drug name + dispense + sig is a 409
    ``duplicate_prescription``. ``allow_duplicate`` is the API half of the
    dialog's override — the seed legitimately lists one drug twice with different
    configurations, so the server refuses the *accidental* duplicate, never the
    duplicate. ``sig`` over 240 characters is a 422 ``sig_too_long`` (RX-2)."""

    allow_duplicate: bool = False


class PrescriptionLibraryUpdate(_RxUpdate):  # type: ignore[valid-type, misc]
    allow_duplicate: bool = False


# RX-1: the Setup header renders "Modified By: DRLI" — a name, not a user id.
PrescriptionLibraryRead = create_model(
    "PrescriptionLibraryRead", __base__=_RxReadBase,
    created_by_name=(Optional[str], None),
    updated_by_name=(Optional[str], None),
)


class PrescriptionMatch(BaseModel):
    id: int
    drug_name: str
    dispense: str | None = None
    sig: str | None = None
    refills: int | None = None
    is_as_written: bool | None = None
    is_active: bool | None = None
    legacy_id: str | None = None


class PrescriptionAvailabilityResult(BaseModel):
    """RX-4 probe — ``taken`` is exactly the condition the save path 409s on."""

    drug_name: str
    dispense: str | None = None
    sig: str | None = None
    taken: bool
    matches: list[PrescriptionMatch] = Field(default_factory=list)
    inactive_matches: list[PrescriptionMatch] = Field(default_factory=list)
    same_name_matches: list[PrescriptionMatch] = Field(default_factory=list)
    override_field: str = "allow_duplicate"


class PrescriptionLibraryLimits(BaseModel):
    """RX-2 — the caps the API enforces, so the editor's counter cannot drift."""

    sig_max_length: int
    drug_name_max_length: int
    dispense_max_length: int
    duplicate_key_fields: list[str]
    override_field: str
