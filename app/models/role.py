from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.associations import role_permissions#, user_roles


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    tenant_id = Column(
        Integer,
        ForeignKey("public.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    name = Column(String(100), nullable=False)
    level = Column(Integer, nullable=False)
    is_system = Column(Boolean, default=False)
    scope = Column(String(50), nullable=False)  # system | tenant | office 

    permissions = relationship(
        "Permission",
        secondary=role_permissions,
        back_populates="roles",
        lazy="joined",
    )
    
    user_roles = relationship(
        "UserRole",
        cascade="all, delete-orphan",
    )

    # users = relationship(
    #     "User",
    #     secondary=user_roles,
    #     back_populates="roles",
    # )
