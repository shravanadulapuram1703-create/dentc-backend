from pydantic import BaseModel
from datetime import date
from typing import Optional

class PatientCreate(BaseModel):
    chart_no: Optional[str]
    first_name: str
    last_name: str
    dob: Optional[date]
    gender: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    home_office_id: Optional[int]

class PatientUpdate(BaseModel):
    first_name: Optional[str]
    last_name: Optional[str]
    phone: Optional[str]
    email: Optional[str]

class PatientOut(PatientCreate):
    id: int

    class Config:
        from_attributes = True
