from sqlalchemy import Column, BigInteger, Integer, String, Boolean, Text, DateTime
from datetime import datetime
from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(BigInteger, primary_key=True)
    tenant_id = Column(Integer)
    user_id = Column(Integer)

    action = Column(String(100), nullable=False)
    resource = Column(String(100))
    resource_id = Column(String(50))

    success = Column(Boolean, nullable=False)
    reason = Column(Text)

    ip_address = Column(String(50))
    user_agent = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
