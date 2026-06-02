"""Account settings service — 1:1 per-tenant Basic + Advanced config + logo.

Settings rows are created on first access (upsert semantics) so the FE always
gets a row to bind to. The AI-assist client secret is encrypted at rest and never
returned; the logo is stored on the configured upload dir and served by URL.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings as cfg
from app.core.crypto import encrypt
from app.core.exceptions import ValidationError
from app.db.models.account import AccountSettings
from app.schemas.account import AccountSettingsRead

_EXT_BY_TYPE = {"image/jpeg": ".jpg", "image/png": ".png"}


def get_or_create_settings(db: Session, tenant_id: int) -> AccountSettings:
    row = db.execute(
        select(AccountSettings).where(AccountSettings.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if row is None:
        row = AccountSettings(tenant_id=tenant_id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def update_settings(db: Session, tenant_id: int, data: dict, user_id: int | None) -> AccountSettings:
    row = get_or_create_settings(db, tenant_id)
    secret = data.pop("ai_assist_client_secret", None)
    if secret is not None:  # only rotate when explicitly provided
        row.ai_assist_client_secret_enc = encrypt(secret) if secret else None
    for key, value in data.items():
        if hasattr(row, key):
            setattr(row, key, value)
    row.updated_by = user_id
    db.commit()
    db.refresh(row)
    return row


def to_read(row: AccountSettings) -> AccountSettingsRead:
    out = AccountSettingsRead.model_validate(row)
    out.ai_assist_has_secret = bool(row.ai_assist_client_secret_enc)
    return out


# ── Logo ─────────────────────────────────────────────────────────────────────
def save_logo(db: Session, tenant_id: int, filename: str, content_type: str, data: bytes) -> str:
    if content_type not in cfg.LOGO_ALLOWED_TYPES:
        raise ValidationError(
            f"Unsupported logo type '{content_type}'. Allowed: {', '.join(cfg.LOGO_ALLOWED_TYPES)}",
            code="invalid_logo_type",
        )
    if len(data) > cfg.LOGO_MAX_BYTES:
        raise ValidationError(
            f"Logo exceeds {cfg.LOGO_MAX_BYTES // (1024 * 1024)} MB limit", code="logo_too_large"
        )
    ext = _EXT_BY_TYPE.get(content_type, Path(filename).suffix or ".img")
    logo_dir = Path(cfg.UPLOAD_DIR) / "logos"
    logo_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"tenant_{tenant_id}{ext}"
    (logo_dir / stored_name).write_bytes(data)

    url = f"{cfg.UPLOAD_URL_BASE}/logos/{stored_name}"
    row = get_or_create_settings(db, tenant_id)
    row.logo_url = url
    db.commit()
    return url


def delete_logo(db: Session, tenant_id: int) -> None:
    row = get_or_create_settings(db, tenant_id)
    if row.logo_url:
        stored = Path(cfg.UPLOAD_DIR) / "logos" / Path(row.logo_url).name
        try:
            stored.unlink(missing_ok=True)
        except OSError:
            pass
    row.logo_url = None
    db.commit()
