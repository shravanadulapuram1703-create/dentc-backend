"""Procedure Code Setup DTOs (procedure-code dev-report PROC-2/3/5/6)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.db.models import ProcedureCode, ProcedureInsuranceRule
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
