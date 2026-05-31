"""Communications domain models.

sms_messages · letter_templates · postcard_templates
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
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
