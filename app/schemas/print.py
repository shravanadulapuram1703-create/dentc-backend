"""Wire models for the patient print module (PRINT-1/2/6)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class OfficeLetterhead(BaseModel):
    """PRINT-2: what prints at the top of every report for this office — the
    same resolution ``print_service.resolve_letterhead`` uses for the PDFs.

    ``logo_source`` says where the logo came from: ``office`` (the office's own
    Statement-tab upload), ``tenant`` (the practice logo from Account Info) or
    ``none`` (the office opted out, or nothing is uploaded)."""

    name: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    logo_url: Optional[str] = None
    logo_source: str = "none"


class DayTotals(BaseModel):
    """PRINT-6 / CHG-7: the Transactions Entry dashboard's *Today's* block for
    one date, including the deductible portion the estimate engine would
    consume across the day's charges."""

    patient_id: int
    date: date
    transaction_count: int = 0
    total_charges: Decimal = Decimal("0")
    insurance_estimate: Decimal = Decimal("0")
    patient_estimate: Decimal = Decimal("0")
    estimated_deductible: Decimal = Field(
        Decimal("0"),
        description=(
            "Deductible applied to the day's charges, computed by the estimate engine "
            "against the primary slot's remaining deductible at call time"
        ),
    )
    has_active_coverage: bool = False
