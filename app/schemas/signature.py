"""Signature-capture DTOs (docs/signature/topaz_signature_backend_devreport.md).

``PatientSignatureRead`` / ``PatientConsentRead`` are the generated reads with
``sig_string`` **excluded** (SIG-4) and the enrichment fields
``signature_service.enrich_patient_*`` populate. ``SignatureVectorRead`` is the
one shape that carries the clear SigString, returned only by the audited
``…/sig-string`` routes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, create_model

from app.core.datetimes import UtcDatetime
from app.db.models import PatientConsent, PatientSignature, SignatureAuditEvent
from app.schemas.factory import build_schemas

# ── patient_signatures ───────────────────────────────────────────────────────
PatientSignatureCreate, PatientSignatureUpdate, _ = build_schemas(PatientSignature, "PatientSignature")

_signature_read_base = build_schemas(
    PatientSignature, "PatientSignatureFull", read_exclude=("sig_string",)
)[2]
PatientSignatureRead = create_model(
    "PatientSignatureRead", __base__=_signature_read_base,
    # Populated by signature_service.enrich_patient_signatures.
    has_image=(bool, False),
    # SIG-9: true when the list was called with ``include_image=false``.
    image_omitted=(bool, False),
    has_sig_string=(bool, False),
    # A legacy row still holding a raw SigString in ``signature_data`` (see
    # scripts/migrate_legacy_sigstrings.py) — the FE cannot render it as <img>.
    legacy_sig_string_in_image=(bool, False),
    # SIG-7: signed | stale | unverifiable | voided | superseded | null (unbound).
    signature_status=(Optional[str], None),
    # CS-8: topaz | drawn | legacy | unknown, derived from device_source.
    capture_method=(Optional[str], None),
    created_by_name=(Optional[str], None),
    signed_by_name=(Optional[str], None),
    voided_by_name=(Optional[str], None),
)

# ── patient_consents ─────────────────────────────────────────────────────────
PatientConsentCreate, PatientConsentUpdate, _ = build_schemas(PatientConsent, "PatientConsent")

_consent_read_base = build_schemas(
    PatientConsent, "PatientConsentFull", read_exclude=("sig_string",)
)[2]
class ConsentSignatureRead(BaseModel):
    """CS-2: a countersignature line (images only with ``include_image=true``)."""

    id: int
    consent_id: int
    role: str
    signer_user_id: Optional[int] = None
    signer_provider_id: Optional[str] = None
    signer_name: Optional[str] = None
    signed_at: Optional[datetime] = None
    captured_at: Optional[datetime] = None
    device_source: Optional[str] = None
    capture_method: Optional[str] = None
    has_image: bool = False
    signature_data: Optional[str] = None
    signature_len: Optional[int] = None
    has_sig_string: bool = False
    sig_format: Optional[str] = None
    point_count: Optional[int] = None
    stroke_count: Optional[int] = None
    device_vendor: Optional[str] = None
    device_model: Optional[str] = None
    device_serial: Optional[str] = None
    captured_user_agent: Optional[str] = None
    content_hash: Optional[str] = None
    is_active: bool = True
    voided_at: Optional[datetime] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None


PatientConsentRead = create_model(
    "PatientConsentRead", __base__=_consent_read_base,
    has_sig_string=(bool, False),
    # SIG-7: signed | stale | unverifiable | unsigned | declined | voided.
    signature_status=(Optional[str], None),
    # CS-5: ``?include_signature=false`` strips the image and says so.
    has_image=(bool, False),
    image_omitted=(bool, False),
    # CS-8: the shared capture vocabulary, derived.
    capture_method=(Optional[str], None),
    # CS-2: countersign lines (never with images inline).
    countersigns=(list[ConsentSignatureRead], []),
)

# ── audit trail (SIG-8) ──────────────────────────────────────────────────────
_, _, SignatureAuditEventRead = build_schemas(SignatureAuditEvent, "SignatureAuditEvent")


class SignatureVectorRead(BaseModel):
    """SIG-4: the clear Topaz SigString for one signature. Admin-only, audited."""

    entity_type: str = Field(..., examples=["patient_signature", "patient_consent", "user"])
    entity_id: int
    sig_string: Optional[str] = None
    sig_string_readable: bool = Field(
        False, description="False when the row holds a token the current key cannot open"
    )
    sig_format: Optional[str] = None
    sig_compression: Optional[int] = None
    sig_encryption: Optional[int] = None
    point_count: Optional[int] = None
    stroke_count: Optional[int] = None
    device_source: Optional[str] = None
    device_vendor: Optional[str] = None
    device_model: Optional[str] = None
    device_serial: Optional[str] = None
    signed_at: Optional[UtcDatetime] = None
    encrypted_at_rest: bool = False


class SignatureCaptureRules(BaseModel):
    """``GET /metadata/signature-capture`` — the vocabularies and limits the
    API enforces, so the pad diagnostics page reads them from one place."""

    sig_formats: list[str]
    sig_compression_values: dict[str, str]
    sig_encryption_values: dict[str, str]
    device_sources: list[str]
    legacy_device_source: str
    legacy_device_sources: list[str]
    signature_methods: list[str]
    signature_statuses: list[str]
    audit_events: list[str]
    min_point_count: int
    min_stroke_count: int
    max_signature_chars: int
    max_sig_string_chars: int
    sig_string_encrypted_at_rest: bool
    sig_string_on_read_models: bool
    sig_string_endpoints: list[str]
    canonical_user_signature_write: str
    document_binding: dict[str, str]
    capture_methods: list[str]
    capture_method_rule: str
    consent_countersign_roles: list[str]
    consent_signed_at_tolerance_minutes: int
    consent_content_hash: str
    consent_signed_rendition: str
    # Round 2 (SIG-12/13/14/15/16).
    provider_signature_write: str
    signature_types: list[str]
    claim_signature_items: dict[str, list[str]]
    claim_signature_resolution: list[str]
    signer_relationships: list[str]
    item_53_attester: str


class ClaimSignatureSlot(BaseModel):
    """One of the ADA form's three signature lines as resolved for a claim (SIG-16)."""

    signature_id: Optional[int] = None
    source: Optional[str] = Field(None, description="claim | patient | provider | user | null")
    signature_type: Optional[str] = None
    signed_at: Optional[datetime] = None
    signer_name: Optional[str] = None
    signer_relationship: Optional[str] = None
    signer_provider_id: Optional[str] = None
    signed_by_user_id: Optional[int] = None
    has_image: bool = False
    legacy_sig_string_only: bool = Field(
        False, description="A legacy SigString-only row: on file but not printable"
    )
    signature_data: Optional[str] = Field(None, description="Only with include_image=true")
    printed_name: Optional[str] = None


class ClaimSignaturesRead(BaseModel):
    claim_id: str
    patient_id: int
    treating_provider_id: Optional[str] = None
    item_36: ClaimSignatureSlot
    item_37: ClaimSignatureSlot
    item_53: ClaimSignatureSlot


class SignatureCaptureFields(BaseModel):
    """The Topaz block as a reusable request mixin (SIG-1/2/3/8). Every value is
    optional: the on-screen pad sends only ``signature_data`` + ``device_source``."""

    sig_string: Optional[str] = Field(
        None, description="Topaz SigString — clear text, lossless; encrypted at rest"
    )
    sig_format: Optional[str] = Field(None, examples=["topaz_sigstring_v1"], max_length=24)
    sig_compression: Optional[int] = Field(None, description="0 none | 1 lossless | 2 lossy")
    sig_encryption: Optional[int] = Field(None, description="0 clear | 1 DES | 2 high")
    point_count: Optional[int] = None
    stroke_count: Optional[int] = None
    device_vendor: Optional[str] = Field(None, examples=["topaz"], max_length=20)
    device_model: Optional[str] = Field(None, examples=["T-L(BK)462", "T-LBK755SE"], max_length=40)
    device_serial: Optional[str] = Field(None, max_length=40)
    captured_user_agent: Optional[str] = Field(
        None, max_length=255, description="Workstation hint; defaults to the request User-Agent"
    )


class ProviderSignatureUpdate(SignatureCaptureFields):
    """SIG-14: ``PUT /providers/{id}/signature`` — same block as the user store."""

    signature_data: str = Field(..., description="Base64 / data-URL signature image")
    signature_len: Optional[int] = None
    device_source: Optional[str] = Field(None, max_length=20, examples=["topaz", "web-pad"])
    signed_at: Optional[datetime] = None


class ProviderSignatureRead(BaseModel):
    provider_id: str
    #: provider | user — which store answered (``GET …?resolve=true`` falls back
    #: to the provider's linked user account).
    source: Optional[str] = None
    user_id: Optional[int] = None
    signature_data: Optional[str] = None
    signature_len: Optional[int] = None
    device_source: Optional[str] = None
    capture_method: Optional[str] = None
    updated_at: Optional[datetime] = None
    signed_at: Optional[datetime] = None
    has_sig_string: bool = False
    sig_string: Optional[str] = None
    sig_format: Optional[str] = None
    sig_compression: Optional[int] = None
    sig_encryption: Optional[int] = None
    point_count: Optional[int] = None
    stroke_count: Optional[int] = None
    device_vendor: Optional[str] = None
    device_model: Optional[str] = None
    device_serial: Optional[str] = None
    captured_user_agent: Optional[str] = None
