"""Enriched read models — generated columns + denormalised names/totals (G7/G9).

Each is the factory-generated read model plus a few transient fields the
matching ``enrich_*`` hook populates. Built by subclassing the generated base
under a private name so the public component name (``PatientProcedureRead`` …)
is defined exactly once.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import create_model

from app.db import models as m
from app.schemas.factory import build_schemas

# Create/Update keep the canonical component names; the read is enriched below.
_pp_create, PatientProcedureUpdate, _ = build_schemas(m.PatientProcedure, "PatientProcedure")


class PatientProcedureCreate(_pp_create):  # type: ignore[valid-type, misc]
    """FEE-3: ``fee`` is **optional**.

    ``patient_procedures.fee`` is NOT NULL, so the factory made it required and
    every caller had to price the charge itself — which is exactly how charges
    ended up posting at ``0.00`` when a client fell back to the code's
    ``default_fee``. Omit it and ``PatientProcedureCRUD`` resolves it through
    the same server-side rules ``GET /patients/{id}/fee`` answers with. Sending
    a fee still wins, so no existing caller changes.
    """

    fee: Decimal | None = None
PatientPaymentCreate, PatientPaymentUpdate, _ = build_schemas(m.PatientPayment, "PatientPayment")
InsuranceClaimCreate, InsuranceClaimUpdate, _ = build_schemas(m.InsuranceClaim, "InsuranceClaim")
TreatmentPlanCreate, TreatmentPlanUpdate, _ = build_schemas(m.TreatmentPlan, "TreatmentPlan")

# CHG-5: the applied-money rollup behind the grid's Pat Paid / Pat Adj / Rem Amt
# columns (previously always 0.00 because the read carried no running totals).
_pp_base = build_schemas(m.PatientProcedure, "PatientProcedureFull")[2]
PatientProcedureRead = create_model(
    "PatientProcedureRead", __base__=_pp_base,
    patient_name=(Optional[str], None), provider_name=(Optional[str], None),
    paid_to_date=(Decimal, Decimal("0")),
    insurance_paid_to_date=(Decimal, Decimal("0")),
    adjusted_to_date=(Decimal, Decimal("0")),
    remaining_amount=(Decimal, Decimal("0")),
    # AL-15: the legacy "Outstanding Amount" — fee minus everything applied.
    outstanding_amount=(Decimal, Decimal("0")),
)

_ppay_base = build_schemas(m.PatientPayment, "PatientPaymentFull")[2]
PatientPaymentRead = create_model(
    "PatientPaymentRead", __base__=_ppay_base,
    patient_name=(Optional[str], None), provider_name=(Optional[str], None),
)

_claim_base = build_schemas(m.InsuranceClaim, "InsuranceClaimFull")[2]
InsuranceClaimRead = create_model(
    "InsuranceClaimRead", __base__=_claim_base,
    patient_name=(Optional[str], None), carrier_name=(Optional[str], None),
)

_tp_base = build_schemas(m.TreatmentPlan, "TreatmentPlanFull")[2]
TreatmentPlanRead = create_model(
    "TreatmentPlanRead", __base__=_tp_base,
    patient_name=(Optional[str], None),
    item_count=(int, 0),
    total_fee=(Decimal, Decimal("0")),
    est_insurance=(Decimal, Decimal("0")),
    est_patient=(Decimal, Decimal("0")),
)


# PROV-3: ``providers.role`` is free text ("dentist", "Dentist", "Hygenist", …)
# and ``specialty`` is blank on 96 of 97 migrated rows, so every screen that
# needs "doctors here, hygienists there" had to normalise client-side. The
# derived kind is now published alongside the raw role, so a misspelling in the
# data can no longer put a hygienist in the treating-provider dropdown.
_provider_base = build_schemas(m.Provider, "ProviderFull")[2]
ProviderRead = create_model(
    "ProviderRead", __base__=_provider_base,
    provider_kind=(Optional[str], None),
)
