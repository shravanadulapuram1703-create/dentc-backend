from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class AppointmentBase(BaseModel):
    patient_id: int
    provider_id: int
    operatory_id: int
    office_id: int
    start_time: datetime
    end_time: datetime
    status: str
    notes: Optional[str] = None

class AppointmentCreate(AppointmentBase):
    pass

class AppointmentUpdate(BaseModel):
    provider_id: Optional[int]
    operatory_id: Optional[int]
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    status: Optional[str]
    notes: Optional[str]

class AppointmentOut(AppointmentBase):
    id: int

    class Config:
        from_attributes = True
