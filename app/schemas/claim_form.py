"""ADA Dental Claim Form (2024) response models (ADA-BE-1..14).

One nested model per form region, item numbers in the field descriptions, so
the OpenAPI/Orval client documents which box every value prints in. Every
derived value carries a ``*_source`` sibling and the form carries
``warnings[]`` — a print that silently fell back is a rejected claim.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.datetimes import UtcDatetime
from app.schemas.signature import ClaimSignatureSlot


class ClaimFormAddress(BaseModel):
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None


class ClaimFormHeader(BaseModel):
    transaction_type: str = Field(description="Item 1: statement | predetermination | epsdt")
    is_preauth: bool
    is_epsdt: bool = Field(description="Item 1 EPSDT / Title XIX (ADA-BE-2)")
    predetermination_number: str | None = Field(None, description="Item 2")


class ClaimFormPayer(ClaimFormAddress):
    carrier_id: int | None = None
    name: str | None = Field(None, description="Item 3")
    payer_id: str | None = Field(None, description="Item 3a")


class ClaimFormSubscriber(ClaimFormAddress):
    subscriber_id: int | None = None
    last_name: str | None = None
    first_name: str | None = None
    middle_initial: str | None = None
    suffix: str | None = Field(None, description="ADA-BE-10")
    dob: dt.date | None = None
    sex: str = Field("U", description="M | F | U")
    member_id: str | None = None
    group_number: str | None = None
    employer_name: str | None = None
    relationship: str | None = Field(None, description="stored free text")
    relationship_code: str = Field(description="self | spouse | dependent | other")
    ins_plan_id: int | None = None
    plan_type: str | None = None


class ClaimFormOtherCoverage(BaseModel):
    has_other_coverage: bool = Field(description="Item 4")
    has_other_coverage_source: str = Field(description="stored | derived")
    plan_source: str = Field(description="stored | stored_plan_only | derived | none (ADA-BE-9)")
    subscriber: ClaimFormSubscriber | None = Field(None, description="Items 5–11")
    carrier: ClaimFormPayer | None = Field(None, description="Items 9–11")
    coverage_type: str | None = Field(None, description="dental | medical")


class ClaimFormPatient(ClaimFormAddress):
    patient_id: int
    last_name: str | None = None
    first_name: str | None = None
    middle_initial: str | None = None
    suffix: str | None = None
    dob: dt.date | None = None
    sex: str = "U"
    chart_no: str | None = Field(None, description="Item 23")
    relationship_to_subscriber: str = Field(description="Item 18")


class ClaimFormServiceLine(BaseModel):
    line_no: int
    page_no: int = Field(description="1-based; ten lines per form (rule E)")
    procedure_id: str
    date_of_service: dt.date | None = Field(None, description="Item 24")
    area_of_oral_cavity: str | None = Field(None, description="Item 25 (ADA two-digit code)")
    tooth_system: str = Field("JP", description="Item 26")
    tooth: str | None = Field(None, description="Item 27")
    surface: str | None = Field(None, description="Item 28")
    procedure_code: str = Field(description="Item 29")
    diagnosis_pointers: str | None = Field(None, description="Item 29a (ADA-BE-3)")
    quantity: int = Field(1, description="Item 29b (ADA-BE-4)")
    description: str | None = Field(None, description="Item 30")
    fee: Decimal = Field(description="Item 31")
    provider_id: str | None = None


class ClaimFormFees(BaseModel):
    lines_total: Decimal
    other_fees: Decimal | None = Field(None, description="Item 31a (ADA-BE-5)")
    total_fee: Decimal = Field(description="Item 32 = lines + other fees")


class ClaimFormMissingTeeth(BaseModel):
    teeth: list[str] = Field(description="Item 33: permanent Universal ids")
    source: str = Field(description="claim | chart (ADA-BE-6)")


class ClaimFormDiagnosis(BaseModel):
    qualifier: str = Field(description="Item 34: AB = ICD-10-CM, B = ICD-9-CM")
    codes: dict[str, str | None] = Field(description="Item 34a: A–D")


class ClaimFormAuthorizations(BaseModel):
    signature_on_file: bool = Field(description="Item 36")
    signature_source: str = Field(description="claim_consent_signature | claim | none (ADA-BE-7)")
    consent_signature_id: int | None = None
    consent_signed_at: UtcDatetime | None = None
    assignment_of_benefits: bool = Field(description="Item 37")
    # SIG-16: the three resolved signature lines (images only on the PDF path /
    # ``?include_signature_images=true``).
    signatures: ClaimFormSignatures | None = None


class ClaimFormSignatures(BaseModel):
    item_36: ClaimSignatureSlot
    item_37: ClaimSignatureSlot
    item_53: ClaimSignatureSlot


class ClaimFormEnclosures(BaseModel):
    radiographs: int = 0
    oral_images: int = 0
    models: int = 0
    narratives: int = 0
    perio_charts: int = 0
    other: int = 0
    attachments_enclosed: bool = False
    required_attachment_types: list[str] = Field(default_factory=list)
    missing_attachment_types: list[str] = Field(default_factory=list)


class ClaimFormAncillary(BaseModel):
    place_of_treatment: str = Field(description="Item 38 (CMS POS code)")
    place_of_treatment_source: str
    enclosures: ClaimFormEnclosures = Field(description="Item 39 (derived, PROC-7d)")
    date_last_srp: dt.date | None = Field(None, description="Item 39a (ADA-BE-2)")
    date_last_srp_source: str = Field(description="claim | derived | none")
    is_ortho: bool = Field(description="Item 40")
    ortho_appliance_date: dt.date | None = Field(None, description="Item 41")
    ortho_months_remaining: int | None = Field(None, description="Item 42")
    prosthesis_replacement: bool = Field(description="Item 43")
    prosthesis_prior_date: dt.date | None = Field(None, description="Item 44")
    accident_type: str | None = Field(None, description="Item 45: occupational | auto | other")
    accident_date: dt.date | None = Field(None, description="Item 46")
    accident_state: str | None = Field(None, description="Item 47")


class ClaimFormBilling(ClaimFormAddress):
    name: str | None = Field(None, description="Item 48")
    npi: str | None = Field(None, description="Item 49")
    npi_type: str = Field(description="2 = organisation (offices.npi), 1 = individual (ADA-BE-8)")
    npi_source: str = Field(description="office | billing_provider")
    license: str | None = Field(None, description="Item 50")
    tax_id: str | None = Field(None, description="Item 51")
    phone: str | None = Field(None, description="Item 52")
    additional_provider_id: str | None = Field(None, description="Item 52a")
    provider_id: str | None = None
    provider_source: str = Field(description="claim | office | treating | none")
    office_id: int | None = None


class ClaimFormTreating(BaseModel):
    provider_id: str | None = None
    provider_source: str = Field(description="claim | procedures | preferred_provider | none (ADA-BE-12)")
    name: str | None = Field(None, description="Item 53")
    is_locum_tenens: bool = Field(description="Item 53a (ADA-BE-2)")
    npi: str | None = Field(None, description="Item 54")
    license: str | None = Field(None, description="Item 55")
    tax_id: str | None = None
    specialty: str | None = None
    location: ClaimFormAddress = Field(description="Item 56")
    location_source: str = Field(description="treatment_address | office_address | none (ADA-BE-13)")
    specialty_code: str = Field(description="Item 56a taxonomy code (ADA-BE-14)")
    specialty_code_source: str = Field(description="stored | specialty | default")
    specialty_label: str | None = None
    phone: str | None = Field(None, description="Item 57")
    additional_provider_id: str | None = Field(None, description="Item 58")


class ClaimFormWarning(BaseModel):
    code: str
    item: str
    message: str
    line_no: int | None = None
    procedure_id: str | None = None
    provider_ids: list[str] | None = None


class AdaClaimForm(BaseModel):
    """Every item of the ADA Dental Claim Form (2024) for one claim."""

    form_version: str
    claim_id: str
    claim_number: str | None = None
    patient_id: int
    status: str | None = None
    pages: int
    lines_per_page: int
    header: ClaimFormHeader
    payer: ClaimFormPayer
    other_coverage: ClaimFormOtherCoverage
    subscriber: ClaimFormSubscriber
    patient: ClaimFormPatient
    service_lines: list[ClaimFormServiceLine]
    fees: ClaimFormFees
    missing_teeth: ClaimFormMissingTeeth
    diagnosis: ClaimFormDiagnosis
    remarks: str | None = Field(None, description="Item 35")
    authorizations: ClaimFormAuthorizations
    ancillary: ClaimFormAncillary
    billing: ClaimFormBilling
    treating: ClaimFormTreating
    warnings: list[ClaimFormWarning] = Field(default_factory=list)


class ClaimFormBatchRequest(BaseModel):
    claim_ids: list[str] = Field(min_length=1, max_length=200, description="Rendered in this order, one form each")
    mode: str = Field("form", pattern="^(form|overlay)$")
    offset_x: float = Field(0, ge=-72, le=72, description="printer calibration, pt")
    offset_y: float = Field(0, ge=-72, le=72)


class ToothStatus(BaseModel):
    tooth: str
    status: str = Field(description="present | missing | extracted | implant")
    source: str | None = Field(None, description="chart_condition | patient_procedure")
    date: dt.date | None = None
    condition_code: str | None = None
    procedure_code: str | None = None


class PatientToothStatus(BaseModel):
    patient_id: int
    teeth: list[ToothStatus]
    missing_teeth: list[str] = Field(description="the Item 33 set: every non-present permanent tooth")


class ProviderTaxonomyCode(BaseModel):
    code: str
    label: str
    keywords: list[str]
