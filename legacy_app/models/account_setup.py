from sqlalchemy import Boolean, CheckConstraint, Column, ForeignKey, Integer, String, TIMESTAMP, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class AccountSetup(Base):
    __tablename__ = "account_setups"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_account_setups_tenant_id"),
        CheckConstraint("max_treatment_plan_discount >= 0 AND max_treatment_plan_discount <= 100", name="ck_account_setups_discount_range"),
        {"schema": "public"},
    )

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("public.tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(String(50), nullable=False, unique=True, index=True)
    account_number = Column(String(50), nullable=False)
    account_name = Column(String(150), nullable=False)
    email = Column(String(255), nullable=False)
    culture_code = Column(String(20), nullable=False, default="en-US")
    enable_full_screen = Column(Boolean, nullable=False, default=False)
    max_treatment_plan_discount = Column(Integer, nullable=False, default=0)
    pgid = Column(String(100), nullable=True)
    oid = Column(String(100), nullable=True)
    updated_by_user_id = Column(Integer, ForeignKey("public.users.id", ondelete="SET NULL"), nullable=True)
    updated_by_email = Column(String(255), nullable=True)
    lock_version = Column(Integer, nullable=False, default=1)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)
