"""My Page DTOs (self-service profile, tasks, preferences, notifications)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


# ── MP-1: self-service profile update ────────────────────────────────────────
class UserSelfUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


# ── MP-3: personal tasks ──────────────────────────────────────────────────────
_Priority = Literal["high", "normal", "low"]


class UserTaskCreate(BaseModel):
    title: str
    priority: _Priority = "normal"
    is_done: bool = False
    due_date: Optional[date] = None
    notes: Optional[str] = None


class UserTaskUpdate(BaseModel):
    title: Optional[str] = None
    priority: Optional[_Priority] = None
    is_done: Optional[bool] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None


class UserTaskRead(ORMModel):
    id: int
    user_id: int
    title: str
    priority: str
    is_done: bool
    due_date: Optional[date] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


# ── MP-4: opaque per-user preferences blob ───────────────────────────────────
class PreferencesBlob(BaseModel):
    preferences: dict[str, Any] = Field(default_factory=dict)


# ── MP-6: notifications ───────────────────────────────────────────────────────
class NotificationRead(ORMModel):
    id: int
    category: Optional[str] = None
    title: str
    body: Optional[str] = None
    ref_type: Optional[str] = None
    ref_id: Optional[str] = None
    is_read: bool
    read_at: Optional[datetime] = None
    created_at: datetime


class NotificationList(BaseModel):
    unread_count: int
    items: list[NotificationRead]
