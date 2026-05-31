from sqlalchemy import (
    Column, Integer, String, TIMESTAMP, Text
)
from app.core.database import Base

class TreatmentPlan(Base):
    __tablename__ = "treatment_plans"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, nullable=False)
    office_id = Column(Integer, nullable=False)
    created_by = Column(Integer, nullable=False)
    status = Column(String(30), nullable=False)
    total_fee = Column(Integer)
    created_at = Column(TIMESTAMP)
