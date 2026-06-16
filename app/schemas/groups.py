"""Security -> Groups DTOs (rights catalog + group->rights assignment + copy)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class PermissionRead(ORMModel):
    """One assignable right in the global catalog (gap #1)."""

    code: str
    label: str
    category: str | None = None


class GroupRightsSet(BaseModel):
    """Full-replace payload for a group's rights (gap #2).

    "Save with Full Access" = send the entire catalog's codes.
    """

    right_codes: list[str] = Field(default_factory=list, description="Permission codes to assign")


class GroupRead(ORMModel):
    """User group, returned by the copy endpoint (gap #3)."""

    id: int
    tenant_id: int
    name: str
    description: str | None = None
    is_active: bool
    created_at: datetime
