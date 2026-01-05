# app/models/tenant.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    TIMESTAMP,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True, index=True)

    # Canonical tenant identifier (formerly tenant_key)
    code = Column(String(80), unique=True, nullable=False, index=True)

    name = Column(String(255), nullable=False)

    status = Column(
        String(20),
        default="active",
        nullable=False,  # active | suspended | deleted
    )

    is_active = Column(Boolean, default=True, nullable=False)
    is_locked = Column(Boolean, default=False, nullable=False)

    created_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    created_by = Column(
        Integer,
        ForeignKey("public.users.id", ondelete="SET NULL"),
        nullable=True,
    )

    creator = relationship(
        "User",
        foreign_keys=[created_by],
        lazy="joined",
    )

    offices = relationship("Office", back_populates="tenant")