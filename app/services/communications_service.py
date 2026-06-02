"""Communications service — TCR/Twilio business profile, telecom verification,
and office phone-number assignments.

EIN is encrypted at rest and returned masked. Telecom verification is a stub that
records status/timestamp (a real telecom-provider sync is a separate integration).
The "max 5 Office-Specific" rule is enforced on phone-assignment replacement.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt, encrypt, mask
from app.core.exceptions import ValidationError
from app.db.models.account import AccountCommunications, OfficePhoneAssignment

MAX_OFFICE_SPECIFIC = 5


def get_or_create(db: Session, tenant_id: int) -> AccountCommunications:
    row = db.execute(
        select(AccountCommunications).where(AccountCommunications.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if row is None:
        row = AccountCommunications(tenant_id=tenant_id)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def update(db: Session, tenant_id: int, data: dict, user_id: int | None) -> AccountCommunications:
    row = get_or_create(db, tenant_id)
    ein = data.pop("ein", None)
    if ein is not None:
        row.ein_enc = encrypt(ein) if ein else None
    for key, value in data.items():
        if hasattr(row, key):
            setattr(row, key, value)
    row.updated_by = user_id
    db.commit()
    db.refresh(row)
    return row


def ein_masked(row: AccountCommunications) -> str | None:
    return mask(decrypt(row.ein_enc), visible=4)


def verify_telecom(db: Session, tenant_id: int, user_id: int | None) -> AccountCommunications:
    row = get_or_create(db, tenant_id)
    # Stub: a real implementation would call the telecom provider and poll status.
    row.telecom_status = "submitted"
    row.telecom_verified_at = datetime.now(timezone.utc)
    row.telecom_verified_by = user_id
    db.commit()
    db.refresh(row)
    return row


def list_phone_assignments(db: Session, tenant_id: int) -> list[OfficePhoneAssignment]:
    return list(
        db.execute(
            select(OfficePhoneAssignment)
            .where(OfficePhoneAssignment.tenant_id == tenant_id)
            .order_by(OfficePhoneAssignment.office_id.asc())
        ).scalars().all()
    )


def replace_phone_assignments(
    db: Session, tenant_id: int, assignments: list[dict]
) -> list[OfficePhoneAssignment]:
    office_specific = sum(1 for a in assignments if a.get("assignment_type") == "office_specific")
    if office_specific > MAX_OFFICE_SPECIFIC:
        raise ValidationError(
            f"At most {MAX_OFFICE_SPECIFIC} Office-Specific phone assignments are allowed",
            code="too_many_office_specific",
        )
    db.execute(sa_delete(OfficePhoneAssignment).where(OfficePhoneAssignment.tenant_id == tenant_id))
    rows = [OfficePhoneAssignment(tenant_id=tenant_id, **a) for a in assignments]
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows
