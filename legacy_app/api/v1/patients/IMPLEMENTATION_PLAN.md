# Patient Module Implementation Plan

## Status: In Progress

This document tracks the implementation of the comprehensive Patient Management API module.

## Completed

1. ✅ SQL Migration Script (`app/api/v1/patients/sql/migrate_patient_module.sql`)
   - Alters existing patients table with all new fields
   - Creates all related tables (addresses, contact_info, insurance, etc.)
   - Creates reference tables (patient_types, referral_types, etc.)
   - Inserts seed data
   - Creates indexes and foreign keys

2. ✅ Patient Related Models (`app/models/patient_models.py`)
   - PatientAddress
   - PatientContactInfo
   - ResponsibleParty
   - PatientInsurance
   - FeeSchedule
   - PatientType
   - ReferralType
   - ResponsiblePartyRelationship
   - ContactPreference
   - PatientAccountMember
   - PatientBalance
   - PatientClinicalInfo
   - PatientMedicalAlert

## In Progress

3. ⏳ Update Patient Model (`app/models/patient.py`)
   - Add all new fields
   - Add relationships to new models

4. ⏳ Comprehensive Schemas (`app/api/v1/patients/schemas.py`)
   - Patient search request/response
   - Patient details request/response
   - Patient create/update request/response
   - Metadata schemas
   - Duplicate check schemas

5. ⏳ Service Layer (`app/api/v1/patients/service.py`)
   - Patient search with field-specific logic
   - Patient details retrieval
   - Patient create/update
   - Metadata retrieval
   - Duplicate checking

6. ⏳ Routes (`app/api/v1/patients/router.py`)
   - GET /api/v1/patients/search
   - GET /api/v1/patients/{patientId}
   - POST /api/v1/patients
   - PUT /api/v1/patients/{patientId}
   - GET /api/v1/patients/metadata/* endpoints
   - POST /api/v1/patients/check-duplicate

## Next Steps

1. Update Patient model with all fields and relationships
2. Create comprehensive Pydantic schemas
3. Implement service layer with business logic
4. Update routes with all endpoints
5. Test all endpoints
6. Update models __init__.py to import new models
