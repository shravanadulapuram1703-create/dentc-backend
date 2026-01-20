from __future__ import annotations

from pydantic import BaseModel, Field, EmailStr
from datetime import date
from typing import Optional

class PatientCreate(BaseModel):
    """Schema for creating a new patient"""
    chart_no: Optional[str] = Field(None, max_length=50, description="Patient chart number (auto-generated if not provided)")
    first_name: str = Field(..., min_length=1, max_length=100, description="Patient first name")
    last_name: str = Field(..., min_length=1, max_length=100, description="Patient last name")
    dob: Optional[date] = Field(None, description="Date of birth (YYYY-MM-DD)")
    gender: Optional[str] = Field(None, max_length=20, description="Gender (M/F/O)")
    phone: Optional[str] = Field(None, max_length=20, description="Phone number")
    email: Optional[EmailStr] = Field(None, description="Email address")
    home_office_id: Optional[int] = Field(None, description="Home office ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "first_name": "John",
                "last_name": "Doe",
                "dob": "1990-01-15",
                "gender": "M",
                "phone": "555-1234",
                "email": "john.doe@example.com",
                "home_office_id": 1
            }
        }


class PatientCreateWithAliases(BaseModel):
    """Schema for creating a patient with camelCase aliases (for frontend compatibility)"""
    chartNo: Optional[str] = Field(None, alias="chart_no", max_length=50)
    firstName: str = Field(..., alias="first_name", min_length=1, max_length=100)
    lastName: str = Field(..., alias="last_name", min_length=1, max_length=100)
    dob: Optional[date] = None
    gender: Optional[str] = Field(None, max_length=20)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None
    homeOfficeId: Optional[int] = Field(None, alias="home_office_id")
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "firstName": "John",
                "lastName": "Doe",
                "dob": "1990-01-15",
                "gender": "M",
                "phone": "555-1234",
                "email": "john.doe@example.com",
                "homeOfficeId": 1
            }
        }


class PatientUpdate(BaseModel):
    """Schema for updating a patient"""
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    dob: Optional[date] = None
    gender: Optional[str] = Field(None, max_length=1)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None
    home_office_id: Optional[int] = None


class PatientResponse(BaseModel):
    """Schema for patient response"""
    id: int = Field(..., description="Patient ID")
    chart_no: Optional[str] = Field(None, alias="chartNo", description="Patient chart number")
    first_name: str = Field(..., alias="firstName", description="Patient first name")
    last_name: str = Field(..., alias="lastName", description="Patient last name")
    dob: Optional[date] = Field(None, description="Date of birth")
    gender: Optional[str] = Field(None, description="Gender")
    phone: Optional[str] = Field(None, description="Phone number")
    email: Optional[str] = Field(None, description="Email address")
    home_office_id: Optional[int] = Field(None, alias="homeOfficeId", description="Home office ID")
    created_at: Optional[str] = Field(None, alias="createdAt", description="Creation timestamp")
    updated_at: Optional[str] = Field(None, alias="updatedAt", description="Last update timestamp")
    
    class Config:
        populate_by_name = True
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "chartNo": "CH001",
                "firstName": "John",
                "lastName": "Doe",
                "dob": "1990-01-15",
                "gender": "M",
                "phone": "555-1234",
                "email": "john.doe@example.com",
                "homeOfficeId": 1,
                "createdAt": "2024-01-01T10:00:00",
                "updatedAt": "2024-01-01T10:00:00"
            }
        }


class PatientListResponse(BaseModel):
    """Schema for patient list response"""
    patients: list[PatientResponse]
    total: int = Field(..., description="Total number of patients")


# Legacy alias for backward compatibility
PatientOut = PatientResponse