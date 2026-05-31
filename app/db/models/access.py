"""User access/profile sub-resources (Phase 4, net-new — not in the migration).

user_preferences · user_groups · user_group_memberships · user_ip_rules

These back the UserSetup advanced tabs. Storage only — IP-rule *enforcement* is a
separate, larger task. Group semantics deliberately stay simple and do not
constitute the deferred Phase-4 RBAC system.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
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
