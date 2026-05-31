"""Declarative base, naming convention, and shared column mixins.

All models inherit from :class:`Base`. The explicit naming convention keeps
Alembic autogenerate deterministic. Mixins provide the audit / tenancy columns
that recur across nearly every migrated table.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IntPKMixin:
    """SERIAL integer primary key (the default for most tables)."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())


class CreatedAtMixin:
    """For append-only / reference tables that only track creation."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class TenantMixin:
    """Direct tenant scoping. Present on org / patient / reference root tables."""

    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=False, index=True
    )


class LegacyIdMixin:
    """Source-system identifier carried from the Denticon migration (read-only)."""

    legacy_id: Mapped[str | None] = mapped_column(index=True)


def created_by_fk() -> Mapped[int | None]:
    return mapped_column(Integer, ForeignKey("users.id"))


__all__ = [
    "Base",
    "IntPKMixin",
    "TimestampMixin",
    "CreatedAtMixin",
    "TenantMixin",
    "LegacyIdMixin",
    "BigInteger",
]
