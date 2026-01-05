from sqlalchemy import Column, Integer, String, Date, TIMESTAMP
from app.core.database import Base

class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True)
    chart_no = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    dob = Column(Date)
    gender = Column(String(1))
    phone = Column(String)
    email = Column(String)
    home_office_id = Column(Integer)
    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)
