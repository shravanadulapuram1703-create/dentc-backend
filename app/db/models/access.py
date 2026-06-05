"""User access/profile sub-resources (Phase 4, net-new — not in the migration).

user_preferences · user_groups · user_group_memberships · user_ip_rules

These back the UserSetup advanced tabs. Storage only — IP-rule *enforcement* is a
separate, larger task. Group semantics deliberately stay simple and do not
constitute the deferred Phase-4 RBAC system.
"""

from __future__ import annotations

from datetime import time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin, TimestampMixin


class UserPreference(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "user_preferences"
    __table_args__ = (UniqueConstraint("user_id", "pref_key", name="uq_user_preferences_user_key"),)

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    pref_key: Mapped[str] = mapped_column(String(100))
    pref_value: Mapped[str | None] = mapped_column(Text)


class UserGroup(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "user_groups"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class UserGroupMembership(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "user_group_memberships"
    __table_args__ = (UniqueConstraint("user_id", "group_id", name="uq_user_group_memberships_user_group"),)

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_groups.id"), index=True)


class UserIpRule(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "user_ip_rules"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    ip_address: Mapped[str] = mapped_column(String(45))
    rule_type: Mapped[str] = mapped_column(String(10), default="allow")  # 'allow' | 'deny'
    description: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class UserTimeClockConfig(Base, IntPKMixin, TimestampMixin):
    """1:1 per-user time-clock configuration (Users module gap #3).

    Distinct from ``time_clock_entries`` (punch records) — this is the config.
    """

    __tablename__ = "user_time_clock_config"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_time_clock_config_user"),)

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    pay_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    overtime_method: Mapped[str | None] = mapped_column(String(50))
    overtime_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    clock_in_required: Mapped[bool] = mapped_column(Boolean, default=False)


class UserLoginRestriction(Base, IntPKMixin, TimestampMixin):
    """1:1 per-user login window (Users module gap #4)."""

    __tablename__ = "user_login_restrictions"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_login_restrictions_user"),)

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    is_24_7: Mapped[bool] = mapped_column(Boolean, default=True)
    allowed_days: Mapped[str | None] = mapped_column(String(50))  # CSV e.g. "Mon,Tue,Wed"
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
