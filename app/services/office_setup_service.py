"""Office Setup service — per-office configuration (gaps #10–#17).

Every office-scoped operation first verifies the office belongs to the
authenticated tenant (``get_office_in_tenant``). 1:1 settings rows are created on
first access (upsert). Secrets (DoseSpot key) are encrypted at rest and returned
masked. The office logo is stored on the configured upload dir and served by URL.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import settings as cfg
from app.core.crypto import decrypt, encrypt, mask
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.db.models import FeeSchedule, Office, OfficeGroup, Provider
from app.db.models.comms import SmsTemplate
from app.integrations import email as email_transport
from app.services import fee_vocab
from app.db.models.office_setup import (
    OfficeAdvancedSettings,
    OfficeIntegrations,
    OfficeScheduleDay,
    OfficeSmartAssist,
    OfficeSmartAssistItem,
    OfficeStatementSettings,
)

# Curated IANA time zones (gap #10 — the one piece with no backend source).
US_TIME_ZONES = [
    ("America/New_York", "Eastern (America/New_York)"),
    ("America/Chicago", "Central (America/Chicago)"),
    ("America/Denver", "Mountain (America/Denver)"),
    ("America/Phoenix", "Arizona (America/Phoenix)"),
    ("America/Los_Angeles", "Pacific (America/Los_Angeles)"),
    ("America/Anchorage", "Alaska (America/Anchorage)"),
    ("Pacific/Honolulu", "Hawaii (Pacific/Honolulu)"),
]


def get_office_in_tenant(db: Session, office_id: int, tenant_id: int) -> Office:
    office = db.get(Office, office_id)
    if office is None:
        raise NotFoundError(f"Office '{office_id}' was not found")
    if office.tenant_id != tenant_id:
        raise ForbiddenError("Office does not belong to the authenticated tenant")
    return office


# ── Info-tab metadata aggregate (#10) ────────────────────────────────────────
def metadata(db: Session, tenant_id: int) -> dict:
    providers = db.execute(
        select(Provider.id, Provider.name).where(
            Provider.tenant_id == tenant_id, Provider.is_active.is_(True)
        ).order_by(Provider.name.asc())
    ).all()
    fee_schedules = db.execute(
        select(FeeSchedule.id, FeeSchedule.name).where(
            FeeSchedule.tenant_id == tenant_id, FeeSchedule.is_active.is_(True)
        ).order_by(FeeSchedule.name.asc())
    ).all()
    return {
        "time_zones": [{"value": v, "label": label} for v, label in US_TIME_ZONES],
        "billing_providers": [{"id": pid, "name": name} for pid, name in providers],
        "fee_schedules": [{"id": fid, "name": name} for fid, name in fee_schedules],
    }


# ── Generic 1:1 singleton helpers ────────────────────────────────────────────
def get_or_create_singleton(db: Session, model: type, office_id: int, tenant_id: int):
    """The office's 1:1 settings row, created with defaults on first access.

    OFF-QA-13: the insert is ``INSERT … ON CONFLICT (office_id) DO NOTHING`` and
    the row is re-read, so two concurrent first reads (React StrictMode fires
    every GET twice in dev) both land on the one row instead of one of them
    500-ing on the unique constraint.
    """
    stmt = select(model).where(model.office_id == office_id)
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
        db.execute(
            insert(model.__table__)
            .values(office_id=office_id, tenant_id=tenant_id, **_column_defaults(model))
            .on_conflict_do_nothing(index_elements=["office_id"])
        )
        db.commit()
        row = db.execute(stmt).scalar_one()
    return row


def _column_defaults(model: type) -> dict:
    """Python-side scalar defaults (a Core insert does not apply ORM defaults
    for NOT NULL booleans like ``enabled``/``is_ortho``)."""
    out: dict = {}
    for col in model.__table__.columns:
        if col.name in ("id", "office_id", "tenant_id"):
            continue
        default = col.default
        if default is not None and getattr(default, "is_scalar", False):
            out[col.name] = default.arg
    return out


def update_singleton(
    db: Session, model: type, office_id: int, tenant_id: int, data: dict, user_id: int | None
):
    row = get_or_create_singleton(db, model, office_id, tenant_id)
    if "preferred_provider_id" in data:
        _check_provider(db, data["preferred_provider_id"], tenant_id, "preferred_provider_id")
    for key, value in data.items():
        if hasattr(row, key):
            setattr(row, key, value)
    if hasattr(row, "updated_by"):
        row.updated_by = user_id
    db.commit()
    db.refresh(row)
    return row


def field_error(field: str, message: str, code: str, **extra: Any) -> ValidationError:
    """OFF-QA-10: a field-level 422 in the shape the request validator uses
    (``loc``/``msg``), never the raw driver text."""
    return ValidationError(
        message, code=code,
        details={"code": code, "field": field, "loc": ["body", field], "msg": message, **extra},
    )


def _check_provider(db: Session, provider_id: str | None, tenant_id: int, field: str) -> None:
    if provider_id in (None, ""):
        return
    found = db.execute(
        select(Provider.id).where(Provider.id == provider_id, Provider.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if found is None:
        raise field_error(field, "Unknown provider", "provider_not_found")


# ── Integrations (#13) — DoseSpot key encrypted/masked ───────────────────────
def _reset_email_verification(row: OfficeIntegrations) -> None:
    row.service_email_verified = False
    row.service_email_verified_at = None
    row.service_email_verification_hash = None
    row.service_email_verification_sent_at = None
    row.service_email_verification_expires_at = None
    row.service_email_verification_attempts = 0


def update_integrations(db: Session, office_id: int, tenant_id: int, data: dict, user_id: int | None):
    key = data.pop("dosespot_key", None)
    row = get_or_create_singleton(db, OfficeIntegrations, office_id, tenant_id)
    if key is not None:
        row.dosespot_key_enc = encrypt(key) if key else None
    # OFF-QA-5: "verified" describes an address; a different address is unverified.
    if "service_email" in data and _norm_email(data["service_email"]) != _norm_email(row.service_email):
        _reset_email_verification(row)
    for k, v in data.items():
        if hasattr(row, k):
            setattr(row, k, v)
    row.updated_by = user_id
    db.commit()
    db.refresh(row)
    return row


def _norm_email(value: str | None) -> str:
    return (value or "").strip().lower()


def dosespot_key_masked(row: OfficeIntegrations) -> str | None:
    return mask(decrypt(row.dosespot_key_enc), visible=4)


# OFF-QA-5: verify-email round trip — a 6-digit code mailed to the address.
EMAIL_CODE_TTL = timedelta(hours=24)
EMAIL_CODE_MAX_ATTEMPTS = 5


def _code_hash(office_id: int, email: str, code: str) -> str:
    # Bound to the office and the address so a code cannot confirm anything else.
    return hashlib.sha256(f"{office_id}:{_norm_email(email)}:{code.strip()}".encode()).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def send_service_email_verification(
    db: Session, office_id: int, tenant_id: int, user_id: int | None,
) -> dict:
    office = get_office_in_tenant(db, office_id, tenant_id)
    row = get_or_create_singleton(db, OfficeIntegrations, office_id, tenant_id)
    if not row.service_email:
        raise field_error("service_email", "Save a service e-mail address first", "service_email_missing")
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = _utcnow()
    row.service_email_verification_hash = _code_hash(office_id, row.service_email, code)
    row.service_email_verification_sent_at = now
    row.service_email_verification_expires_at = now + EMAIL_CODE_TTL
    row.service_email_verification_attempts = 0
    row.updated_by = user_id
    db.commit()
    sent = email_transport.send_email(
        row.service_email,
        f"Verify the service e-mail for {office.name}",
        f"Your verification code is {code}.\n\n"
        f"Enter it in Setup -> Offices -> {office.name} -> Integration to confirm this address. "
        f"The code expires in 24 hours.",
    )
    return {
        "service_email": row.service_email,
        "sent": sent,
        "expires_at": row.service_email_verification_expires_at,
        "transport": email_transport.active_transport(),
    }


def confirm_service_email_verification(
    db: Session, office_id: int, tenant_id: int, code: str, user_id: int | None,
) -> OfficeIntegrations:
    row = get_or_create_singleton(db, OfficeIntegrations, office_id, tenant_id)
    if not row.service_email or not row.service_email_verification_hash:
        raise ValidationError("No verification is pending for this office",
                              code="email_verification_not_pending")
    if row.service_email_verification_expires_at and row.service_email_verification_expires_at < _utcnow():
        raise ValidationError("The verification code has expired; send a new one",
                              code="email_verification_expired")
    if (row.service_email_verification_attempts or 0) >= EMAIL_CODE_MAX_ATTEMPTS:
        raise ValidationError("Too many wrong codes; send a new one",
                              code="email_verification_locked")
    if not hmac.compare_digest(row.service_email_verification_hash,
                               _code_hash(office_id, row.service_email, code)):
        row.service_email_verification_attempts = (row.service_email_verification_attempts or 0) + 1
        db.commit()
        raise field_error("code", "The verification code is not correct", "email_verification_invalid",
                          attempts_left=max(0, EMAIL_CODE_MAX_ATTEMPTS - row.service_email_verification_attempts))
    row.service_email_verified = True
    row.service_email_verified_at = _utcnow()
    row.service_email_verification_hash = None
    row.service_email_verification_attempts = 0
    row.updated_by = user_id
    db.commit()
    db.refresh(row)
    return row


# ── Schedule (#14) — 7-day weekly grid ───────────────────────────────────────
_DEFAULT_OPEN = (time(8, 0), time(17, 0))


def default_schedule_day(office_id: int, tenant_id: int, day: int) -> OfficeScheduleDay:
    """Mon–Fri 08:00–17:00, weekend closed — a transient row, never added."""
    return OfficeScheduleDay(
        tenant_id=tenant_id, office_id=office_id, day_of_week=day,
        is_closed=day >= 5,
        start_time=None if day >= 5 else _DEFAULT_OPEN[0],
        end_time=None if day >= 5 else _DEFAULT_OPEN[1],
        lunch_start=None, lunch_end=None,
    )


def get_schedule(db: Session, office_id: int, tenant_id: int) -> list[OfficeScheduleDay]:
    """The office week, one entry per day. OFF-QA-13: a day with no stored row
    reads the default (unsaved, ``id`` null) instead of a GET writing seven rows
    — which also kept "never configured" distinguishable from "configured as
    8–5" for the booking check (OFF-QA-7)."""
    stored = {r.day_of_week: r for r in db.execute(
        select(OfficeScheduleDay).where(OfficeScheduleDay.office_id == office_id)
    ).scalars().all()}
    return [stored.get(d) or default_schedule_day(office_id, tenant_id, d) for d in range(7)]


def replace_schedule(
    db: Session, office_id: int, tenant_id: int, days: list[dict]
) -> list[OfficeScheduleDay]:
    """OFF-QA-4: upsert the days sent; a day not in the payload is left as it is
    (a partial PUT used to delete it). Times are validated by ``ScheduleDayInput``."""
    seen = {d["day_of_week"] for d in days}
    if seen - set(range(7)):
        raise ValidationError("day_of_week must be 0–6 (Mon–Sun)", code="invalid_day")
    stored = {r.day_of_week: r for r in db.execute(
        select(OfficeScheduleDay).where(OfficeScheduleDay.office_id == office_id)
    ).scalars().all()}
    for d in days:
        values = {**d}
        if values.get("is_closed"):
            # A closed day has no hours; keeping stale ones would read as open.
            values.update(start_time=None, end_time=None, lunch_start=None, lunch_end=None)
        row = stored.get(d["day_of_week"])
        if row is None:
            db.add(OfficeScheduleDay(tenant_id=tenant_id, office_id=office_id, **values))
        else:
            for k, v in values.items():
                setattr(row, k, v)
    db.commit()
    return get_schedule(db, office_id, tenant_id)


# ── SmartAssist (#17) — settings + items ─────────────────────────────────────
#: OFF-QA-6: the default item set (the codes the Setup tab already labels).
#: Served until the office saves its own grid; nothing reads it to *run* yet.
SMART_ASSIST_CATALOG: tuple[dict, ...] = (
    {"item_code": "payment", "label": "Payment", "frequency": "EVERY_VISIT",
     "description": "Collect the patient portion / outstanding balance", "include_unpaid_balance": True},
    {"item_code": "email", "label": "E-mail", "frequency": "EVERY_VISIT",
     "description": "Confirm the patient's e-mail address"},
    {"item_code": "cell_phone", "label": "Cell Phone", "frequency": "EVERY_VISIT",
     "description": "Confirm the patient's cell phone number"},
    {"item_code": "eligibility", "label": "Eligibility", "frequency": "EVERY_VISIT",
     "description": "Verify insurance eligibility"},
    {"item_code": "medical_history", "label": "Medical History", "frequency": "EVERY_YEAR",
     "description": "Review and sign the medical history"},
    {"item_code": "hipaa", "label": "HIPAA", "frequency": "EVERY_YEAR",
     "description": "Sign the HIPAA notice acknowledgement"},
    {"item_code": "consent_form_1", "label": "Consent Form 1", "frequency": "ONCE",
     "description": "Sign consent form 1"},
    {"item_code": "consent_form_2", "label": "Consent Form 2", "frequency": "ONCE",
     "description": "Sign consent form 2"},
    {"item_code": "consent_form_3", "label": "Consent Form 3", "frequency": "ONCE",
     "description": "Sign consent form 3"},
    {"item_code": "consent_form_4", "label": "Consent Form 4", "frequency": "ONCE",
     "description": "Sign consent form 4"},
    {"item_code": "progress_note", "label": "Progress Note", "frequency": "EVERY_VISIT",
     "description": "Progress note written for the visit"},
    {"item_code": "ledger_posting", "label": "Ledger Posting", "frequency": "EVERY_VISIT",
     "description": "Charges posted to the ledger for the visit"},
)
_CATALOG_LABELS = {c["item_code"]: c["label"] for c in SMART_ASSIST_CATALOG}


def smart_assist_catalog() -> list[dict]:
    return [{"include_unpaid_balance": False, **c} for c in SMART_ASSIST_CATALOG]


def _catalog_item(office_id: int, tenant_id: int, c: dict) -> dict:
    return {
        "id": None, "created_at": None, "tenant_id": tenant_id, "office_id": office_id,
        "item_code": c["item_code"], "label": c["label"], "description": c["description"],
        "frequency": c["frequency"], "sms_template_id": None,
        "include_unpaid_balance": c.get("include_unpaid_balance", False), "is_enabled": False,
    }


def get_smart_assist(db: Session, office_id: int, tenant_id: int) -> dict:
    settings_row = db.execute(
        select(OfficeSmartAssist).where(OfficeSmartAssist.office_id == office_id)
    ).scalar_one_or_none()
    items = list(db.execute(
        select(OfficeSmartAssistItem).where(OfficeSmartAssistItem.office_id == office_id)
        .order_by(OfficeSmartAssistItem.id.asc())
    ).scalars().all())
    enabled = bool(settings_row.enabled) if settings_row is not None else False
    if not items:
        return {"enabled": enabled, "items_source": "catalog",
                "items": [_catalog_item(office_id, tenant_id, c) for c in SMART_ASSIST_CATALOG]}
    for it in items:
        it.label = _CATALOG_LABELS.get(it.item_code)  # transient display attribute
    return {"enabled": enabled, "items_source": "stored", "items": items}


def smart_assist_sms_templates(db: Session, office_id: int, tenant_id: int) -> list[dict]:
    """Active SMS templates this office may use: its own + the tenant-shared ones."""
    rows = db.execute(
        select(SmsTemplate).where(
            SmsTemplate.tenant_id == tenant_id, SmsTemplate.is_active.is_(True),
            or_(SmsTemplate.office_id == office_id, SmsTemplate.office_id.is_(None)),
        ).order_by(SmsTemplate.name.asc())
    ).scalars().all()
    return [{"id": str(r.id), "name": r.name, "message_type": r.message_type, "office_id": r.office_id}
            for r in rows]


def update_smart_assist(
    db: Session, office_id: int, tenant_id: int, enabled: bool | None,
    items: list[dict] | None, user_id: int | None,
) -> dict:
    settings_row = get_or_create_singleton(db, OfficeSmartAssist, office_id, tenant_id)
    if enabled is not None:
        settings_row.enabled = enabled
    settings_row.updated_by = user_id
    if items is not None:
        # OFF-QA-6: a template must be one this office can use (it was free text).
        allowed = {t["id"] for t in smart_assist_sms_templates(db, office_id, tenant_id)}
        for i, it in enumerate(items):
            tid = it.get("sms_template_id")
            if tid is not None and str(tid).strip() not in allowed:
                db.rollback()
                raise ValidationError(
                    "Unknown SMS template", code="unknown_sms_template",
                    details={"code": "unknown_sms_template", "loc": ["body", "items", i, "sms_template_id"],
                             "field": "sms_template_id", "index": i, "value": tid},
                )
        codes = [it["item_code"] for it in items]
        if len(codes) != len(set(codes)):
            db.rollback()
            raise ValidationError("Each item_code may appear only once", code="duplicate_item_code")
        db.execute(sa_delete(OfficeSmartAssistItem).where(OfficeSmartAssistItem.office_id == office_id))
        db.add_all([
            OfficeSmartAssistItem(tenant_id=tenant_id, office_id=office_id, **it) for it in items
        ])
    db.commit()
    return get_smart_assist(db, office_id, tenant_id)


# ── Statement logo (#12) ─────────────────────────────────────────────────────
_EXT_BY_TYPE = {"image/jpeg": ".jpg", "image/png": ".png"}


def save_statement_logo(
    db: Session, office_id: int, tenant_id: int, filename: str, content_type: str, data: bytes
) -> str:
    if content_type not in cfg.LOGO_ALLOWED_TYPES:
        raise ValidationError(f"Unsupported logo type '{content_type}'", code="invalid_logo_type")
    if len(data) > cfg.LOGO_MAX_BYTES:
        raise ValidationError("Logo exceeds size limit", code="logo_too_large")
    ext = _EXT_BY_TYPE.get(content_type, Path(filename).suffix or ".img")
    logo_dir = Path(cfg.UPLOAD_DIR) / "office_logos"
    logo_dir.mkdir(parents=True, exist_ok=True)
    stored = f"office_{office_id}{ext}"
    (logo_dir / stored).write_bytes(data)
    url = f"{cfg.UPLOAD_URL_BASE}/office_logos/{stored}"
    row = get_or_create_singleton(db, OfficeStatementSettings, office_id, tenant_id)
    row.logo_url = url
    db.commit()
    return url


def delete_statement_logo(db: Session, office_id: int, tenant_id: int) -> None:
    row = get_or_create_singleton(db, OfficeStatementSettings, office_id, tenant_id)
    if row.logo_url:
        try:
            (Path(cfg.UPLOAD_DIR) / "office_logos" / Path(row.logo_url).name).unlink(missing_ok=True)
        except OSError:
            pass
    row.logo_url = None
    db.commit()


def set_fee_defaults(db: Session, office_id: int, tenant_id: int, data: dict) -> dict:
    """PATCH /offices/{id}/fee-defaults — the office's UCR list, its default patient
    list and its unpriced-charge policy, each validated (§3.5/§3.6). A schedule
    pointer must be a live schedule of this tenant (clearing it with ``null`` is
    allowed); an unrecognised policy is refused. Only fields present in the body
    are touched."""
    from app.services.fee_schedule_service import _schedule_valid  # noqa: PLC0415

    office = get_office_in_tenant(db, office_id, tenant_id)
    for field in ("default_ucr_fee_schedule_id", "default_fee_schedule_id"):
        if field not in data:
            continue
        value = data[field]
        if value is not None and not _schedule_valid(db, value, tenant_id):
            raise ValidationError(
                fee_vocab.ERROR_CODES["office_schedule_invalid"],
                details={"code": "office_schedule_invalid", "field": field},
            )
        setattr(office, field, value)
    if "unpriced_charge_policy" in data and data["unpriced_charge_policy"] is not None:
        policy = str(data["unpriced_charge_policy"]).strip().lower()
        if policy not in fee_vocab.UNPRICED_POLICY_CODES:
            raise ValidationError(
                "Unknown unpriced-charge policy",
                details={"code": "invalid_unpriced_policy", "field": "unpriced_charge_policy",
                         "allowed": list(fee_vocab.UNPRICED_POLICY_CODES)},
            )
        office.unpriced_charge_policy = policy
    db.commit()
    db.refresh(office)
    return {
        "office_id": office.id,
        "default_ucr_fee_schedule_id": office.default_ucr_fee_schedule_id,
        "default_fee_schedule_id": office.default_fee_schedule_id,
        "unpriced_charge_policy": office.unpriced_charge_policy,
    }


# ── Office row write rules (OFF-QA-3/9/10) ───────────────────────────────────
def _norm_code(value: Any) -> str | None:
    if value is None:
        return None
    v = str(value).strip()
    return v or None


def validate_office_write(db: Session, payload: dict, current: Office | None, tenant_id: int | None) -> dict:
    """Run by ``OfficeCRUD`` on create and PATCH. Each rule fires only when the
    payload *moves* the field (or on create), so a migrated office already
    holding a duplicate Short ID (``MOON`` x2) or an odd NPI stays editable.

    * ``short_id`` unique per tenant, case-insensitive -> 409 ``duplicate_short_id``;
    * ``office_code`` unique case-insensitively across **all** tenants -> 409
      ``duplicate_office_code`` (it is the anonymous AppointNow booking key and is
      resolved without a tenant, so it cannot become tenant-scoped);
    * ``npi`` 10 digits + Luhn, ``taxonomy_code`` NUCC shape -> 422;
    * FK pointers named field-by-field instead of a raw driver error.
    """
    from app.services import office_rules  # noqa: PLC0415

    tid = tenant_id if tenant_id is not None else getattr(current, "tenant_id", None)
    not_self = [Office.id != current.id] if current is not None else []

    def moved(field: str) -> bool:
        if field not in payload:
            return False
        if current is None:
            return True
        old, new = getattr(current, field, None), payload[field]
        if isinstance(old, str) or isinstance(new, str):
            return (str(old or "").strip().upper()) != (str(new or "").strip().upper())
        return old != new

    if "short_id" in payload:
        payload["short_id"] = _norm_code(payload["short_id"])
    if moved("short_id") and payload["short_id"] and tid is not None:
        clash = db.execute(
            select(Office.id, Office.name).where(
                Office.tenant_id == tid,
                func.upper(func.trim(Office.short_id)) == payload["short_id"].upper(),
                *not_self,
            )
        ).first()
        if clash is not None:
            raise ConflictError(
                f"Short ID '{payload['short_id']}' is already used by {clash.name}",
                code="duplicate_short_id",
                details={"code": "duplicate_short_id", "field": "short_id", "loc": ["body", "short_id"],
                         "office_id": clash.id, "office_name": clash.name},
            )

    if "office_code" in payload and payload["office_code"] is not None:
        payload["office_code"] = str(payload["office_code"]).strip()
        if not payload["office_code"]:
            raise field_error("office_code", "Office code is required", "office_code_required")
    if moved("office_code") and payload.get("office_code"):
        clash = db.execute(
            select(Office.id).where(
                func.lower(Office.office_code) == payload["office_code"].lower(),
                *not_self,
            )
        ).first()
        if clash is not None:
            # Deliberately no office name: the clash may be another tenant's.
            raise ConflictError(
                f"Office code '{payload['office_code']}' is already in use",
                code="duplicate_office_code",
                details={"code": "duplicate_office_code", "field": "office_code", "loc": ["body", "office_code"]},
            )

    if "npi" in payload:
        payload["npi"] = _norm_code(payload["npi"])
        if moved("npi") and payload["npi"] and not office_rules.npi_is_valid(payload["npi"]):
            raise field_error("npi", "NPI must be 10 digits and pass the NPI check digit", "invalid_npi")
    if "taxonomy_code" in payload:
        payload["taxonomy_code"] = _norm_code(payload["taxonomy_code"])
        if payload["taxonomy_code"]:
            payload["taxonomy_code"] = payload["taxonomy_code"].upper()
        if moved("taxonomy_code") and payload["taxonomy_code"] and not office_rules.taxonomy_is_valid(
            payload["taxonomy_code"]
        ):
            raise field_error("taxonomy_code", "Taxonomy code must look like 1223G0001X", "invalid_taxonomy_code")

    if tid is not None:
        if moved("billing_provider_id"):
            _check_provider(db, payload["billing_provider_id"], tid, "billing_provider_id")
        for field in ("default_fee_schedule_id", "default_ucr_fee_schedule_id"):
            if moved(field) and payload[field] is not None:
                ok = db.execute(select(FeeSchedule.id).where(
                    FeeSchedule.id == payload[field], FeeSchedule.tenant_id == tid)).first()
                if ok is None:
                    raise field_error(field, "Unknown fee schedule", "fee_schedule_not_found")
        if moved("office_group_id") and payload["office_group_id"] is not None:
            ok = db.execute(select(OfficeGroup.id).where(
                OfficeGroup.id == payload["office_group_id"], OfficeGroup.tenant_id == tid)).first()
            if ok is None:
                raise field_error("office_group_id", "Unknown office group", "office_group_not_found")
    return payload
