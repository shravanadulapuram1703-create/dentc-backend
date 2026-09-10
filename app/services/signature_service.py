"""Electronic signature capture — the one home for the Topaz block.

Backs ``docs/signature/topaz_signature_backend_devreport.md`` (SIG-1…10). Four
screens share one frontend ``SignatureCapture`` component (Medical History,
Progress Notes, Letters → Consent signing, Security → Users) and three stores
(``patient_signatures``, ``patient_consents``, ``users.signature_*``); this
module is what keeps them from drifting:

* :func:`normalise_capture` — the single validation / defaulting pass every
  write path runs (generic CRUD, ``/medical-history/sign``,
  ``/patient-consents/{id}/sign``, ``PUT /users/…/signature``). It encrypts the
  SigString at rest (SIG-4), defaults ``sig_format``/``device_vendor``/
  ``device_source`` from what was sent, refuses an empty capture (SIG-2) and
  stamps the workstation User-Agent (SIG-8).
* :func:`record_event` — the append-only ``signature_audit_events`` trail.
* Document binding (SIG-7): a ``patient_signatures`` row that names a
  ``progress_note_id`` / ``consent_id`` gets a server-computed ``content_hash``
  and reports ``signature_status`` (``signed`` | ``stale`` | ``unverifiable``)
  the way MH-6 does for medical histories.
* :class:`PatientSignatureCRUD` / :class:`PatientConsentCRUD` — the engine
  hooks so the generic routes cannot route around any of the above.

Why the SigString is never on a read model
------------------------------------------
The rendered JPEG is a picture; the SigString is the biometric record (strokes,
pressure, timing). A list endpoint that ships it to every grid is a disclosure
surface with no consumer. ``GET /patient-signatures/{id}/sig-string`` (admin,
audited as an ``exported`` event) is the only way out.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import client_ip_ctx, user_agent_ctx
from app.crud.base import CRUDBase
from app.db.models import (
    Patient,
    PatientConsent,
    PatientSignature,
    ProgressNote,
    SignatureAuditEvent,
    User,
)

# ── Vocabularies ─────────────────────────────────────────────────────────────
SIG_FORMAT_TOPAZ_V1 = "topaz_sigstring_v1"
SIG_FORMATS = (SIG_FORMAT_TOPAZ_V1,)

#: 0 none | 1 lossless | 2 lossy
SIG_COMPRESSION_VALUES = (0, 1, 2)
#: 0 clear | 1 DES | 2 high. The browser always sends 0 (SIG-4: a key shipped
#: in JS is public) — the *at-rest* encryption is ours, not Topaz's.
SIG_ENCRYPTION_VALUES = (0, 1, 2)

DEVICE_SOURCE_TOPAZ = "topaz"
DEVICE_SOURCE_WEB_PAD = "web-pad"
#: The legacy import wrote ``"0"`` on every migrated SigString row (3,760 on the
#: dev database) and ``"2"`` on the 98 migrated rows that hold a real data-URL
#: image. Both are kept as written — they are the only marker of provenance.
DEVICE_SOURCE_LEGACY = "0"
DEVICE_SOURCE_LEGACY_IMAGE = "2"
DEVICE_SOURCES = (DEVICE_SOURCE_TOPAZ, DEVICE_SOURCE_WEB_PAD, DEVICE_SOURCE_LEGACY,
                  DEVICE_SOURCE_LEGACY_IMAGE)

DEVICE_VENDOR_TOPAZ = "topaz"

#: SIG-5: ``patient_consents.signature_method``. ``topaz`` is the pad capture;
#: ``drawn`` is the on-screen fallback.
SIGNATURE_METHODS = ("drawn", "scanned", "verbal", "topaz")

#: SIG-2: a Topaz pad reports hundreds of sampled points per stroke, so these
#: only reject an empty pad or a single dot. Enforced when the counts are sent.
MIN_POINT_COUNT = 2
MIN_STROKE_COUNT = 1

#: SIG-9 sizing: a 900×300 Topaz JPEG is 20–40 KB of base64; a SigString for a
#: normal signature is a few KB. Caps stop an uncapped TEXT column bloating.
MAX_SIGNATURE_CHARS = 512 * 1024
MAX_SIG_STRING_CHARS = 1024 * 1024

#: ``signature_status`` vocabulary shared by every store that reports it.
SIGNATURE_STATUSES = ("signed", "stale", "unverifiable", "unsigned", "voided", "superseded",
                      "declined")

#: Audit ``event`` vocabulary.
EVENT_CAPTURED = "captured"
EVENT_SUPERSEDED = "superseded"
EVENT_VOIDED = "voided"
EVENT_DECLINED = "declined"
EVENT_REPLACED = "replaced"
EVENT_CLEARED = "cleared"
EVENT_EXPORTED = "sig_string_exported"
EVENTS = (EVENT_CAPTURED, EVENT_SUPERSEDED, EVENT_VOIDED, EVENT_DECLINED, EVENT_REPLACED,
          EVENT_CLEARED, EVENT_EXPORTED)

ENTITY_PATIENT_SIGNATURE = "patient_signature"
ENTITY_PATIENT_CONSENT = "patient_consent"
ENTITY_USER = "user"

#: The capture block as it appears on ``patient_signatures`` / ``patient_consents``.
#: On ``users`` every key is prefixed ``signature_`` except the two that already
#: carry the prefix (``signature_data``/``signature_len``) — see
#: :func:`user_column_for`.
CAPTURE_FIELDS = (
    "signature_data", "signature_len", "device_source",
    "sig_string", "sig_format", "sig_compression", "sig_encryption",
    "point_count", "stroke_count",
    "device_vendor", "device_model", "device_serial",
    "captured_user_agent", "signed_at",
)

_FERNET_PREFIX = "gAAAA"
_HEX_RE = re.compile(r"^[0-9A-Fa-f]+$")
_WS_RE = re.compile(r"\s+")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# ── SIG-4: at-rest encryption ────────────────────────────────────────────────
def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(_FERNET_PREFIX)


def encrypt_sig_string(value: str | None) -> str | None:
    """Fernet-encrypt a clear SigString. Idempotent: an already-encrypted value
    (a token round-tripped through a PATCH) is stored as-is."""
    if not value:
        return None
    if is_encrypted(value):
        return value
    return crypto.encrypt(value)


def decrypt_sig_string(value: str | None) -> str | None:
    """The clear SigString, or ``None`` when the row holds nothing readable.

    A clear-text value (a row written before encryption existed, or a legacy
    import that bypassed the service) is returned verbatim rather than refused —
    the record is still the record. A token the current key cannot open is
    ``None``: returning ciphertext as if it were stroke data would be worse.
    """
    if not value:
        return None
    if not is_encrypted(value):
        return value
    return crypto.decrypt(value)


def looks_like_sigstring(value: str | None) -> bool:
    """The legacy import put raw Topaz SigStrings (``02008C00D5…``) where images
    go. A SigString is hex text; an image is a ``data:`` URL. Used by the
    migration script and by the read model to say "no image here"."""
    if not value:
        return False
    text = value.strip()
    if text.startswith("data:"):
        return False
    return len(text) >= 16 and bool(_HEX_RE.match(text))


# ── Request attribution (SIG-8) ──────────────────────────────────────────────
def request_user_agent() -> str | None:
    ua = user_agent_ctx.get()
    return ua[:255] if ua else None


def request_ip() -> str | None:
    ip = client_ip_ctx.get()
    return ip[:45] if ip else None


# ── The validation / defaulting pass ─────────────────────────────────────────
def _int_or_422(value: Any, field: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError(
            f"{field} must be an integer.", code="invalid_signature_field",
            details={"field": field},
        ) from None


def normalise_capture(payload: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Validate + default the capture block. Returns **only** the keys the
    caller sent or that are derived from them, so a PATCH carrying one field
    touches one field.

    Rules (published at ``GET /metadata/signature-capture``):

    * ``sig_string`` is trimmed, size-capped, must contain no whitespace, and is
      **encrypted at rest**. Sending one defaults ``sig_format`` to
      ``topaz_sigstring_v1``, ``sig_compression``/``sig_encryption`` to ``0``,
      ``device_source`` to ``topaz`` and ``device_vendor`` to ``topaz``.
    * ``sig_format`` / ``sig_compression`` / ``sig_encryption`` must be in the
      published sets (422 ``invalid_signature_field``).
    * ``point_count`` < 2 or ``stroke_count`` < 1 is an empty pad → 422
      ``signature_empty`` (SIG-2). Only judged when the count is sent — the
      on-screen pad reports neither.
    * ``device_source`` / ``device_vendor`` are lower-cased and trimmed; an
      unrecognised source is **stored as written** (the PROV-3 call — a 422 on
      save is a worse failure than an unfamiliar string). Model/serial are
      trimmed to the column width rather than refused: they are pad-reported.
    * ``signature_len`` is recomputed from ``signature_data`` when the image is
      sent without it; ``captured_user_agent`` defaults to the request's
      User-Agent; ``signed_at`` defaults to now when any capture is sent.
    """
    out: dict[str, Any] = {}
    sent = {k: payload[k] for k in CAPTURE_FIELDS if k in payload}

    if "signature_data" in sent:
        image = _clean(sent["signature_data"])
        if image and len(image) > MAX_SIGNATURE_CHARS:
            raise ValidationError("Signature payload is too large", code="signature_too_large")
        out["signature_data"] = image
        if image and sent.get("signature_len") in (None, 0):
            out["signature_len"] = len(image)
    if "signature_len" in sent and "signature_len" not in out:
        out["signature_len"] = _int_or_422(sent["signature_len"], "signature_len")

    sig_string = _clean(sent.get("sig_string")) if "sig_string" in sent else None
    if "sig_string" in sent:
        if sig_string and len(sig_string) > MAX_SIG_STRING_CHARS:
            raise ValidationError("sig_string is too large", code="sig_string_too_large")
        if sig_string and _WS_RE.search(sig_string):
            raise ValidationError(
                "sig_string must be the raw Topaz SigString (no whitespace).",
                code="invalid_sig_string",
            )
        out["sig_string"] = encrypt_sig_string(sig_string)

    if "sig_format" in sent or sig_string:
        fmt = _clean(sent.get("sig_format"))
        fmt = fmt.lower() if fmt else (SIG_FORMAT_TOPAZ_V1 if sig_string else None)
        if fmt is not None and fmt not in SIG_FORMATS:
            raise ValidationError(
                f"sig_format must be one of {', '.join(SIG_FORMATS)}.",
                code="invalid_signature_field", details={"field": "sig_format"},
            )
        out["sig_format"] = fmt

    for field, allowed in (("sig_compression", SIG_COMPRESSION_VALUES),
                           ("sig_encryption", SIG_ENCRYPTION_VALUES)):
        if field in sent or sig_string:
            value = _int_or_422(sent.get(field), field)
            if value is None and sig_string:
                value = 0
            if value is not None and value not in allowed:
                raise ValidationError(
                    f"{field} must be one of {', '.join(map(str, allowed))}.",
                    code="invalid_signature_field", details={"field": field},
                )
            out[field] = value

    for field, minimum in (("point_count", MIN_POINT_COUNT), ("stroke_count", MIN_STROKE_COUNT)):
        if field in sent:
            value = _int_or_422(sent[field], field)
            if value is not None and value < minimum:
                raise ValidationError(
                    "The pad reported an empty signature; ask the signer to sign again.",
                    code="signature_empty",
                    details={"field": field, "value": value, "minimum": minimum},
                )
            out[field] = value

    if "device_source" in sent or sig_string:
        source = _clean(sent.get("device_source"))
        source = source.lower() if source else None
        if source is None and sig_string:
            source = DEVICE_SOURCE_TOPAZ
        out["device_source"] = source[:20] if source else None
    if "device_vendor" in sent or sig_string or out.get("device_source") == DEVICE_SOURCE_TOPAZ:
        vendor = _clean(sent.get("device_vendor"))
        vendor = vendor.lower() if vendor else None
        if vendor is None and (sig_string or out.get("device_source") == DEVICE_SOURCE_TOPAZ):
            vendor = DEVICE_VENDOR_TOPAZ
        out["device_vendor"] = vendor[:20] if vendor else None
    for field in ("device_model", "device_serial"):
        if field in sent:
            value = _clean(sent[field])
            out[field] = value[:40] if value else None

    captured_anything = any(out.get(k) is not None for k in ("signature_data", "sig_string"))
    if "captured_user_agent" in sent:
        ua = _clean(sent["captured_user_agent"])
        out["captured_user_agent"] = ua[:255] if ua else None
    elif captured_anything:
        out["captured_user_agent"] = request_user_agent()

    if "signed_at" in sent and sent["signed_at"] is not None:
        out["signed_at"] = sent["signed_at"]
    elif captured_anything:
        out["signed_at"] = now or _now()
    return out


def apply_capture(row: Any, capture: dict[str, Any]) -> None:
    for key, value in capture.items():
        setattr(row, key, value)


def user_column_for(field: str) -> str:
    """``users`` carries the block prefixed: ``device_source`` →
    ``signature_device_source``; the two already-prefixed keys stay."""
    if field.startswith("signature_"):
        return field
    return f"signature_{field}"


def apply_user_capture(user: User, capture: dict[str, Any]) -> None:
    for key, value in capture.items():
        setattr(user, user_column_for(key), value)


def clear_user_topaz_metadata(user: User) -> None:
    """The user PATCH (``signature_data`` only) replaced the image without any
    capture metadata — whatever Topaz block was stored described the *previous*
    image, so it is cleared rather than left asserting a pad that never saw
    this signature. ``PUT /users/{id}/signature`` is the canonical write (SIG-6)."""
    for field in CAPTURE_FIELDS:
        if field in ("signature_data", "signature_len"):
            continue
        setattr(user, user_column_for(field), None)


# ── SIG-7: document hashes ───────────────────────────────────────────────────
def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def consent_content_hash(rendered_html: str | None) -> str | None:
    """SHA-256 over the rendered consent with whitespace collapsed, so a
    re-serialisation that only reflows the markup does not read as an edit."""
    if not rendered_html:
        return None
    return _sha256(_WS_RE.sub(" ", rendered_html).strip())


def progress_note_content_hash(note: ProgressNote) -> str:
    """SHA-256 over the clinical content of a note — text, structured charting
    fields and the freehand drawing — never its audit columns."""
    body = {
        "notes": (note.notes or "").strip(),
        "notes_html": _WS_RE.sub(" ", note.notes_html or "").strip(),
        "tooth": (note.tooth or "").strip(),
        "surface": (note.surface or "").strip(),
        "region": (note.region or "").strip(),
        "note_date": note.note_date.isoformat() if note.note_date else None,
        "drawing_strokes": note.drawing_strokes,
    }
    return _sha256(json.dumps(body, sort_keys=True, default=str))


def document_status(*, signed: bool, stored_hash: str | None, current_hash: str | None) -> str:
    """``signed`` | ``stale`` | ``unverifiable`` | ``unsigned`` — the MH-6
    semantics. A signature with no recorded hash is *unverifiable*, never
    *signed*: asserting it attests to today's content would be the original
    bug with the API's authority behind it."""
    if not signed:
        return "unsigned"
    if not stored_hash:
        return "unverifiable"
    return "signed" if stored_hash == current_hash else "stale"


# ── SIG-8: audit trail ───────────────────────────────────────────────────────
def record_event(
    db: Session,
    *,
    tenant_id: int | None,
    entity_type: str,
    entity_id: int,
    event: str,
    actor_id: int | None,
    patient_id: int | None = None,
    source: Any = None,
    signature_type: str | None = None,
    content_hash: str | None = None,
    reason: str | None = None,
    occurred_at: datetime | None = None,
) -> SignatureAuditEvent:
    """Append one audit row. Does **not** commit — it rides the caller's
    transaction so an event can never outlive a rolled-back capture. ``source``
    is the row the device block is read from (a ``patient_signatures`` /
    ``patient_consents`` row, or a ``User`` via the prefixed columns)."""
    prefix = "signature_" if isinstance(source, User) else ""

    def col(name: str) -> Any:
        return getattr(source, f"{prefix}{name}", None) if source is not None else None

    row = SignatureAuditEvent(
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        patient_id=patient_id,
        event=event,
        actor_id=actor_id,
        occurred_at=occurred_at or _now(),
        ip=request_ip(),
        user_agent=request_user_agent(),
        device_source=col("device_source"),
        device_vendor=col("device_vendor"),
        device_model=col("device_model"),
        device_serial=col("device_serial"),
        signature_type=signature_type,
        content_hash=content_hash,
        reason=_clean(reason)[:500] if _clean(reason) else None,
    )
    db.add(row)
    return row


# ── Tenancy / binding helpers ────────────────────────────────────────────────
def _require_patient(db: Session, tenant_id: int | None, patient_id: int | None) -> Patient:
    patient = db.get(Patient, patient_id) if patient_id is not None else None
    if patient is None or (tenant_id is not None and patient.tenant_id != tenant_id):
        raise NotFoundError(f"Patient '{patient_id}' was not found")
    return patient


def _bind_document(db: Session, tenant_id: int | None, patient_id: int,
                   data: dict[str, Any]) -> None:
    """SIG-7: resolve ``progress_note_id`` / ``consent_id`` on a signature write.
    The document must be on the **same patient** (422
    ``signature_document_mismatch`` — a signature rendered inside one chart
    that attests to another patient's note is a records error, not cosmetic),
    and the server computes ``content_hash`` over it, overriding any echo."""
    note_id = data.get("progress_note_id")
    consent_id = data.get("consent_id")
    if note_id is not None:
        note = db.get(ProgressNote, int(note_id))
        if note is None or note.is_deleted:
            raise NotFoundError(f"ProgressNote '{note_id}' was not found")
        if note.patient_id != patient_id:
            raise ValidationError(
                "progress_note_id belongs to a different patient.",
                code="signature_document_mismatch", details={"field": "progress_note_id"},
            )
        _require_patient(db, tenant_id, note.patient_id)
        data["content_hash"] = progress_note_content_hash(note)
        if not data.get("signature_type"):
            data["signature_type"] = "progress_note"
    if consent_id is not None:
        consent = db.get(PatientConsent, int(consent_id))
        if consent is None or consent.is_deleted or (
            tenant_id is not None and consent.tenant_id != tenant_id
        ):
            raise NotFoundError(f"PatientConsent '{consent_id}' was not found")
        if consent.patient_id != patient_id:
            raise ValidationError(
                "consent_id belongs to a different patient.",
                code="signature_document_mismatch", details={"field": "consent_id"},
            )
        data["content_hash"] = consent_content_hash(consent.rendered_html)
        if not data.get("signature_type"):
            data["signature_type"] = "consent"


# ── Engine hooks ─────────────────────────────────────────────────────────────
class PatientSignatureCRUD(CRUDBase):
    """``patient_signatures`` has no ``tenant_id``, and the generic engine only
    scopes models that carry one — so before this class any tenant could read
    or void any signature by id. Tenancy is enforced through the owning patient
    (the ``InsuranceCoverageRuleCRUD`` precedent)."""

    custom_filter_fields = ("include_image",)

    def _scope_tenant(self, stmt, tenant_id: int | None):  # noqa: ANN001
        if tenant_id is not None:
            owned = select(Patient.id).where(Patient.tenant_id == tenant_id)
            stmt = stmt.where(self.model.patient_id.in_(owned))
        return stmt

    def list(self, db, *, filters=None, **kwargs):  # noqa: ANN001
        filters = dict(filters or {})
        include_image = filters.pop("include_image", None)
        items, total = super().list(db, filters=filters, **kwargs)
        # SIG-9: ``?include_image=false`` — a 50-row list stops shipping 50
        # JPEGs. The rows are detached first so blanking the column can never
        # be flushed back as a NULL.
        if include_image is False:
            for row in items:
                db.expunge(row)
                row.has_image = bool(row.signature_data) and not looks_like_sigstring(row.signature_data)
                row.signature_data = None
                row.image_omitted = True
        return items, total

    def create(self, db, data, *, tenant_id=None, created_by=None):  # noqa: ANN001
        data = dict(data)
        patient = _require_patient(db, tenant_id, data.get("patient_id"))
        _bind_document(db, tenant_id, patient.id, data)
        data.update(normalise_capture(data))
        if data.get("signed_by_user_id") is None:
            data["signed_by_user_id"] = created_by
        obj = self.model(**{k: v for k, v in data.items() if hasattr(self.model, k)})
        if created_by is not None:
            obj.created_by = created_by
        db.add(obj)
        db.flush()
        record_event(
            db, tenant_id=tenant_id, entity_type=ENTITY_PATIENT_SIGNATURE, entity_id=obj.id,
            event=EVENT_CAPTURED, actor_id=created_by, patient_id=obj.patient_id, source=obj,
            signature_type=obj.signature_type, content_hash=obj.content_hash,
            occurred_at=obj.signed_at,
        )
        self._commit(db)
        db.refresh(obj)
        return obj

    def update(self, db, obj_id, data, *, tenant_id=None, updated_by=None):  # noqa: ANN001
        obj = self.get(db, obj_id, tenant_id=tenant_id)
        data = dict(data)
        if "patient_id" in data and data["patient_id"] != obj.patient_id:
            raise ValidationError(
                "A signature cannot be moved to another patient.",
                code="signature_patient_immutable", details={"field": "patient_id"},
            )
        if "progress_note_id" in data or "consent_id" in data:
            merged = {
                "progress_note_id": data.get("progress_note_id", obj.progress_note_id),
                "consent_id": data.get("consent_id", obj.consent_id),
                "signature_type": data.get("signature_type", obj.signature_type),
            }
            _bind_document(db, tenant_id, obj.patient_id, merged)
            data.update(merged)
        data.update(normalise_capture(data))
        for key, value in data.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
        if updated_by is not None:
            obj.updated_by = updated_by
        self._commit(db)
        db.refresh(obj)
        return obj

    def delete(self, db, obj_id, *, tenant_id=None):  # noqa: ANN001
        obj = self.get(db, obj_id, tenant_id=tenant_id)
        if obj.is_active:
            obj.is_active = False
            obj.voided_at = _now()
            record_event(
                db, tenant_id=tenant_id, entity_type=ENTITY_PATIENT_SIGNATURE,
                entity_id=obj.id, event=EVENT_VOIDED, actor_id=obj.updated_by,
                patient_id=obj.patient_id, source=obj, signature_type=obj.signature_type,
                content_hash=obj.content_hash,
            )
        self._commit(db)


class PatientConsentCRUD(CRUDBase):
    """The generic consent routes accept the capture block too (an import, an
    older client); they go through the same normalisation so a clear-text
    SigString can never land in the column."""

    def create(self, db, data, *, tenant_id=None, created_by=None):  # noqa: ANN001
        data = dict(data)
        data.update(normalise_capture(data))
        return super().create(db, data, tenant_id=tenant_id, created_by=created_by)

    def update(self, db, obj_id, data, *, tenant_id=None, updated_by=None):  # noqa: ANN001
        data = dict(data)
        data.update(normalise_capture(data))
        return super().update(db, obj_id, data, tenant_id=tenant_id, updated_by=updated_by)


# ── Read enrichment ──────────────────────────────────────────────────────────
def _names(db: Session, ids: Iterable[int | None]) -> dict[int, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    from app.services.user_admin_service import resolve_user_names

    return resolve_user_names(db, wanted)


def enrich_patient_signatures(db: Session, items: list, tenant_id: int | None = None) -> None:  # noqa: ARG001
    """``has_image`` / ``has_sig_string`` / ``signature_status`` / actor names."""
    rows = list(items)
    if not rows:
        return
    note_ids = {r.progress_note_id for r in rows if r.progress_note_id is not None}
    consent_ids = {r.consent_id for r in rows if r.consent_id is not None}
    note_hashes: dict[int, str] = {}
    if note_ids:
        for note in db.execute(select(ProgressNote).where(ProgressNote.id.in_(note_ids))).scalars():
            note_hashes[note.id] = progress_note_content_hash(note)
    consent_hashes: dict[int, str | None] = {}
    if consent_ids:
        for consent in db.execute(
            select(PatientConsent).where(PatientConsent.id.in_(consent_ids))
        ).scalars():
            consent_hashes[consent.id] = consent_content_hash(consent.rendered_html)
    names = _names(db, [a for r in rows for a in (r.created_by, r.signed_by_user_id, r.voided_by)])

    for r in rows:
        if not hasattr(r, "has_image"):
            r.has_image = bool(r.signature_data) and not looks_like_sigstring(r.signature_data)
        if not hasattr(r, "image_omitted"):
            r.image_omitted = False
        r.has_sig_string = bool(r.sig_string)
        r.legacy_sig_string_in_image = looks_like_sigstring(r.signature_data)
        r.created_by_name = names.get(r.created_by) if r.created_by else None
        r.signed_by_name = names.get(r.signed_by_user_id) if r.signed_by_user_id else None
        r.voided_by_name = names.get(r.voided_by) if r.voided_by else None
        if not r.is_active:
            r.signature_status = "voided" if r.voided_at else "superseded"
        elif r.progress_note_id is not None:
            r.signature_status = document_status(
                signed=True, stored_hash=r.content_hash,
                current_hash=note_hashes.get(r.progress_note_id),
            )
        elif r.consent_id is not None:
            r.signature_status = document_status(
                signed=True, stored_hash=r.content_hash,
                current_hash=consent_hashes.get(r.consent_id),
            )
        else:
            # Unbound: a medical-history signature is judged by the medical-
            # history document (MH-6); anything else has nothing to compare to.
            r.signature_status = None


def consent_signature_status(consent: PatientConsent) -> str:
    if consent.status in ("declined", "voided"):
        return consent.status
    return document_status(
        signed=consent.status == "signed", stored_hash=consent.content_hash,
        current_hash=consent_content_hash(consent.rendered_html),
    )


def enrich_patient_consents(db: Session, items: list, tenant_id: int | None = None) -> None:  # noqa: ARG001
    for r in items:
        r.has_sig_string = bool(r.sig_string)
        r.signature_status = consent_signature_status(r)


def progress_note_signature_status(note: ProgressNote) -> str:
    return document_status(
        signed=note.signed_at is not None, stored_hash=note.content_hash,
        current_hash=progress_note_content_hash(note),
    )


# ── SIG-4: the audited way to read a SigString ───────────────────────────────
def signature_vector(row: Any, *, entity_type: str) -> dict[str, Any]:
    prefix = "signature_" if isinstance(row, User) else ""

    def col(name: str) -> Any:
        return getattr(row, f"{prefix}{name}", None)

    stored = col("sig_string")
    clear = decrypt_sig_string(stored)
    return {
        "entity_type": entity_type,
        "entity_id": row.id,
        "sig_string": clear,
        "sig_string_readable": clear is not None,
        "sig_format": col("sig_format"),
        "sig_compression": col("sig_compression"),
        "sig_encryption": col("sig_encryption"),
        "point_count": col("point_count"),
        "stroke_count": col("stroke_count"),
        "device_source": col("device_source"),
        "device_vendor": col("device_vendor"),
        "device_model": col("device_model"),
        "device_serial": col("device_serial"),
        "signed_at": col("signed_at"),
        "encrypted_at_rest": is_encrypted(stored),
    }


# ── Published rules ──────────────────────────────────────────────────────────
def published_rules() -> dict[str, Any]:
    return {
        "sig_formats": list(SIG_FORMATS),
        "sig_compression_values": {"0": "none", "1": "lossless", "2": "lossy"},
        "sig_encryption_values": {"0": "clear", "1": "des", "2": "high"},
        "device_sources": list(DEVICE_SOURCES),
        "legacy_device_source": DEVICE_SOURCE_LEGACY,
        "legacy_device_sources": [DEVICE_SOURCE_LEGACY, DEVICE_SOURCE_LEGACY_IMAGE],
        "signature_methods": list(SIGNATURE_METHODS),
        "signature_statuses": list(SIGNATURE_STATUSES),
        "audit_events": list(EVENTS),
        "min_point_count": MIN_POINT_COUNT,
        "min_stroke_count": MIN_STROKE_COUNT,
        "max_signature_chars": MAX_SIGNATURE_CHARS,
        "max_sig_string_chars": MAX_SIG_STRING_CHARS,
        "sig_string_encrypted_at_rest": True,
        "sig_string_on_read_models": False,
        "sig_string_endpoints": [
            "GET /patient-signatures/{id}/sig-string",
            "GET /patient-consents/{id}/sig-string",
            "GET /users/{id}/signature?include_sig_string=true",
        ],
        "canonical_user_signature_write": "PUT /users/{id}/signature",
        "document_binding": {
            "progress_note_id": "content_hash = SHA-256 over the note content at signing",
            "consent_id": "content_hash = SHA-256 over rendered_html at signing",
            "medical_history": "POST /patients/{id}/medical-history/sign (MH-6)",
        },
    }
