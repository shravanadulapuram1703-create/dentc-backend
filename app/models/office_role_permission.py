from sqlalchemy import Column, Integer, ForeignKey
from app.core.database import Base


class OfficeRolePermission(Base):
    __tablename__ = "office_role_permissions"
    __table_args__ = {"schema": "public"}

    role_id = Column(
        Integer,
        ForeignKey("public.office_roles.id", ondelete="CASCADE"),
        primary_key=True
    )

    permission_id = Column(
        Integer,
        ForeignKey("public.office_permissions.id", ondelete="CASCADE"),
        primary_key=True
    )

    office_id = Column(
        Integer,
        ForeignKey("public.offices.id", ondelete="CASCADE"),
        primary_key=True
    )
