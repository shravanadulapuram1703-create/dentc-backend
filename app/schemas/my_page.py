"""My Page DTOs (self-service profile, tasks, preferences, notifications)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.core.datetimes import UtcDatetime


# ── MP-1: self-service profile update ────────────────────────────────────────
class UserSelfUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    # OFF-SCOPE-3: the working office + default patient are writable here so the
    # switcher / patient selection restore across devices. ``current_office_id``
    # is validated against the caller's ``user_offices`` (403 if not assigned);
    # ``last_patient_id`` against the tenant (null if missing/archived). Both
    # accept an explicit ``null`` to clear (a PATCH that omits them leaves them).
    current_office_id: Optional[int] = None
    last_patient_id: Optional[int] = None


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
    created_at: UtcDatetime
    updated_at: Optional[UtcDatetime] = None


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
    read_at: Optional[UtcDatetime] = None
    created_at: UtcDatetime


class NotificationList(BaseModel):
    unread_count: int
    items: list[NotificationRead]
