"""Audit logging (Phase 3 / HIPAA).

Append-only access+change log. Not part of the Denticon migration — created by
its own Alembic revision. High-volume, so a BIGINT surrogate key.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    # SQLite only auto-increments an INTEGER PRIMARY KEY, so under the in-memory
    # test engine a BigInteger PK made every ``AuditLog()`` insert fail on
    # ``NOT NULL constraint failed: audit_logs.id`` — silently, because the audit
    # writers are exception-safe. Postgres keeps BIGINT (no migration).
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    tenant_id: Mapped[int | None] = mapped_column(Integer, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(20))
    resource_type: Mapped[str | None] = mapped_column(String(100), index=True)
    resource_id: Mapped[str | None] = mapped_column(String(100))
    # MH-19: the chart a mutation belongs to, so a patient-scoped, non-admin
    # read ("everything that happened to this chart") is one indexed filter.
    # Resolved from the CRUD engine's audit context, the 201 body, or the path.
    patient_id: Mapped[int | None] = mapped_column(Integer, index=True)
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(500))
    status_code: Mapped[int | None] = mapped_column(Integer)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
