"""Imaging, collections, and referral-demographics models.

image_groups · image_details · collection_agencies · referral_demog_headers ·
referral_demog_details
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin, TimestampMixin


class ImageGroup(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "image_groups"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    patient_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("patients.id"), index=True)
    template_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("imaging_templates.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str | None] = mapped_column(String(255))
    group_type: Mapped[str | None] = mapped_column(String(20))
    ext_id: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str | None] = mapped_column(String(50))
    source2: Mapped[str | None] = mapped_column(String(50))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String(100))


class ImageDetail(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "image_details"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    image_group_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("image_groups.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    tile_id: Mapped[str | None] = mapped_column(String(20))
    filename: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    teeth: Mapped[str | None] = mapped_column(String(100))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class CollectionAgency(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "collection_agencies"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(255))
    address2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(50))
    zip: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(20))
    created_by: Mapped[str | None] = mapped_column(String(100))


class ReferralDemogHeader(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "referral_demog_headers"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(String(255))
    created_by: Mapped[str | None] = mapped_column(String(100))


class ReferralDemogDetail(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "referral_demog_details"

    referral_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("referrals.id"), index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    demog_header_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("referral_demog_headers.id"))
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    data: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(100))
