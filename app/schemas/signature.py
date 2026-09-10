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
    created_by_name=(Optional[str], None),
    signed_by_name=(Optional[str], None),
    voided_by_name=(Optional[str], None),
)

# ── patient_consents ─────────────────────────────────────────────────────────
PatientConsentCreate, PatientConsentUpdate, _ = build_schemas(PatientConsent, "PatientConsent")

_consent_read_base = build_schemas(
    PatientConsent, "PatientConsentFull", read_exclude=("sig_string",)
)[2]
PatientConsentRead = create_model(
    "PatientConsentRead", __base__=_consent_read_base,
    has_sig_string=(bool, False),
    # SIG-7: signed | stale | unverifiable | unsigned | declined | voided.
    signature_status=(Optional[str], None),
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
    signed_at: Optional[datetime] = None
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
