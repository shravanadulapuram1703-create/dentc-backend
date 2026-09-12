"""Generated Patient schemas, defined once and shared.

Both the CRUD registry (``/patients``) and the composite register endpoint
(``POST /patients/register``) need the ``PatientCreate`` shape. Building it here
once keeps a single named OpenAPI component (``PatientCreate``/``PatientRead``)
instead of two clashing definitions.

``PatientRead`` is the generated read enriched with the resolved office name/code
(LEG-16), populated by ``enrich_service.enrich_patient_office`` — so screens can
display the office by name without a separate ``GET /offices`` fan-out.

GAP-AP-21: ``PatientCreate`` carries ``force_create``. The duplicate guard used
to live only on ``/patients/register``, so the plain ``POST /patients`` — the
endpoint every fallback and import path uses — created duplicates silently.
``PatientCRUD.create`` now runs the same guard and honours the same override, so
the two endpoints answer the same question the same way.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field, create_model

from app.db.models import Patient
from app.schemas.factory import build_schemas

# Create/Update keep the canonical component names; the read is enriched below.
_patient_create_base, PatientUpdate, _ = build_schemas(Patient, "Patient")

PatientCreate = create_model(
    "PatientCreate", __base__=_patient_create_base,
    force_create=(
        bool,
        Field(
            False,
            description=(
                "GAP-AP-21: create even if a strong duplicate match exists (the user "
                "reviewed the 409 `error.details.candidates` and confirmed this is a "
                "new patient). Not a column — consumed by the guard."
            ),
        ),
    ),
)

_patient_read_base = build_schemas(Patient, "PatientFull")[2]
PatientRead = create_model(
    "PatientRead", __base__=_patient_read_base,
    home_office_name=(Optional[str], None),
    home_office_code=(Optional[str], None),
    # PE-4: resolved audit-actor display names (mirrors UserRead), set by
    # enrich_service.enrich_patient_office.
    created_by_name=(Optional[str], None),
    updated_by_name=(Optional[str], None),
    # ADA-BE-7: an active ``claim_consent`` signature exists (ADA Item 36 /
    # 837D CLM09), set by enrich_service.enrich_patient_office.
    has_claim_consent=(bool, False),
)
