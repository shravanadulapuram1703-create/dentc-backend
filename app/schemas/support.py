"""Help Center → support-ticket (Jira proxy) DTOs (HELP-1/2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from app.schemas.common import ORMModel


class SupportAttachment(BaseModel):
    name: str
    type: Optional[str] = None
    size: Optional[int] = None
    data_base64: Optional[str] = None


class SupportTicketCreate(BaseModel):
    """Mirrors ``jiraService.buildProxyBody`` on the frontend."""

    project_key: Optional[str] = None
    summary: str
    issue_type: Optional[str] = "Bug"
    priority: Optional[str] = "Medium"
    description_adf: Optional[dict[str, Any]] = None
    fields: Optional[dict[str, Any]] = None
    context: Optional[dict[str, Any]] = None
    attachments: list[SupportAttachment] = []


class SupportTicketResult(BaseModel):
    issue_key: str
    issue_url: Optional[str] = None


class SupportTicketRead(ORMModel):
    id: int
    issue_key: Optional[str] = None
    issue_url: Optional[str] = None
    title: str
    issue_type: Optional[str] = None
    priority: Optional[str] = None
    module: Optional[str] = None
    status: str
    mode: str = "proxy"
    reporter_id: Optional[str] = None
    created_at: datetime


class SupportTicketList(BaseModel):
    tickets: list[SupportTicketRead]
