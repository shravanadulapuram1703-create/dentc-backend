from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, TIMESTAMP
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)

    tenant_id = Column(
        Integer,
        ForeignKey("public.tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id = Column(
        Integer,
        ForeignKey("public.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    token_hash = Column(String(255), nullable=False, index=True)

    expires_at = Column(TIMESTAMP, nullable=False)

    revoked = Column(Boolean, default=False, nullable=False)

    created_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="refresh_tokens")
