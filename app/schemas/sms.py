"""SMS / e-mail DTOs (Patient -> Messages, SMS/Email log; SMS-1…9, EMAIL-1).

The ``SmsMessageRead`` the generic ``/sms-messages`` resource returns is built
from the ORM model (so every SMS-3 column is on the wire automatically) and
specialised with the SMS-6 denormalised names.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.db.models import EmailMessage, SmsMessage, SmsTemplate
from app.schemas.factory import build_schemas

# ── sms_messages ─────────────────────────────────────────────────────────────
SmsMessageCreate, SmsMessageUpdate, _SmsRead = build_schemas(
    SmsMessage, "SmsMessage",
    create_exclude=("twilio_sid", "reply_twilio_sid", "inbound_payload_hash",
                    "status_payload_hash", "updated_at"),
    update_exclude=("twilio_sid", "reply_twilio_sid", "inbound_payload_hash",
                    "status_payload_hash", "updated_at", "tenant_id", "created_by"),
)


class SmsMessageRead(_SmsRead):  # type: ignore[valid-type, misc]
    """SMS-6: denormalised so the inbox never fans out per row."""

    patient_first_name: str | None = None
    patient_last_name: str | None = None
    patient_name: str | None = None
    patient_chart_no: str | None = None
    office_name: str | None = None
    template_name: str | None = None
    created_by_name: str | None = None


# ── sms_templates (SMS-5) ────────────────────────────────────────────────────
SmsTemplateCreate, SmsTemplateUpdate, SmsTemplateRead = build_schemas(
    SmsTemplate, "SmsTemplate",
    create_exclude=("created_by", "updated_by"),
    update_exclude=("tenant_id", "created_by", "updated_by"),
)

# ── email_messages (EMAIL-1) ─────────────────────────────────────────────────
EmailMessageCreate, EmailMessageUpdate, EmailMessageRead = build_schemas(
    EmailMessage, "EmailMessage",
    create_exclude=("provider_message_id", "status_payload_hash", "updated_at"),
    update_exclude=("provider_message_id", "status_payload_hash", "updated_at",
                    "tenant_id", "created_by"),
)


# ── SMS-1 send gateway ───────────────────────────────────────────────────────
class SmsSendRequest(BaseModel):
    patient_id: int
    office_id: int | None = None
    appointment_id: str | None = None
    to_phone: str = Field(..., description="E.164 (+1…); US 10-digit numbers are normalised")
    body: str = Field(..., min_length=1, max_length=1600)
    message_type: str = Field("manual", description="manual|appointment_reminder|appointment_confirmation|recall|balance|other")
    client_id: str | None = Field(None, max_length=40, description="Idempotency key — the same value never sends twice")
    template_id: int | None = None
    override_consent: bool = Field(
        False, description="SMS-8: required to send a *manual* text to a patient with no_auto_sms")


class SmsGatewayStatus(BaseModel):
    configured: bool
    mode: str = Field(..., description="live | log_only")
    webhook_validation: bool
    webhook_signing_ready: bool
    status_callback_url: str | None = None
    messaging_service_configured: bool
    quiet_hours: dict | None = None
    reminders_enabled: bool | None = None


class SmsSenderResolution(BaseModel):
    office_id: int | None
    from_phone: str | None
    messaging_service_sid: str | None
    source: str = Field(..., description="office_specific|multi_office_shared|tenant_default|platform_default|none")


# ── SMS-5 render ─────────────────────────────────────────────────────────────
class SmsRenderRequest(BaseModel):
    patient_id: int
    body: str | None = Field(None, description="Raw body with {{merge_fields}}; or pass template_id")
    template_id: int | None = None
    appointment_id: str | None = None
    office_id: int | None = None


class SmsRenderResult(BaseModel):
    body: str
    unresolved_fields: list[str]
    context: dict[str, str]
    template_id: int | None = None
    message_type: str | None = None
    length: int
    segments: int


# ── SMS-6 inbox ──────────────────────────────────────────────────────────────
class SmsInboxOfficeSummary(BaseModel):
    office_id: int | None
    office_name: str | None
    unread_replies: int
    needs_attention: int
    unmatched: int
    failed: int


class SmsInboxSummary(BaseModel):
    unread_replies: int
    needs_attention: int
    unmatched: int
    failed: int
    offices: list[SmsInboxOfficeSummary]


class SmsMarkReadRequest(BaseModel):
    patient_id: int | None = None
    office_id: int | None = None


class SmsMarkReadResult(BaseModel):
    updated: int


# ── SMS-9 reminders ──────────────────────────────────────────────────────────
class SmsReminderRunRequest(BaseModel):
    dry_run: bool = False


class SmsReminderRunResult(BaseModel):
    tenants: int
    scanned: int
    sent: int
    failed: int
    skipped: dict[str, int]
    dry_run: bool
    items: list[dict]


# ── metadata ─────────────────────────────────────────────────────────────────
class SmsMetadata(BaseModel):
    message_types: list[str]
    sendable_message_types: list[str]
    send_statuses: list[str]
    reply_intents: list[str]
    directions: list[str]
    merge_fields: list[str]
    max_body_length: int
    stop_keywords: list[str]
    start_keywords: list[str]
    reply_window_hours: int
    default_reminder_body: str
    default_reminder_lead_hours: list[int]


# ── EMAIL-1 ──────────────────────────────────────────────────────────────────
class EmailSendRequest(BaseModel):
    patient_id: int
    office_id: int | None = None
    appointment_id: str | None = None
    to_email: str | None = Field(None, description="Defaults to the patient's e-mail")
    subject: str = Field(..., min_length=1, max_length=500)
    body_html: str | None = None
    body_text: str | None = None
    message_type: str = "manual"
    client_id: str | None = Field(None, max_length=40)
    override_consent: bool = False


class EmailGatewayStatus(BaseModel):
    configured: bool
    mode: str
    provider: str | None = None
    from_email: str | None = None
    webhook_validation: bool
    webhook_signing_ready: bool


class EmailMetadata(BaseModel):
    message_types: list[str]
    send_statuses: list[str]


class WebhookAck(BaseModel):
    ok: bool
    applied: int = 0


__all__ = [
    "SmsMessageCreate", "SmsMessageUpdate", "SmsMessageRead",
    "SmsTemplateCreate", "SmsTemplateUpdate", "SmsTemplateRead",
    "EmailMessageCreate", "EmailMessageUpdate", "EmailMessageRead",
    "SmsSendRequest", "SmsGatewayStatus", "SmsSenderResolution",
    "SmsRenderRequest", "SmsRenderResult", "SmsInboxSummary", "SmsInboxOfficeSummary",
    "SmsMarkReadRequest", "SmsMarkReadResult", "SmsReminderRunRequest", "SmsReminderRunResult",
    "SmsMetadata", "EmailSendRequest", "EmailGatewayStatus", "EmailMetadata", "WebhookAck",
    "date",
]
