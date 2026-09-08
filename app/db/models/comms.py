"""Communications domain models.

sms_messages · sms_templates · email_messages · letter_templates ·
postcard_templates · letter_batch_runs · letter_batch_items · campaigns
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin, TimestampMixin


class SmsMessage(Base, IntPKMixin, CreatedAtMixin):
    """One row per outbound text, with the reply on the same row (legacy shape).

    SMS-3 adds the Twilio correlation/delivery columns. The legacy shape is kept
    on purpose — the frontend fans a row out into an outbound entry (``sent_text``)
    and an inbound entry (``reply_text``); a stand-alone inbound text is a row
    with ``sent_text IS NULL`` and ``direction='inbound'``.
    """

    __tablename__ = "sms_messages"
    __table_args__ = (
        # SMS-1: idempotent sends — the same client_id must never send twice.
        UniqueConstraint("tenant_id", "client_id", name="uq_sms_messages_tenant_client_id"),
        # SMS-6: the practice-wide inbox pages by office + time.
        Index("ix_sms_messages_office_sent_at", "office_id", "sent_at"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    patient_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    appointment_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("appointments.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    sent_text: Mapped[str | None] = mapped_column(Text)
    sent_phone: Mapped[str | None] = mapped_column(String(20))
    send_status: Mapped[str | None] = mapped_column(String(50))
    delivered_on: Mapped[datetime | None]
    reply_text: Mapped[str | None] = mapped_column(Text)
    reply_phone: Mapped[str | None] = mapped_column(String(20))
    reply_received_on: Mapped[datetime | None]
    message_type: Mapped[str | None] = mapped_column(String(50))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    # ── SMS-3: Twilio correlation + delivery detail ──────────────────────────
    twilio_sid: Mapped[str | None] = mapped_column(String(34), unique=True)
    # The reply is stored on the outbound row (legacy parity), so its own Twilio
    # sid needs a home too — that is what makes the inbound webhook idempotent.
    reply_twilio_sid: Mapped[str | None] = mapped_column(String(34), unique=True)
    from_phone: Mapped[str | None] = mapped_column(String(20))
    direction: Mapped[str | None] = mapped_column(String(10))  # outbound | inbound
    sent_at: Mapped[datetime | None]
    error_code: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    segments: Mapped[int | None] = mapped_column(SmallInteger)
    client_id: Mapped[str | None] = mapped_column(String(40))
    template_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("sms_templates.id"))
    # SMS-2 step 3: what the patient's reply meant (confirm|reschedule|cancel|
    # stop|start|help|other) and whether staff still need to look at it.
    reply_intent: Mapped[str | None] = mapped_column(String(20))
    needs_attention: Mapped[bool] = mapped_column(Boolean, default=False)
    # SMS-2 step 1: several patients (a family) shared the inbound number and none
    # had a recent text from this office — the row is unmatched, but staff can
    # still see who it might be.
    candidate_patient_ids: Mapped[list | None] = mapped_column(JSON)
    # SMS-9: which lead-time bucket an automated reminder was sent for; part of
    # the (appointment_id, message_type, reminder_lead_hours) dedupe key.
    reminder_lead_hours: Mapped[int | None] = mapped_column(SmallInteger)
    # SMS-10: SHA-256 of the raw webhook payloads that touched this row, kept for
    # carrier disputes without retaining the (PHI-adjacent) payload itself.
    inbound_payload_hash: Mapped[str | None] = mapped_column(String(64))
    status_payload_hash: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime | None]


class SmsTemplate(Base, IntPKMixin, TimestampMixin):
    """SMS-5: practice-authored text templates (were browser localStorage).

    ``office_id`` NULL = shared by every office of the tenant. Merge-field
    syntax is ``{{patient_first_name}}`` etc. — see ``sms_service.MERGE_FIELDS``.
    """

    __tablename__ = "sms_templates"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    message_type: Mapped[str] = mapped_column(String(50), default="manual")
    body: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class EmailMessage(Base, IntPKMixin, CreatedAtMixin):
    """EMAIL-1: the e-mail counterpart of ``sms_messages`` (one row per send).

    ``provider_message_id`` correlates the SendGrid event webhook the same way
    ``twilio_sid`` does for texts. ``send_status`` uses SendGrid's event
    vocabulary (queued|processed|delivered|deferred|bounce|dropped|open|click|
    spamreport|unsubscribe|failed).
    """

    __tablename__ = "email_messages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "client_id", name="uq_email_messages_tenant_client_id"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    patient_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    appointment_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("appointments.id"))
    to_email: Mapped[str] = mapped_column(String(255))
    from_email: Mapped[str | None] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(500))
    body_html: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(20))  # sendgrid | none
    provider_message_id: Mapped[str | None] = mapped_column(String(120), index=True)
    send_status: Mapped[str] = mapped_column(String(30), default="queued")
    sent_at: Mapped[datetime | None]
    delivered_at: Mapped[datetime | None]
    opened_at: Mapped[datetime | None]
    error_message: Mapped[str | None] = mapped_column(Text)
    message_type: Mapped[str | None] = mapped_column(String(50))
    client_id: Mapped[str | None] = mapped_column(String(40))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    status_payload_hash: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    updated_at: Mapped[datetime | None]


class LetterTemplate(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "letter_templates"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(255))
    letter_type: Mapped[str | None] = mapped_column(String(10))
    channel: Mapped[str | None] = mapped_column(String(20))
    title: Mapped[str | None] = mapped_column(String(255))
    body_html: Mapped[str | None] = mapped_column(Text)
    is_editable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PostcardTemplate(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "postcard_templates"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(255))
    card_type: Mapped[str | None] = mapped_column(String(10))
    body: Mapped[str | None] = mapped_column(Text)


class LetterBatchRun(Base, IntPKMixin, CreatedAtMixin):
    """LTR-5: one server-side batch letter run (the ``CS001…CS009 - Batch Coll N``
    templates are meaningless per-patient — they are meant to sweep a collections
    queue), plus the durable job record the UI polls for a job id.

    The run header holds the counters; per-patient outcomes live in
    :class:`LetterBatchItem` so a 500-patient run doesn't become one giant JSON blob.
    """

    __tablename__ = "letter_batch_runs"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    template_id: Mapped[int] = mapped_column(Integer, ForeignKey("letter_templates.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|completed|failed
    requested: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    succeeded: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    options: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None]
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class LetterBatchItem(Base, IntPKMixin, CreatedAtMixin):
    """One patient's outcome inside a :class:`LetterBatchRun`.

    ``rendered_html`` is only retained when the caller asks for it — a batch over
    a collections queue is normally consumed as a single print stream, not as 500
    stored bodies.
    """

    __tablename__ = "letter_batch_items"

    batch_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("letter_batch_runs.id"), index=True
    )
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="rendered")  # rendered|skipped|failed
    unresolved_tokens: Mapped[list | None] = mapped_column(JSON)
    rendered_html: Mapped[str | None] = mapped_column(Text)
    document_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("patient_documents.id"))
    error: Mapped[str | None] = mapped_column(Text)


class Campaign(Base, IntPKMixin, CreatedAtMixin):
    """APPT-7: the marketing campaign an appointment can be attributed to.

    ``appointments.campaign_id`` was free text with nothing to pick from, so the
    field was an unvalidated box and campaign roll-ups were impossible. This is
    the catalog behind it: the appointment still stores the campaign **code**
    (a string, unchanged on the wire), and this table gives the picker its
    options and the reports a name/date-window to group by.
    """

    __tablename__ = "campaigns"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_campaigns_tenant_code"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    code: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    # Marketing channel (mail / email / sms / referral / web / other) — free text so
    # a practice can name its own; the FE offers the common set.
    channel: Mapped[str | None] = mapped_column(String(50))
    start_date: Mapped[date | None]
    end_date: Mapped[date | None]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
