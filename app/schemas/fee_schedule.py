"""Fee Schedule DTOs (insurance dev-report FEE-4).

The Create/Update/Read trio is shared between the generated CRUD router (registry)
and the supplemental router (restore / new-version), so there is a single named
``FeeScheduleRead`` OpenAPI component.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.db.models import FeeSchedule
from app.schemas.factory import build_schemas

FeeScheduleCreate, FeeScheduleUpdate, FeeScheduleRead = build_schemas(
    FeeSchedule, "FeeSchedule",
    # version & lineage are server-managed (set on create / new-version).
    create_exclude=("version", "parent_schedule_id"),
    update_exclude=("version", "parent_schedule_id"),
)


class NewFeeScheduleVersionRequest(BaseModel):
    """FEE-4: clone a schedule (and its entries) under a new effective date."""

    effective_date: date = Field(..., description="Effective date of the new version")
    name: str | None = Field(None, description="Optional new name; defaults to the source name")
