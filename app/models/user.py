# app/models/user.py

from sqlalchemy import (
    Column, Integer, String, Boolean, Time,
    DateTime, ForeignKey, ARRAY, TIMESTAMP,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
from app.models.associations import user_permissions
from app.models.user_role import UserRole


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(
        Integer,
        ForeignKey("public.tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email = Column(String(255), unique=True, nullable=False, index=True)
    # email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String(50), nullable=False)  # legacy / convenience
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    is_platform_user = Column(Boolean, default=False, nullable=False)
    is_locked = Column(Boolean, default=False, nullable=False)
    created_by = Column(
        Integer,
        ForeignKey("public.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_login_at = Column(TIMESTAMP, nullable=True)

    username = Column(String(50), unique=True, nullable=False)
    first_name = Column(String(100))
    last_name = Column(String(100))
    short_id = Column(String(6))
    phone = Column(String(20))
    patient_access_level = Column(String(50))  # all_offices / home_office
    allowed_days = Column(ARRAY(String))
    allowed_from = Column(Time)
    allowed_until = Column(Time)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by = Column(String(50))

    # self-referential relationship (creator)
    creator = relationship(
        "User",
        remote_side=[id],
        backref="created_users",
        foreign_keys=[created_by],
    )

    # RBAC mappings
    # user_roles = relationship(
    #     "UserRole",
    #     foreign_keys="UserRole.user_id",
    #     cascade="all, delete-orphan",
    #     back_populates="user",
    #     lazy="joined",
    # )
    user_roles = relationship(
        "UserRole",
        foreign_keys="UserRole.user_id",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    permissions = relationship(
        "Permission",
        secondary=user_permissions,
        lazy="joined",
    )

    refresh_tokens = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    office = relationship(
        "UserOffice",
        back_populates="users",
        cascade="all, delete-orphan"
    )
    # offices = relationship("UserOffice", back_populates="user", cascade="all, delete")
    # groups = relationship("UserGroup", back_populates="user", cascade="all, delete")
    ip_rules = relationship("UserIPRule", back_populates="user", cascade="all, delete")
    time_clock = relationship("UserTimeClock", uselist=False, back_populates="user")
    # preferences = relationship("UserPreference", uselist=False, back_populates="user")
    preferences = relationship(
    "UserPreference",
    uselist=False,
    back_populates="user",
    cascade="all, delete-orphan",
)
    group_memberships = relationship(
        "UserGroupMembership",
        foreign_keys="UserGroupMembership.user_id",
        back_populates="user",
        cascade="all, delete-orphan"
    )


    @property
    def roles(self):
        return [ur.role for ur in self.user_roles]
