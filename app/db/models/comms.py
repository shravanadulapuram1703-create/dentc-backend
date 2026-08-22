"""Communications domain models.

sms_messages · letter_templates · postcard_templates ·
letter_batch_runs · letter_batch_items · campaigns
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin


class SmsMessage(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "sms_messages"

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
