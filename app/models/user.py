from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, TIMESTAMP
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
from app.models.associations import user_permissions#, user_roles 
from app.models.user_role import UserRole


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    tenant_id = Column(
        Integer,
        ForeignKey("public.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)

    role = Column(String(50), nullable=False)  # legacy / convenience
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

    # RBAC
    # roles = relationship(
    #     "Role",
    #     secondary=user_roles,
    #     back_populates="users",
    #     lazy="joined",
    # )
    user_roles = relationship(
        "UserRole",
        cascade="all, delete-orphan",
        back_populates="user",
        lazy="joined",
    )

    permissions = relationship(
        "Permission",
        secondary=user_permissions,
        lazy="joined",
    )

    refresh_tokens = relationship("RefreshToken", back_populates="user")

    @property
    def roles(self):
        return [ur.role for ur in self.user_roles]

