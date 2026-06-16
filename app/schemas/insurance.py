"""Insurance Setup DTOs (insurance dev-report INS-2).

The carrier ``Read`` schema adds a typed ``is_dental`` discriminator derived from
the brittle legacy ``carrier_type`` string (``"True"``/``"False"``), so the
frontend has a stable boolean to branch on instead of guessing. ``carrier_type``
remains the writable field (form binds to it 1:1); ``is_dental`` is read-only.
"""

from __future__ import annotations

from pydantic import computed_field

from app.db.models import InsuranceCarrier
from app.schemas.factory import build_schemas

InsuranceCarrierCreate, InsuranceCarrierUpdate, _CarrierReadBase = build_schemas(
    InsuranceCarrier, "InsuranceCarrier"
)

# carrier_type values that denote a *medical* carrier (everything else → dental).
_MEDICAL_TOKENS = {"false", "medical", "m", "0", "f", "no"}


class InsuranceCarrierRead(_CarrierReadBase):  # type: ignore[valid-type, misc]
    @computed_field(  # type: ignore[prop-decorator]
        description="Typed discriminator derived from carrier_type (True/dental → true)."
    )
    @property
    def is_dental(self) -> bool | None:
        ct = self.carrier_type
        if ct is None:
            return None
        return ct.strip().lower() not in _MEDICAL_TOKENS
