from sqlalchemy import (
    Column, Integer, String, TIMESTAMP, Text
)
from app.core.database import Base

class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, nullable=False)
    provider_id = Column(Integer, nullable=False)
    operatory_id = Column(Integer, nullable=False)
    office_id = Column(Integer, nullable=False)

    start_time = Column(TIMESTAMP, nullable=False)
    end_time = Column(TIMESTAMP, nullable=False)

    status = Column(String(50), nullable=False)
    notes = Column(Text)
    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)