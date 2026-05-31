from sqlalchemy import (
    Column,
    Integer,
    String,
    Numeric,
    Date,
    TIMESTAMP,
)
from app.core.database import Base


class Ledger(Base):
    __tablename__ = "ledger"

    id = Column(Integer, primary_key=True, index=True)

    patient_id = Column(Integer, nullable=False)
    office_id = Column(Integer, nullable=False)
    appointment_id = Column(Integer, nullable=True)

    txn_date = Column(Date, nullable=False)

    description = Column(String, nullable=False)

    charge = Column(Numeric(10, 2), default=0)
    payment = Column(Numeric(10, 2), default=0)

    balance = Column(Numeric(10, 2), nullable=False)

    txn_type = Column(String(30), nullable=False)

    created_at = Column(TIMESTAMP)
