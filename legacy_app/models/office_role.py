from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    ForeignKey
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class OfficeRole(Base):
    __tablename__ = "office_roles"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)

    tenant_id = Column(
        Integer,
        ForeignKey("public.tenants.id", ondelete="CASCADE"),
        nullable=False
    )

    office_id = Column(
        Integer,
        ForeignKey("public.offices.id", ondelete="CASCADE"),
        nullable=False
    )

    name = Column(String(100), nullable=False)
    level = Column(Integer, nullable=False)
    is_system = Column(Boolean, default=False)

    office = relationship("Office", back_populates="roles")

    
    permissions = relationship(
        "OfficeRolePermission",
        cascade="all, delete"
    )
