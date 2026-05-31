# app/models/group.py

from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, TIMESTAMP
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class Group(Base):
    """
    Group definitions table.
    Groups are identified by codes like "GRP-001", "GRP-002", etc.
    """
    __tablename__ = "groups"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True, index=True)
    
    tenant_id = Column(
        Integer,
        ForeignKey("public.tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    code = Column(String(50), nullable=False, unique=True, index=True)  # e.g., "GRP-001"
    name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=True)
    
    # Relationships
    user_memberships = relationship(
        "UserGroupMembership",
        back_populates="group",
        cascade="all, delete-orphan"
    )


class UserGroupMembership(Base):
    """
    Junction table linking users to groups.
    Represents which groups a user belongs to.
    """
    __tablename__ = "user_group_memberships"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True, index=True)
    
    user_id = Column(
        Integer,
        ForeignKey("public.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    group_id = Column(
        Integer,
        ForeignKey("public.groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    tenant_id = Column(
        Integer,
        ForeignKey("public.tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    assigned_by = Column(
        Integer,
        ForeignKey("public.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    
    # Relationships
    user = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="group_memberships"
    )
    
    group = relationship(
        "Group",
        back_populates="user_memberships"
    )
    
    assigned_by_user = relationship(
        "User",
        foreign_keys=[assigned_by]
    )
