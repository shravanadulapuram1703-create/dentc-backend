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
PatientProcedureCreate, PatientProcedureUpdate, _ = build_schemas(m.PatientProcedure, "PatientProcedure")
PatientPaymentCreate, PatientPaymentUpdate, _ = build_schemas(m.PatientPayment, "PatientPayment")
InsuranceClaimCreate, InsuranceClaimUpdate, _ = build_schemas(m.InsuranceClaim, "InsuranceClaim")
TreatmentPlanCreate, TreatmentPlanUpdate, _ = build_schemas(m.TreatmentPlan, "TreatmentPlan")

_pp_base = build_schemas(m.PatientProcedure, "PatientProcedureFull")[2]
PatientProcedureRead = create_model(
    "PatientProcedureRead", __base__=_pp_base,
    patient_name=(Optional[str], None), provider_name=(Optional[str], None),
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
