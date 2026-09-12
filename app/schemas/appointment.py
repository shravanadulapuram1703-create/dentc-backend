"""Appointment + lab-vendor DTOs (Lab Tracking, LAB-1..11).

``AppointmentCreate`` / ``AppointmentUpdate`` are the factory-generated shapes
with the lab-field rules the DB could only enforce with a 500:

* ``lab_dds`` — ``max_length=100`` (LAB-6; the column is ``String(100)``).
* ``lab_cost`` — ``>= 0``, ``max_digits=10``, ``decimal_places=2`` (LAB-7; the
  column is ``Numeric(10, 2)`` and a negative cost is not a cost).
* ``extra="forbid"`` (LAB-10) — an unknown key is a 422 naming it, so a client
  can no longer send ``short_notice`` and read a 200 back with nothing stored.

``AppointmentRead`` is the generated read plus ``lab_vendor_name`` and the
derived ``lab_status`` (``lab_tracking_service.enrich_appointments``), so no
client has to re-derive the status the list filter evaluates.
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, create_model

from app.core.datetimes import UtcDatetime
from app.db import models as m
from app.schemas.common import PageMeta
from app.schemas.factory import build_schemas

LabStatus = Literal["not_sent", "sent", "overdue", "received"]
# The list filter also accepts the legacy Lab Report review filter "not
# received" (= sent OR overdue).
LabStatusFilter = Literal["not_sent", "sent", "overdue", "received", "not_received"]

# ── appointments ─────────────────────────────────────────────────────────────
_appt_create, _appt_update, _ = build_schemas(m.Appointment, "AppointmentBase")


class AppointmentCreate(_appt_create):  # type: ignore[valid-type, misc]
    model_config = ConfigDict(extra="forbid")

    lab_dds: Optional[str] = Field(None, max_length=100)
    lab_cost: Optional[Decimal] = Field(None, ge=0, max_digits=10, decimal_places=2)


class AppointmentUpdate(_appt_update):  # type: ignore[valid-type, misc]
    model_config = ConfigDict(extra="forbid")

    lab_dds: Optional[str] = Field(None, max_length=100)
    lab_cost: Optional[Decimal] = Field(None, ge=0, max_digits=10, decimal_places=2)


_appt_read_base = build_schemas(m.Appointment, "AppointmentFull")[2]
AppointmentRead = create_model(
    "AppointmentRead", __base__=_appt_read_base,
    # LAB-1: resolved from ``labs`` in one batched query per response.
    lab_vendor_name=(Optional[str], None),
    # LAB-2: the same derivation the ``?lab_status=`` filter evaluates. Null
    # when ``has_lab`` is false.
    lab_status=(Optional[LabStatus], None),
)

# ── labs catalog ─────────────────────────────────────────────────────────────
_lab_create, LabUpdate, _ = build_schemas(m.Lab, "Lab")


class LabCreate(_lab_create):  # type: ignore[valid-type, misc]
    """``allow_duplicate_name`` overrides the 409 ``duplicate_lab_name`` guard
    (the INS-PT-13 shape: two active vendors with the same name is almost
    always a double-entry, but "Smile Lab" twice in two states is legitimate).
    """

    allow_duplicate_name: bool = False


_lab_read_base = build_schemas(m.Lab, "LabFull")[2]
LabRead = create_model(
    "LabRead", __base__=_lab_read_base,
    created_by_name=(Optional[str], None),
    updated_by_name=(Optional[str], None),
)


class LabNameAvailability(BaseModel):
    name: str
    available: bool
    conflicts: list[dict] = Field(default_factory=list, description="Active labs with the same name")


# ── office-wide lab-case view (LAB-2 / LAB-5) ────────────────────────────────
class LabCaseRead(BaseModel):
    """One lab case = one ``has_lab`` appointment, denormalised for the grid."""

    id: str
    office_id: int
    office_name: Optional[str] = None
    patient_id: Optional[int] = None
    patient_name: Optional[str] = None
    chart_no: Optional[str] = None
    patient_phone: Optional[str] = None
    provider_id: Optional[str] = None
    provider_name: Optional[str] = None
    date: date
    start_time: time
    status: str
    is_archived: bool = False
    procedure_label: Optional[str] = None
    lab_vendor_id: Optional[int] = None
    lab_vendor_name: Optional[str] = None
    lab_dds: Optional[str] = None
    lab_cost: Optional[Decimal] = None
    lab_short_notice: bool = False
    lab_sent_on: Optional[date] = None
    lab_due_on: Optional[date] = None
    lab_received_on: Optional[date] = None
    lab_status: LabStatus
    # Days past ``lab_due_on`` (positive = overdue) for the sent-not-received cases.
    days_overdue: Optional[int] = None
    updated_at: Optional[UtcDatetime] = None


class LabStatusCounts(BaseModel):
    """Per-status counts over the same filter set *minus* ``lab_status`` — the
    review-filter tabs stay accurate while one of them is selected."""

    all: int = 0
    not_sent: int = 0
    sent: int = 0
    overdue: int = 0
    received: int = 0
    not_received: int = 0


class LabCaseListResponse(BaseModel):
    items: list[LabCaseRead]
    meta: PageMeta
    counts: LabStatusCounts
    # Sum of ``lab_cost`` over every case matching the filters (all pages).
    total_cost: Decimal = Decimal("0")
    # The date the status derivation used ("today" in the office's timezone
    # when one office is selected, else UTC).
    as_of: date


class LabCostReportRow(BaseModel):
    key: Optional[str] = None
    label: str
    case_count: int
    total_cost: Decimal


class LabCostReport(BaseModel):
    """LAB-4: the legacy Lab Cost Report — totals by date range, grouped."""

    date_from: Optional[date] = None
    date_to: Optional[date] = None
    date_basis: Literal["appointment", "sent", "due", "received"]
    group_by: Literal["vendor", "provider", "office", "month", "dds"]
    rows: list[LabCostReportRow]
    case_count: int
    total_cost: Decimal
