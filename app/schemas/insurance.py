"""Insurance Setup DTOs (insurance dev-report INS-2, patient-insurance INS-PT-*).

The carrier ``Read`` schema adds a typed ``is_dental`` discriminator derived from
the brittle legacy ``carrier_type`` string (``"True"``/``"False"``), so the
frontend has a stable boolean to branch on instead of guessing.

INS-PT-12 makes that boolean **writable** as well: send ``is_dental`` and the
server stores the canonical ``carrier_type``. Both fields stay accepted (the form
binds to ``carrier_type`` 1:1 today), and the vocabulary that decides which is
which lives once, in ``app.services.insurance_service``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, computed_field, create_model

from app.db.models import Employer, InsuranceCarrier, InsurancePlan
from app.schemas.factory import build_schemas
from app.services.insurance_service import carrier_is_dental

_CarrierCreate, _CarrierUpdate, _CarrierReadBase = build_schemas(
    InsuranceCarrier, "InsuranceCarrier"
)


class _CarrierWriteMixin(BaseModel):
    # INS-PT-12: the typed alternative to ``carrier_type``. When present it wins,
    # because it is the field that cannot have been mistyped.
    is_dental: bool | None = None
    # INS-PT-13: quick-add creates a second carrier under an existing name only
    # when the caller says so; otherwise the create is a 409 the dialog can act on.
    allow_duplicate_name: bool = False


class InsuranceCarrierCreate(_CarrierCreate, _CarrierWriteMixin):  # type: ignore[valid-type, misc]
    pass


class InsuranceCarrierUpdate(_CarrierUpdate, _CarrierWriteMixin):  # type: ignore[valid-type, misc]
    pass


class InsuranceCarrierRead(_CarrierReadBase):  # type: ignore[valid-type, misc]
    @computed_field(  # type: ignore[prop-decorator]
        description="Typed discriminator derived from carrier_type (True/dental → true)."
    )
    @property
    def is_dental(self) -> bool | None:
        return carrier_is_dental(self.carrier_type)


# ── Employers (INS-PT-13) ────────────────────────────────────────────────────
_EmployerCreate, _EmployerUpdate, EmployerRead = build_schemas(Employer, "Employer")


class EmployerCreate(_EmployerCreate):  # type: ignore[valid-type, misc]
    allow_duplicate_name: bool = False


class EmployerUpdate(_EmployerUpdate):  # type: ignore[valid-type, misc]
    allow_duplicate_name: bool = False


# ── Plans (INS-PT-8/9/12/18/19) ──────────────────────────────────────────────
_PlanCreate, _PlanUpdate, _PlanReadBase = build_schemas(InsurancePlan, "InsurancePlanBase")


class InsurancePlanCreate(_PlanCreate):  # type: ignore[valid-type, misc]
    """INS-PT-19: an active plan on the same carrier + group number is a 409.

    ``allow_duplicate_group`` is the API half of the dialog's "override" button —
    two offices can legitimately hold separate plans on one group, so the server
    refuses the *accidental* duplicate rather than the duplicate.
    """

    allow_duplicate_group: bool = False


class InsurancePlanUpdate(_PlanUpdate):  # type: ignore[valid-type, misc]
    allow_duplicate_group: bool = False


# INS-PT-9/18: a plan list returns carrier_id/employer_id only, so a 20-row grid
# page cost up to 40 single-id GETs (each with a preflight) just to render two
# name columns. INS-PT-8 adds the Created/Modified actors the grid renders as
# "date + user". ``is_dental`` rides along because the plan form re-derives the
# Dental/Medical selector from the carrier every time a plan is opened or copied.
InsurancePlanRead = create_model(
    "InsurancePlanRead", __base__=_PlanReadBase,
    carrier_name=(Optional[str], None),
    payer_id=(Optional[str], None),
    employer_name=(Optional[str], None),
    is_dental=(Optional[bool], None),
    created_by_name=(Optional[str], None),
    updated_by_name=(Optional[str], None),
)


# ── INS-PT-5: eligibility "Update Status" stamp ──────────────────────────────
class EligibilityVerifyRequest(BaseModel):
    elig_status: str | None = None  # defaults to "verified" server-side
    notes: str | None = None


class EligibilityVerifyResult(BaseModel):
    subscriber_id: int
    elig_status: str | None = None
    elig_verified_on: datetime | None = None
    elig_verified_by: str | None = None
    realtime_supported: bool | None = None
    method: str  # "realtime" | "manual"


# ── INS-PT-20/21: "is this group taken?" ─────────────────────────────────────
class PlanMatch(BaseModel):
    id: int
    group_number: str | None = None
    carrier_id: int | None = None
    carrier_name: str | None = None
    payer_id: str | None = None
    employer_id: int | None = None
    employer_name: str | None = None
    plan_type: str | None = None
    coverage_type: str | None = None
    is_active: bool = True


class GroupAvailabilityResult(BaseModel):
    group_number: str
    carrier_id: int | None = None
    #: True when an **active** plan on the same carrier already holds this group.
    taken: bool
    matches: list[PlanMatch] = []
    #: INS-PT-21 — soft-deleted plans holding the number. Never blocking.
    inactive_matches: list[PlanMatch] = []
    #: Same group number under a different carrier. Never blocking.
    other_carrier_matches: list[PlanMatch] = []


# ── INS-PT-13: "is this carrier/employer name taken?" ────────────────────────
class NameMatch(BaseModel):
    id: int
    name: str
    is_active: bool = True


class NameAvailabilityResult(BaseModel):
    name: str
    taken: bool
    matches: list[NameMatch] = []
    inactive_matches: list[NameMatch] = []


__all__ = [
    "EligibilityVerifyRequest",
    "EligibilityVerifyResult",
    "EmployerCreate",
    "EmployerRead",
    "EmployerUpdate",
    "GroupAvailabilityResult",
    "InsuranceCarrierCreate",
    "InsuranceCarrierRead",
    "InsuranceCarrierUpdate",
    "InsurancePlanCreate",
    "InsurancePlanRead",
    "InsurancePlanUpdate",
    "NameAvailabilityResult",
    "NameMatch",
    "PlanMatch",
]
