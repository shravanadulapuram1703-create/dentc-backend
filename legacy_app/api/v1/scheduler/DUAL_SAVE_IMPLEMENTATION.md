# Dual Save Flow Implementation - Quick Save + Full Save

This document describes the implementation of the dual save flow for appointments, supporting both Quick Save (minimal details) and Full Save (complete details).

## Overview

The appointment save API now supports two flows:

1. **Quick Save** - Minimal required fields only (backward compatible)
2. **Full Save** - Complete appointment details including lab info, treatments, flags, etc.

Both flows use the same endpoints but with different payload structures.

## API Endpoints

### Create Appointment
**POST** `/api/v1/scheduler/appointments`

### Update Appointment
**PUT** `/api/v1/scheduler/appointments/{appointment_id}`

## Quick Save Flow

### Use Case
- Clicking "Quick Save" button
- Creating appointment with minimal information
- Works for both new and existing patients

### Required Fields
- `patient_id` (string)
- `date` (string, YYYY-MM-DD)
- `start_time` (string, HH:MM)
- `duration` (integer, minutes)
- `procedure_type` (string)
- `operatory` (string)
- `provider` (string)

### Optional Fields (with defaults)
- `status` (defaults to "Scheduled")
- `notes` (defaults to empty string)

### Example Request
```json
{
  "patientId": "CH001",
  "date": "2024-12-20",
  "startTime": "09:00",
  "duration": 60,
  "procedureType": "PROC001",
  "operatory": "OP1",
  "provider": "Dr. Jinna"
}
```

## Full Save Flow

### Use Case
- After clicking "Continue" button
- Completing the Add/Edit Appointment page
- Saving all appointment details

### All Fields Available

#### Core Fields (Required)
- `patient_id`, `date`, `start_time`, `duration`, `procedure_type`, `operatory`, `provider`

#### Lab Information (Optional)
- `lab` (boolean)
- `labDds` (string)
- `labCost` (number)
- `labSentOn` (string, YYYY-MM-DD)
- `labDueOn` (string, YYYY-MM-DD)
- `labRecvdOn` (string, YYYY-MM-DD)

#### Flags (Optional)
- `missed` (boolean)
- `cancelled` (boolean)

#### Additional Fields (Optional)
- `campaignId` (string)
- `treatmentPlanId` (string)
- `treatmentPlanPhaseId` (string)

#### Treatments Array (Optional)
- `treatments` (array of treatment objects)

### Example Request
```json
{
  "patientId": "CH002",
  "date": "2024-12-21",
  "startTime": "10:00",
  "duration": 90,
  "procedureType": "PROC002",
  "operatory": "OP2",
  "provider": "Dr. Smith",
  "status": "Scheduled",
  "notes": "Routine cleaning and exam",
  "lab": true,
  "labDds": "ABC Dental Lab",
  "labCost": 250.00,
  "labSentOn": "2024-12-21",
  "labDueOn": "2024-12-28",
  "missed": false,
  "cancelled": false,
  "campaignId": "CAMPAIGN_2024_Q4",
  "treatmentPlanId": "TP001",
  "treatmentPlanPhaseId": "TPP001",
  "treatments": [
    {
      "procedureCode": "D0120",
      "status": "TP",
      "description": "Periodic Oral Evaluation",
      "billTo": "Patient",
      "duration": 15,
      "provider": "Dr. Smith",
      "providerUnits": 1,
      "estPatient": 75.00,
      "fee": 75.00
    },
    {
      "procedureCode": "D1110",
      "status": "TP",
      "description": "Adult Prophylaxis",
      "billTo": "Insurance",
      "duration": 30,
      "provider": "Dr. Smith",
      "providerUnits": 1,
      "estPatient": 20.00,
      "estInsurance": 80.00,
      "fee": 100.00
    }
  ]
}
```

## Implementation Details

### Schema Updates

1. **AppointmentBase** - Extended with all optional fields
   - Lab fields (lab, labDds, labCost, labSentOn, labDueOn, labRecvdOn)
   - Flag fields (missed, cancelled)
   - Additional fields (campaignId, treatmentPlanId, treatmentPlanPhaseId)
   - Treatments array

2. **AppointmentTreatmentCreate** - New schema for treatment creation
   - All treatment fields with camelCase aliases

3. **AppointmentResponse** - Extended to include all fields
   - All new fields included in response
   - Treatments array included

### Service Layer Updates

1. **create_appointment** - Handles both Quick Save and Full Save
   - All optional fields are handled gracefully
   - Treatments are created if provided
   - Uses transaction to ensure data consistency

2. **update_appointment** - Supports partial updates
   - Only provided fields are updated
   - Treatments are replaced if provided (delete old, create new)

3. **build_appointment_response** - Helper function
   - Centralized response building
   - Includes all fields and treatments
   - Used by all appointment retrieval functions

### Database Schema

All fields are already in the `scheduler_appointments` table (from previous migration):
- Lab fields: `lab`, `lab_dds`, `lab_cost`, `lab_sent_on`, `lab_due_on`, `lab_recvd_on`
- Flag fields: `missed`, `cancelled`
- Additional fields: `campaign_id`, `treatment_plan_id`, `treatment_plan_phase_id`

Treatments are stored in `appointment_treatments` table with foreign key to `scheduler_appointments`.

## Backward Compatibility

The implementation is fully backward compatible:
- Quick Save requests (minimal fields) work exactly as before
- Existing API consumers continue to work without changes
- All optional fields default to sensible values (False for booleans, None for others)

## Error Handling

### Validation Errors
- Missing required fields → 400 Bad Request
- Invalid date/time format → 400 Bad Request
- Invalid patient_id, operatory, provider → 400 Bad Request
- Operatory overlap → 409 Conflict

### Treatment Validation
- Invalid procedure_code → 400 Bad Request
- Missing required treatment fields → 400 Bad Request
- Invalid treatment status → 400 Bad Request

## Testing

### Test Quick Save
```bash
POST /api/v1/scheduler/appointments
{
  "patientId": "CH001",
  "date": "2024-12-20",
  "startTime": "09:00",
  "duration": 60,
  "procedureType": "PROC001",
  "operatory": "OP1",
  "provider": "Dr. Jinna"
}
```

### Test Full Save
```bash
POST /api/v1/scheduler/appointments
{
  "patientId": "CH002",
  "date": "2024-12-21",
  "startTime": "10:00",
  "duration": 90,
  "procedureType": "PROC002",
  "operatory": "OP2",
  "provider": "Dr. Smith",
  "lab": true,
  "labDds": "ABC Dental Lab",
  "treatments": [...]
}
```

## Summary

✅ **Quick Save** - Minimal fields, backward compatible
✅ **Full Save** - All fields including lab, treatments, flags
✅ **Backward Compatible** - Existing code continues to work
✅ **Consistent API** - Same endpoints, different payloads
✅ **Data Integrity** - Transactions ensure consistency
✅ **Complete Responses** - All fields returned in response

The dual save flow is now fully implemented and ready for use!
