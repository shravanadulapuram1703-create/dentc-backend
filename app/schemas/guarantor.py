"""RP-2/RP-11 guarantor payloads (own module: imported by the patient schema)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

GuarantorKind = Literal["self", "patient", "responsible_party", "unresolved"]


class GuarantorSummary(BaseModel):
    """RP-11: the short form for lists (scheduler feed, patient search)."""

    kind: GuarantorKind
    id: Optional[int] = None
    name: Optional[str] = None
    relationship: Optional[str] = None


class Guarantor(BaseModel):
    """RP-2: the discriminated guarantor payload. ``patient_id`` is set for
    ``self``/``patient``, ``responsible_party_id`` for ``responsible_party``;
    ``unresolved`` carries the raw legacy key in ``legacy_id``."""

    kind: GuarantorKind
    id: Optional[int] = None
    patient_id: Optional[int] = None
    responsible_party_id: Optional[int] = None
    account_id: Optional[int] = None
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    cell_phone: Optional[str] = None
    home_phone: Optional[str] = None
    email: Optional[str] = None
    home_office_id: Optional[int] = None
    relationship: Optional[str] = None
    resp_party_type: Optional[str] = None
    legacy_id: Optional[str] = None
