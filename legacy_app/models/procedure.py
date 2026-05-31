from sqlalchemy import (
    Column,
    Integer,
    String,
    Numeric,
    TIMESTAMP,
)
from app.core.database import Base


class Procedure(Base):
    __tablename__ = "procedures"

    id = Column(Integer, primary_key=True, index=True)

    patient_id = Column(Integer, nullable=False)
    appointment_id = Column(Integer, nullable=True)

    procedure_code = Column(String(10), nullable=False)

    tooth = Column(String(5))
    surfaces = Column(String(10))

    provider_id = Column(Integer)
    office_id = Column(Integer, nullable=False)

    performed_at = Column(TIMESTAMP, nullable=False)

    fee = Column(Numeric(10, 2), nullable=False)

    status = Column(String(30), nullable=False)

    created_at = Column(TIMESTAMP)
