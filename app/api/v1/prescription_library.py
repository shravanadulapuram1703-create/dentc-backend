"""Prescriptions Setup supplements (Setup -> Prescriptions; RX-2 / RX-4 of
``docs/pick-list/pick_list_setup_backend_devreport.md``).

The generic CRUD (``/prescription-library``) is registered from the registry
with ``PrescriptionLibraryCRUD`` as its write authority. These two literal paths
are what the editor needs *around* a save:

* ``GET /prescription-library/limits`` — the caps and the duplicate rule the API
  enforces, so the "Allowed 240 Characters" counter is driven by the server.
* ``GET /prescription-library/availability`` — "is this drug already in the
  library?" in one indexed lookup instead of paging the whole list on every
  keystroke; ``taken`` is exactly what ``POST``/``PATCH`` will 409 on.

Mounted before the generic router so the literal segments win over ``/{item_id}``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession, TenantId
from app.schemas.procedure_setup import (
    PrescriptionAvailabilityResult,
    PrescriptionLibraryLimits,
)
from app.services import prescription_library_service as svc

router = APIRouter(prefix="/prescription-library", tags=["Procedures"])


@router.get(
    "/limits",
    response_model=PrescriptionLibraryLimits,
    operation_id="get_prescription_library_limits",
    summary="Field caps + duplicate rule the API enforces on the Rx library (RX-2/RX-4)",
)
def get_limits():
    """``sig_max_length`` is the legacy 240-character rule, now a 422
    ``sig_too_long`` server-side; ``duplicate_key_fields`` + ``override_field``
    describe the 409 ``duplicate_prescription`` guard."""
    return svc.limits()


@router.get(
    "/availability",
    response_model=PrescriptionAvailabilityResult,
    operation_id="check_prescription_library_availability",
    summary="Check whether a drug name + dispense + sig is already in the library (RX-4)",
)
def check_availability(
    db: DbSession,
    tenant_id: TenantId,
    drug_name: Annotated[str, Query(description="Drug name to test (trimmed, case-insensitive)")],
    dispense: Annotated[str | None, Query(description="Dispense text (blank == omitted)")] = None,
    sig: Annotated[str | None, Query(description="Sig text (blank == omitted)")] = None,
    exclude_id: Annotated[
        int | None, Query(description="Ignore this row (the one being edited)")
    ] = None,
):
    """``taken`` means an **active** row with the identical name + dispense + sig
    exists, so a save will 409 unless ``allow_duplicate`` is sent.
    ``inactive_matches`` (same configuration, deactivated — offer to reactivate)
    and ``same_name_matches`` (same drug, different dispense/sig — the
    *Chlorhexidine* case) are reported and never block."""
    return svc.availability(
        db, tenant_id, drug_name=drug_name, dispense=dispense, sig=sig, exclude_id=exclude_id
    )
