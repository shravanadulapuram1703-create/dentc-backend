"""Office Setup service — per-office configuration (gaps #10–#17).

Every office-scoped operation first verifies the office belongs to the
authenticated tenant (``get_office_in_tenant``). 1:1 settings rows are created on
first access (upsert). Secrets (DoseSpot key) are encrypted at rest and returned
masked. The office logo is stored on the configured upload dir and served by URL.
"""

from __future__ import annotations

from datetime import time
from pathlib import Path
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings as cfg
from app.core.crypto import decrypt, encrypt, mask
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.db.models import FeeSchedule, Office, Provider
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
    row = db.execute(
        select(model).where(model.office_id == office_id)
    ).scalar_one_or_none()
    if row is None:
        row = model(office_id=office_id, tenant_id=tenant_id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def update_singleton(
    db: Session, model: type, office_id: int, tenant_id: int, data: dict, user_id: int | None
):
    row = get_or_create_singleton(db, model, office_id, tenant_id)
    for key, value in data.items():
        if hasattr(row, key):
            setattr(row, key, value)
    if hasattr(row, "updated_by"):
        row.updated_by = user_id
    db.commit()
    db.refresh(row)
    return row


# ── Integrations (#13) — DoseSpot key encrypted/masked ───────────────────────
def update_integrations(db: Session, office_id: int, tenant_id: int, data: dict, user_id: int | None):
    key = data.pop("dosespot_key", None)
    row = get_or_create_singleton(db, OfficeIntegrations, office_id, tenant_id)
    if key is not None:
        row.dosespot_key_enc = encrypt(key) if key else None
    for k, v in data.items():
        if hasattr(row, k):
            setattr(row, k, v)
    row.updated_by = user_id
    db.commit()
    db.refresh(row)
    return row


def dosespot_key_masked(row: OfficeIntegrations) -> str | None:
    return mask(decrypt(row.dosespot_key_enc), visible=4)


# ── Schedule (#14) — 7-day weekly grid ───────────────────────────────────────
_DEFAULT_OPEN = (time(8, 0), time(17, 0))


def get_schedule(db: Session, office_id: int, tenant_id: int) -> list[OfficeScheduleDay]:
    rows = list(db.execute(
        select(OfficeScheduleDay).where(OfficeScheduleDay.office_id == office_id)
        .order_by(OfficeScheduleDay.day_of_week.asc())
    ).scalars().all())
    if not rows:  # seed Mon–Fri open, weekend closed
        rows = [
            OfficeScheduleDay(
                tenant_id=tenant_id, office_id=office_id, day_of_week=d,
                is_closed=d >= 5,
                start_time=None if d >= 5 else _DEFAULT_OPEN[0],
                end_time=None if d >= 5 else _DEFAULT_OPEN[1],
            )
            for d in range(7)
        ]
        db.add_all(rows)
        db.commit()
        for r in rows:
            db.refresh(r)
    return rows


def replace_schedule(
    db: Session, office_id: int, tenant_id: int, days: list[dict]
) -> list[OfficeScheduleDay]:
    seen = {d["day_of_week"] for d in days}
    if seen - set(range(7)):
        raise ValidationError("day_of_week must be 0–6 (Mon–Sun)", code="invalid_day")
    db.execute(sa_delete(OfficeScheduleDay).where(OfficeScheduleDay.office_id == office_id))
    rows = [OfficeScheduleDay(tenant_id=tenant_id, office_id=office_id, **d) for d in days]
    db.add_all(rows)
    db.commit()
    for r in rows:
        db.refresh(r)
    return sorted(rows, key=lambda r: r.day_of_week)


# ── SmartAssist (#17) — settings + items ─────────────────────────────────────
def get_smart_assist(db: Session, office_id: int, tenant_id: int) -> dict:
    settings_row = get_or_create_singleton(db, OfficeSmartAssist, office_id, tenant_id)
    items = list(db.execute(
        select(OfficeSmartAssistItem).where(OfficeSmartAssistItem.office_id == office_id)
        .order_by(OfficeSmartAssistItem.id.asc())
    ).scalars().all())
    return {"enabled": settings_row.enabled, "items": items}


def update_smart_assist(
    db: Session, office_id: int, tenant_id: int, enabled: bool | None,
    items: list[dict] | None, user_id: int | None,
) -> dict:
    settings_row = get_or_create_singleton(db, OfficeSmartAssist, office_id, tenant_id)
    if enabled is not None:
        settings_row.enabled = enabled
    settings_row.updated_by = user_id
    if items is not None:
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
