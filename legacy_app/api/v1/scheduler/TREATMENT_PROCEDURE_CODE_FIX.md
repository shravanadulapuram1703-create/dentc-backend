# Treatment Procedure Code Fix

## Issue

The UI is sending treatment objects without the `procedure_code` field, causing a 422 validation error.

## Root Cause

The `AppointmentTreatmentCreate` schema requires `procedure_code` as a mandatory field, but the UI payload doesn't include it:

```json
{
  "treatments": [{
    "status": "TP",
    "description": "Endodontic Therapy - Bicuspid",
    // Missing: "procedure_code" or "procedureCode"
    "bill_to": "Patient",
    "duration": 30,
    "provider": "Dr. Shravan",
    "provider_units": 1,
    "fee": 900
  }]
}
```

## Solution

### Backend Fix (Applied)

1. **Made `procedure_code` optional** in `AppointmentTreatmentCreate` schema
2. **Added default value** "UNKNOWN" if not provided
3. **Updated service layer** to handle missing procedure_code gracefully

### Changes Made

**Schema (`app/api/v1/scheduler/schemas.py`):**
- Changed `procedure_code` from required (`Field(...)`) to optional (`Field(None)`)
- Added `field_validator` to set default "UNKNOWN" if not provided
- Added `alias="procedureCode"` to support both snake_case and camelCase

**Service Layer (`app/api/v1/scheduler/services.py`):**
- Updated `create_appointment()` to use `procedure_code or "UNKNOWN"`
- Updated `update_appointment()` to use `procedure_code or "UNKNOWN"`

## UI Recommendations

### Option 1: Include procedure_code (Recommended)

The UI should include `procedure_code` in the treatment object:

```json
{
  "treatments": [{
    "procedureCode": "D3320",  // Add this field
    "status": "TP",
    "description": "Endodontic Therapy - Bicuspid",
    "bill_to": "Patient",
    "duration": 30,
    "provider": "Dr. Shravan",
    "provider_units": 1,
    "fee": 900
  }]
}
```

**Benefits:**
- Proper data integrity
- Links to procedure_codes table
- Better reporting and analytics

### Option 2: Keep current behavior (Works but not ideal)

The backend will now accept treatments without `procedure_code` and default to "UNKNOWN".

**Limitations:**
- "UNKNOWN" procedure codes won't link to procedure_codes table
- May cause foreign key constraint issues if procedure_codes table enforces constraints
- Less accurate data for reporting

## Foreign Key Constraint Handling

If the `procedure_codes` table has a foreign key constraint on `appointment_treatments.procedure_code`, you may need to:

1. **Insert "UNKNOWN" into procedure_codes table:**
   ```sql
   INSERT INTO tenant_1.procedure_codes (code, description, category, default_fee)
   VALUES ('UNKNOWN', 'Unknown Procedure', 'ALL', 0.00)
   ON CONFLICT (code) DO NOTHING;
   ```

2. **Or make the foreign key nullable** (not recommended for data integrity)

## Testing

After the fix, the following payload should work:

```json
{
  "patient_id": "CH011",
  "date": "2026-01-19",
  "start_time": "10:30",
  "duration": 30,
  "procedure_type": "Cleaning",
  "operatory": "OP3",
  "provider": "Dr. Shravan",
  "status": "Scheduled",
  "notes": "test",
  "lab": true,
  "lab_dds": "test",
  "lab_cost": 20,
  "lab_sent_on": "2026-01-19",
  "lab_due_on": "2026-01-19",
  "lab_recvd_on": "2026-01-19",
  "missed": true,
  "cancelled": true,
  "campaign_id": "123456",
  "treatments": [{
    "status": "TP",
    "description": "Endodontic Therapy - Bicuspid",
    "bill_to": "Patient",
    "duration": 30,
    "provider": "Dr. Shravan",
    "provider_units": 1,
    "fee": 900
  }]
}
```

## Summary

✅ **Backend Fix Applied:** `procedure_code` is now optional with default "UNKNOWN"
⚠️ **UI Recommendation:** Include `procedureCode` in treatment objects for better data integrity
📝 **Note:** May need to insert "UNKNOWN" into procedure_codes table if foreign key constraint exists

The 422 error should now be resolved!
