from sqlalchemy import Column, Integer, String, ForeignKey
from app.core.database import Base


class Office(Base):
    __tablename__ = "offices"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    tenant_id = Column(
        Integer,
        ForeignKey("public.tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    office_name = Column(String(255))
    timezone = Column(String(50))
