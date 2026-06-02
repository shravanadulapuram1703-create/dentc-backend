"""Online-registration consent service — versioned, one active per tenant.

Each save creates a new version and archives the previously-active one (backend-
implicit versioning; the UI shows only Header + Body). ``body_html`` is sanitized
before storage. Patient signature snapshots can later reference a consent id.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.core.html_sanitize import sanitize_html
from app.db.models.account import AccountConsent


def list_consents(db: Session, tenant_id: int) -> list[AccountConsent]:
    return list(
        db.execute(
            select(AccountConsent)
            .where(AccountConsent.tenant_id == tenant_id)
            .order_by(AccountConsent.version_number.desc())
        ).scalars().all()
    )


def get_active(db: Session, tenant_id: int) -> AccountConsent:
    row = db.execute(
        select(AccountConsent).where(
            AccountConsent.tenant_id == tenant_id, AccountConsent.is_active.is_(True)
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("No active consent for this account")
    return row


def get_consent(db: Session, tenant_id: int, consent_id: int) -> AccountConsent:
    row = db.execute(
        select(AccountConsent).where(
            AccountConsent.id == consent_id, AccountConsent.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"Consent '{consent_id}' was not found")
    return row


def create_consent(
    db: Session, tenant_id: int, header: str, body_html: str,
    effective_date: date | None, user_id: int | None,
) -> AccountConsent:
    now = datetime.now(timezone.utc)
    # Archive the currently-active consent (if any).
    current = db.execute(
        select(AccountConsent).where(
            AccountConsent.tenant_id == tenant_id, AccountConsent.is_active.is_(True)
        )
    ).scalars().all()
    max_version = db.execute(
        select(AccountConsent.version_number)
        .where(AccountConsent.tenant_id == tenant_id)
        .order_by(AccountConsent.version_number.desc())
        .limit(1)
    ).scalar_one_or_none() or 0
    for row in current:
        row.is_active = False
        row.archived_at = now

    consent = AccountConsent(
        tenant_id=tenant_id,
        version_number=max_version + 1,
        header=header,
        body_html=sanitize_html(body_html),
        is_active=True,
        effective_date=effective_date or now.date(),
        created_by=user_id,
    )
    db.add(consent)
    db.commit()
    db.refresh(consent)
    return consent
