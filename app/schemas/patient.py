"""Generated Patient schemas, defined once and shared.

Both the CRUD registry (``/patients``) and the composite register endpoint
(``POST /patients/register``) need the ``PatientCreate`` shape. Building it here
once keeps a single named OpenAPI component (``PatientCreate``/``PatientRead``)
instead of two clashing definitions.

``PatientRead`` is the generated read enriched with the resolved office name/code
(LEG-16), populated by ``enrich_service.enrich_patient_office`` — so screens can
display the office by name without a separate ``GET /offices`` fan-out.
"""

from __future__ import annotations

from typing import Optional

from pydantic import create_model

from app.db.models import Patient
from app.schemas.factory import build_schemas

# Create/Update keep the canonical component names; the read is enriched below.
PatientCreate, PatientUpdate, _ = build_schemas(Patient, "Patient")

_patient_read_base = build_schemas(Patient, "PatientFull")[2]
PatientRead = create_model(
    "PatientRead", __base__=_patient_read_base,
    home_office_name=(Optional[str], None),
    home_office_code=(Optional[str], None),
    # PE-4: resolved audit-actor display names (mirrors UserRead), set by
    # enrich_service.enrich_patient_office.
    created_by_name=(Optional[str], None),
    updated_by_name=(Optional[str], None),
)
