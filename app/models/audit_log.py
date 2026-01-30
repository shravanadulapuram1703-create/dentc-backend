# app/models/audit_log.py

from sqlalchemy import (
    Column, BigInteger, Integer, String,
    Boolean, Text, DateTime
)
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(BigInteger, primary_key=True, index=True)

    tenant_id = Column(Integer, index=True)
    actor_user_id = Column(Integer, index=True)

    action = Column(String(100), nullable=False)

    resource = Column(String(100))
    resource_id = Column(String(50))

    resource_type = Column(String(100))
    resource_pk = Column(String(50))

    success = Column(Boolean, nullable=False, default=True)
    reason = Column(Text)

    ip_address = Column(String(50))
    user_agent = Column(Text)

    impersonated_user_id = Column(Integer)
    office_id = Column(Integer)


    meta = Column("metadata", JSONB)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
