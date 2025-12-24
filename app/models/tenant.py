from sqlalchemy import Column, Integer, String, TIMESTAMP
from app.core.database import Base
from sqlalchemy.sql import func


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    tenant_key = Column(String(80), unique=True, nullable=False)
    pgid = Column(Integer, nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    status = Column(String(20), default="active")
    created_at = Column(TIMESTAMP, server_default=func.now())
