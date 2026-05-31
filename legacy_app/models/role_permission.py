from sqlalchemy import Column, Integer, String, Boolean, UniqueConstraint
from app.core.database import Base


class RolePermission(Base):
    __tablename__ = "role_permissions"

    id = Column(Integer, primary_key=True, index=True)

    code = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(String(255), nullable=False)

    module = Column(String(50), nullable=False)  # Patient, Billing, Admin, etc.

    is_system = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("code", name="uq_role_permissions_code"),
    )

    def __repr__(self) -> str:
        return f"<RolePermission(code={self.code}, module={self.module})>"
