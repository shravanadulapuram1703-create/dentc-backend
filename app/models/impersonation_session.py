from sqlalchemy import Column, Integer, ForeignKey, DateTime, String
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.core.database import Base



class ImpersonationSession(Base):
    __tablename__ = "impersonation_sessions"
    __table_args__ = {"schema": "public"}  # 🔥 REQUIRED

    id = Column(Integer, primary_key=True)

    admin_user_id = Column(
        Integer,
        ForeignKey("public.users.id"),
        nullable=False
    )

    impersonated_user_id = Column(
        Integer,
        ForeignKey("public.users.id"),
        nullable=False
    )

    started_at = Column(DateTime, server_default=func.now())
    ended_at = Column(DateTime, nullable=True)

    ip_address = Column(String(50))
    user_agent = Column(String)

    admin_user = relationship(
        "User",
        foreign_keys=[admin_user_id]
    )

    impersonated_user = relationship(
        "User",
        foreign_keys=[impersonated_user_id]
    )