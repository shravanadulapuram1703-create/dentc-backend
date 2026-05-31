from sqlalchemy import (
    Column, Integer, String, Boolean,TIMESTAMP, Text
)
from app.core.database import Base


class TreatmentPlanProcedure(Base):
    __tablename__ = "treatment_plan_procedures"

    id = Column(Integer, primary_key=True)
    treatment_plan_id = Column(Integer, nullable=False)
    procedure_code = Column(String(10), nullable=False)
    provider_id = Column(Integer)
    fee = Column(Integer)
    status = Column(String(30))
    scheduled = Column(Boolean, default=True)
