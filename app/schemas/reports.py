"""Reports module schemas — executive summary, trends, AR & aging.

These back the Reports frontend (FE dev-report gaps 1/2/3): server-side
aggregation across a tenant (optionally one office) over a date range, so the FE
no longer fans out CRUD list endpoints and surfaces "truncated sample" warnings.

All money fields are plain ``float`` (the established balance/ledger contract).
Tenancy is enforced in the service by joining ``patients.tenant_id``; the child
financial tables (procedures/payments/claims) carry no ``tenant_id`` of their own.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReportSummary(BaseModel):
    """Executive-dashboard KPIs for a tenant/office over [date_from, date_to].

    ``outstanding_ar`` is cumulative (all-time as of ``date_to``), not bounded by
    ``date_from`` — receivables are a running balance, not a windowed flow.
    """

    production: float = Field(0, description="Σ procedure fees (non-void) in the window")
    collections: float = Field(0, description="Σ patient payments (non-void) in the window")
    new_patients: int = Field(0, description="Patients created in the window")
    active_patients: int = Field(0, description="Active patients (point-in-time, not windowed)")
    scheduled_appointments: int = Field(0, description="Non-cancelled, non-blocked appts in the window")
    insurance_receivables: float = Field(
        0, description="Σ (total_billed − total_paid) of outstanding active claims"
    )
    outstanding_ar: float = Field(
        0, description="Practice-wide AR as of date_to (charges − payments − adjustments)"
    )
    office_id: int | None = Field(None, description="Office scope, or null for all offices")
    date_from: str
    date_to: str
    as_of: str = Field(..., description="UTC timestamp the summary was computed")


class TrendBucket(BaseModel):
    period: str = Field(..., description="ISO date of the bucket start (day/week/month)")
    production: float = 0
    collections: float = 0
    new_patients: int = 0


class ReportTrends(BaseModel):
    interval: str = Field(..., description="day | week | month")
    buckets: list[TrendBucket]
    office_id: int | None = None
    date_from: str
    date_to: str
    as_of: str


class AccountsReceivable(BaseModel):
    """Practice-wide outstanding balance as of a point in time (FE gap 2)."""

    total_ar: float = Field(0, description="charges − payments − adjustments, all-time ≤ as_of")
    patient_ar: float = Field(0, description="total_ar − insurance_ar (patient-responsible portion)")
    insurance_ar: float = Field(0, description="Outstanding expected-insurance portion (best-effort)")
    office_id: int | None = None
    as_of: str


class Aging(BaseModel):
    """Receivables aged by the age of each charge's date_of_service (FE gap 3).

    Mirrors the per-patient ``/patients/{id}/balance`` aging (gross-charge dating,
    "Option A") so practice-wide and per-patient views are consistent. Net-of-
    payment FIFO aging is a future refinement (see backend dev report).
    """

    current: float = Field(0, description="0–30 days")
    d30: float = Field(0, description="31–60 days")
    d60: float = Field(0, description="61–90 days")
    d90: float = Field(0, description="91–120 days")
    d120_plus: float = Field(0, description="120+ days")
    total: float = Field(0, description="Σ of all buckets")
    office_id: int | None = None
    as_of: str
