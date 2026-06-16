"""Provider Setup service — per-provider configuration (provider dev-report gaps #1–#6).

Every provider-scoped operation first verifies the provider belongs to the
authenticated tenant (``get_provider_in_tenant``). Secrets (carrier password) are
encrypted at rest and returned masked. Watermark images are stored on the
configured upload dir and served by URL.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings as cfg
from app.core.crypto import decrypt, encrypt, mask
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.db.models import Office, Provider, User
from app.db.models.provider_setup import (
    ProviderCarrierLogin,
    ProviderHoliday,
    ProviderReferralOffice,
    ProviderScheduleDay,
    ProviderWatermark,
)


def get_provider_in_tenant(db: Session, provider_id: str, tenant_id: int) -> Provider:
    provider = db.get(Provider, provider_id)
    if provider is None:
        raise NotFoundError(f"Provider '{provider_id}' was not found")
    if provider.tenant_id != tenant_id:
        raise ForbiddenError("Provider does not belong to the authenticated tenant")
    return provider


# ── Gap #1 Schedule ──────────────────────────────────────────────────────────
def get_schedule(db: Session, provider_id: str) -> list[ProviderScheduleDay]:
    return list(db.execute(
        select(ProviderScheduleDay)
        .where(ProviderScheduleDay.provider_id == provider_id)
        .order_by(ProviderScheduleDay.day_of_week.asc(), ProviderScheduleDay.id.asc())
    ).scalars().all())


def replace_schedule(
    db: Session, provider_id: str, tenant_id: int, days: list[dict]
) -> list[ProviderScheduleDay]:
    if any(not (0 <= d["day_of_week"] <= 6) for d in days):
        raise ValidationError("day_of_week must be 0–6 (Mon–Sun)", code="invalid_day")
    db.execute(sa_delete(ProviderScheduleDay).where(ProviderScheduleDay.provider_id == provider_id))
    rows = [ProviderScheduleDay(tenant_id=tenant_id, provider_id=provider_id, **d) for d in days]
    db.add_all(rows)
    db.commit()
    return get_schedule(db, provider_id)


# ── Gap #2 Holidays ──────────────────────────────────────────────────────────
def list_holidays(
    db: Session, provider_id: str, from_date: date | None = None, to_date: date | None = None
) -> list[ProviderHoliday]:
    stmt = select(ProviderHoliday).where(ProviderHoliday.provider_id == provider_id)
    if from_date is not None:
        stmt = stmt.where(ProviderHoliday.holiday_date >= from_date)
    if to_date is not None:
        stmt = stmt.where(ProviderHoliday.holiday_date <= to_date)
    return list(db.execute(stmt.order_by(ProviderHoliday.holiday_date.asc())).scalars().all())


def _get_holiday(db: Session, provider_id: str, holiday_id: int) -> ProviderHoliday:
    row = db.execute(
        select(ProviderHoliday).where(
            ProviderHoliday.id == holiday_id, ProviderHoliday.provider_id == provider_id
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"Holiday '{holiday_id}' was not found")
    return row


def create_holiday(db: Session, provider_id: str, tenant_id: int, data: dict, user_id: int | None) -> ProviderHoliday:
    row = ProviderHoliday(tenant_id=tenant_id, provider_id=provider_id, created_by=user_id, **data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_holiday(db: Session, provider_id: str, holiday_id: int, data: dict) -> ProviderHoliday:
    row = _get_holiday(db, provider_id, holiday_id)
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def delete_holiday(db: Session, provider_id: str, holiday_id: int) -> None:
    row = _get_holiday(db, provider_id, holiday_id)
    db.delete(row)
    db.commit()


# ── Gap #3 Watermarks ────────────────────────────────────────────────────────
def get_or_create_watermark(db: Session, provider_id: str, tenant_id: int) -> ProviderWatermark:
    row = db.execute(
        select(ProviderWatermark).where(ProviderWatermark.provider_id == provider_id)
    ).scalar_one_or_none()
    if row is None:
        row = ProviderWatermark(provider_id=provider_id, tenant_id=tenant_id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def update_watermark(db: Session, provider_id: str, tenant_id: int, data: dict, user_id: int | None) -> ProviderWatermark:
    row = get_or_create_watermark(db, provider_id, tenant_id)
    for key, value in data.items():
        if hasattr(row, key):
            setattr(row, key, value)
    row.updated_by = user_id
    db.commit()
    db.refresh(row)
    return row


_EXT_BY_TYPE = {"image/jpeg": ".jpg", "image/png": ".png"}
_WATERMARK_KINDS = {"watermark": "watermark_image_url", "signature": "signature_image_url"}


def save_watermark_image(
    db: Session, provider_id: str, tenant_id: int, kind: str,
    filename: str, content_type: str, data: bytes,
) -> ProviderWatermark:
    attr = _WATERMARK_KINDS.get(kind)
    if attr is None:
        raise ValidationError("kind must be 'watermark' or 'signature'", code="invalid_kind")
    if content_type not in cfg.LOGO_ALLOWED_TYPES:
        raise ValidationError(f"Unsupported image type '{content_type}'", code="invalid_image_type")
    if len(data) > cfg.LOGO_MAX_BYTES:
        raise ValidationError("Image exceeds size limit", code="image_too_large")
    ext = _EXT_BY_TYPE.get(content_type, Path(filename).suffix or ".img")
    img_dir = Path(cfg.UPLOAD_DIR) / "provider_watermarks"
    img_dir.mkdir(parents=True, exist_ok=True)
    stored = f"provider_{provider_id}_{kind}{ext}"
    (img_dir / stored).write_bytes(data)
    url = f"{cfg.UPLOAD_URL_BASE}/provider_watermarks/{stored}"
    row = get_or_create_watermark(db, provider_id, tenant_id)
    setattr(row, attr, url)
    db.commit()
    db.refresh(row)
    return row


def delete_watermark_image(db: Session, provider_id: str, tenant_id: int, kind: str) -> ProviderWatermark:
    attr = _WATERMARK_KINDS.get(kind)
    if attr is None:
        raise ValidationError("kind must be 'watermark' or 'signature'", code="invalid_kind")
    row = get_or_create_watermark(db, provider_id, tenant_id)
    url = getattr(row, attr)
    if url:
        try:
            (Path(cfg.UPLOAD_DIR) / "provider_watermarks" / Path(url).name).unlink(missing_ok=True)
        except OSError:
            pass
    setattr(row, attr, None)
    db.commit()
    db.refresh(row)
    return row


# ── Gap #4 Referral offices ──────────────────────────────────────────────────
def get_referral_offices(db: Session, provider_id: str) -> list[Office]:
    sub = select(ProviderReferralOffice.office_id).where(
        ProviderReferralOffice.provider_id == provider_id
    )
    return list(db.execute(
        select(Office).where(Office.id.in_(sub)).order_by(Office.name.asc())
    ).scalars().all())


def set_referral_offices(
    db: Session, provider_id: str, tenant_id: int, office_ids: list[int]
) -> list[Office]:
    existing = {
        link.office_id: link
        for link in db.execute(
            select(ProviderReferralOffice).where(ProviderReferralOffice.provider_id == provider_id)
        ).scalars()
    }
    desired = set(office_ids)
    for oid, link in existing.items():
        if oid not in desired:
            db.delete(link)
    for oid in desired:
        if oid not in existing:
            db.add(ProviderReferralOffice(tenant_id=tenant_id, provider_id=provider_id, office_id=oid))
    db.commit()
    return get_referral_offices(db, provider_id)


# ── Gap #5 Carrier logins ────────────────────────────────────────────────────
def carrier_password_masked(row: ProviderCarrierLogin) -> str | None:
    return mask(decrypt(row.password_enc), visible=2)


def list_carrier_logins(db: Session, tenant_id: int, provider_id: str | None = None) -> list[ProviderCarrierLogin]:
    stmt = select(ProviderCarrierLogin).where(ProviderCarrierLogin.tenant_id == tenant_id)
    if provider_id is not None:
        stmt = stmt.where(ProviderCarrierLogin.provider_id == provider_id)
    return list(db.execute(stmt.order_by(ProviderCarrierLogin.id.asc())).scalars().all())


def get_carrier_login(db: Session, tenant_id: int, login_id: int) -> ProviderCarrierLogin:
    row = db.execute(
        select(ProviderCarrierLogin).where(
            ProviderCarrierLogin.id == login_id, ProviderCarrierLogin.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"Carrier login '{login_id}' was not found")
    return row


def create_carrier_login(db: Session, tenant_id: int, data: dict, user_id: int | None) -> ProviderCarrierLogin:
    provider_id = data.get("provider_id")
    get_provider_in_tenant(db, provider_id, tenant_id)  # validate ownership
    password = data.pop("password", None)
    row = ProviderCarrierLogin(tenant_id=tenant_id, created_by=user_id, updated_by=user_id, **data)
    row.password_enc = encrypt(password) if password else None
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_carrier_login(db: Session, tenant_id: int, login_id: int, data: dict, user_id: int | None) -> ProviderCarrierLogin:
    row = get_carrier_login(db, tenant_id, login_id)
    password = data.pop("password", None)
    if password is not None:
        row.password_enc = encrypt(password) if password else None
    for key, value in data.items():
        if hasattr(row, key):
            setattr(row, key, value)
    row.updated_by = user_id
    db.commit()
    db.refresh(row)
    return row


def delete_carrier_login(db: Session, tenant_id: int, login_id: int) -> None:
    row = get_carrier_login(db, tenant_id, login_id)
    db.delete(row)
    db.commit()


# ── Gap #6 Provider ↔ user link ──────────────────────────────────────────────
def get_linked_user(db: Session, provider: Provider) -> User | None:
    if provider.user_id is None:
        return None
    return db.get(User, provider.user_id)


def set_linked_user(db: Session, provider: Provider, tenant_id: int, user_id: int | None) -> User | None:
    if user_id is not None:
        user = db.get(User, user_id)
        if user is None or user.tenant_id != tenant_id:
            raise ValidationError("User not found in this tenant", code="invalid_user")
    provider.user_id = user_id
    db.commit()
    db.refresh(provider)
    return get_linked_user(db, provider)
