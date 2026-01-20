from sqlalchemy import Column, Integer, String, Date, TIMESTAMP
from sqlalchemy.sql import func
from app.core.database import Base

class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = {"schema": "tenant_1"}

    id = Column(Integer, primary_key=True, index=True)
    chart_no = Column(String(50), unique=True, nullable=True, index=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    dob = Column(Date, nullable=True)
    gender = Column(String(1), nullable=True)  # M, F, or other
    phone = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    home_office_id = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=True)
    updated_at = Column(TIMESTAMP, nullable=True, onupdate=func.now())
