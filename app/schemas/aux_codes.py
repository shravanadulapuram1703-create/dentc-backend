"""Auxiliary code-table DTOs (AUX-4 bulk status)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class IcdBulkStatusRequest(BaseModel):
    """Bulk activate/deactivate ICD codes (legacy "Edit ICD Codes" Active toggle)."""

    ids: list[int] = Field(..., min_length=1, description="ICD code ids to update")
    is_active: bool = Field(..., description="Target active state for all listed ids")


class IcdBulkStatusResult(BaseModel):
    updated: int
