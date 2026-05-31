from sqlalchemy import (
    Column,
    Integer,
    Boolean,
    TIMESTAMP,
    ForeignKey,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class UserIPRule(Base):
    __tablename__ = "user_ip_rules"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, nullable=False, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ip_id = Column(
        Integer,
        ForeignKey("ip_addresses.id"),
        nullable=False,
        index=True,
    )

    is_active = Column(Boolean, default=True)

    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships (optional but recommended)
    ip = relationship("IPAddress", lazy="joined")
    user = relationship("User")
    user_id = Column(
    Integer,
    ForeignKey("public.users.id", ondelete="CASCADE"),
    nullable=False,
)


    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "ip_id",
            name="uq_user_ip_rule",
        ),
    )
