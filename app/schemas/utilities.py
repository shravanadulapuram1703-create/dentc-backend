"""Utilities module DTOs — job submission + audit history (UTIL-1/2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from app.schemas.common import ORMModel


class UtilityRunRequest(BaseModel):
    office_id: Optional[int] = None
    parameters: Optional[dict[str, Any]] = None


class UtilityRunRead(ORMModel):
    id: int
    utility_id: str
    office_id: Optional[int] = None
    run_by: Optional[int] = None
    status: str
    parameters: Optional[dict[str, Any]] = None
    processed: int
    succeeded: int
    failed: int
    logs: Optional[list[str]] = None
    created_at: datetime
    finished_at: Optional[datetime] = None


class UtilityAuditList(BaseModel):
    runs: list[UtilityRunRead]
