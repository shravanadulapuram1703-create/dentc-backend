# New APIs Documentation - Scheduler, Patient, and Procedure Block APIs

This document provides complete API contracts for all new APIs required by the Add/Edit Appointment page.

## Table of Contents

1. [Scheduler APIs](#scheduler-apis)
2. [Procedure APIs](#procedure-apis)
3. [Treatment Plan APIs](#treatment-plan-apis)
4. [Database Schema](#database-schema)
5. [Setup Instructions](#setup-instructions)

---

## Scheduler APIs

### 1. Get Appointment Statuses

**Endpoint:** `GET /api/v1/scheduler/appointment-statuses`

**Description:** Fetch all available appointment status types for the status dropdown.

**Authentication:** Required (JWT token)

**Query Parameters:** None

**Response Schema:**
```json
{
  "statuses": [
    {
      "id": "STATUS001",
      "name": "Scheduled",
      "displayName": "Scheduled",
      "color": "#3A6EA5"
    }
  ]
}
```

**Example Response:**
```json
{
  "statuses": [
    {
      "id": "STATUS001",
      "name": "Scheduled",
      "displayName": "Scheduled",
      "color": "#3A6EA5"
    },
    {
      "id": "STATUS002",
      "name": "Confirmed",
      "displayName": "Confirmed",
      "color": "#2FB9A7"
    },
    {
      "id": "STATUS003",
      "name": "Unconfirmed",
      "displayName": "Unconfirmed",
      "color": "#F59E0B"
    }
  ]
}
```

**Status Codes:**
- `200 OK`: Success
- `401 Unauthorized`: Missing or invalid authentication token
- `500 Internal Server Error`: Server error

---

### 2. Get Appointment Types

**Endpoint:** `GET /api/v1/scheduler/appointment-types`

**Description:** Fetch appointment types (optional - may reuse procedure types).

**Authentication:** Required (JWT token)

**Query Parameters:** None

**Response Schema:**
```json
{
  "appointmentTypes": [
    {
      "id": "TYPE001",
      "name": "New Patient",
      "description": "First visit appointment"
    }
  ]
}
```

**Example Response:**
```json
{
  "appointmentTypes": [
    {
      "id": "TYPE001",
      "name": "New Patient",
      "description": "First visit appointment"
    },
    {
      "id": "TYPE002",
      "name": "Follow-up",
      "description": "Follow-up appointment"
    }
  ]
}
```

**Status Codes:**
- `200 OK`: Success
- `401 Unauthorized`: Missing or invalid authentication token
- `500 Internal Server Error`: Server error

---

## Procedure APIs

### 3. Get Procedure Codes

**Endpoint:** `GET /api/v1/procedures/codes`

**Description:** Fetch all procedure codes for the Quick Add procedure browser. Supports filtering by category and search.

**Authentication:** Required (JWT token)

**Query Parameters:**
- `category` (optional, string): Filter by procedure category (e.g., "DIAGNOSTIC")
- `search` (optional, string): Search in code, userCode, or description

**Response Schema:**
```json
{
  "procedureCodes": [
    {
      "code": "D0120",
      "userCode": "-",
      "description": "Periodic Oral Evaluation",
      "category": "DIAGNOSTIC",
      "requirements": {
        "tooth": false,
        "surface": false,
        "quadrant": false,
        "materials": false
      },
      "defaultFee": 75.00,
      "defaultDuration": 15
    }
  ]
}
```

**Example Request:**
```
GET /api/v1/procedures/codes?category=DIAGNOSTIC&search=D0120
```

**Example Response:**
```json
{
  "procedureCodes": [
    {
      "code": "D0120",
      "userCode": "-",
      "description": "Periodic Oral Evaluation",
      "category": "DIAGNOSTIC",
      "requirements": {
        "tooth": false,
        "surface": false,
        "quadrant": false,
        "materials": false
      },
      "defaultFee": 75.00,
      "defaultDuration": 15
    },
    {
      "code": "D0140",
      "userCode": "-",
      "description": "Limited Oral Eval Prob Focused",
      "category": "DIAGNOSTIC",
      "requirements": {
        "tooth": false,
        "surface": false,
        "quadrant": false,
        "materials": false
      },
      "defaultFee": 85.00,
      "defaultDuration": 20
    }
  ]
}
```

**Status Codes:**
- `200 OK`: Success
- `401 Unauthorized`: Missing or invalid authentication token
- `500 Internal Server Error`: Server error

---

### 4. Get Procedure Categories

**Endpoint:** `GET /api/v1/procedures/categories`

**Description:** Fetch all procedure categories for filtering procedure codes.

**Authentication:** Required (JWT token)

**Query Parameters:** None

**Response Schema:**
```json
{
  "categories": [
    {
      "id": "DIAGNOSTIC",
      "name": "DIAGNOSTIC",
      "displayName": "Diagnostic"
    }
  ]
}
```

**Example Response:**
```json
{
  "categories": [
    {
      "id": "ALL",
      "name": "ALL",
      "displayName": "All"
    },
    {
      "id": "DIAGNOSTIC",
      "name": "DIAGNOSTIC",
      "displayName": "Diagnostic"
    },
    {
      "id": "PREVENTIVE",
      "name": "PREVENTIVE",
      "displayName": "Preventive"
    },
    {
      "id": "RESTORATIVE",
      "name": "RESTORATIVE",
      "displayName": "Restorative"
    }
  ]
}
```

**Status Codes:**
- `200 OK`: Success
- `401 Unauthorized`: Missing or invalid authentication token
- `500 Internal Server Error`: Server error

---

## Treatment Plan APIs

### 5. Get Patient Treatment Plans

**Endpoint:** `GET /api/v1/patients/{patient_id}/treatment-plans`

**Description:** Fetch all treatment plans for a specific patient. Treatment plans contain phases, and phases contain procedures.

**Authentication:** Required (JWT token)

**Path Parameters:**
- `patient_id` (required, string): Patient ID (chart number)

**Query Parameters:**
- `status` (optional, string): Filter by status ("Active", "Completed", "Cancelled")
- `include_completed` (optional, boolean): Include completed plans (default: false)

**Response Schema:**
```json
{
  "treatmentPlans": [
    {
      "id": "TXP-001",
      "name": "Plan 1",
      "patientId": "900097",
      "phases": [
        {
          "id": "PHASE-001",
          "name": "Phase 1",
          "procedures": [
            {
              "id": "PROC-001",
              "code": "Z6000",
              "description": "Impressions Diagnosed (6963/JN, Ahmed, Mary)",
              "tooth": "",
              "surface": "",
              "diagnosedProvider": "Dr. Ahmed",
              "fee": 250.00,
              "insuranceEstimate": 0.00,
              "status": "Planned"
            }
          ]
        }
      ],
      "createdDate": "2024-01-15T10:30:00Z",
      "status": "Active"
    }
  ]
}
```

**Example Request:**
```
GET /api/v1/patients/900097/treatment-plans?status=Active
```

**Example Response:**
```json
{
  "treatmentPlans": [
    {
      "id": "TXP-001",
      "name": "Plan 1",
      "patientId": "900097",
      "phases": [
        {
          "id": "PHASE-001",
          "name": "Phase 1",
          "procedures": [
            {
              "id": "PROC-001",
              "code": "Z6000",
              "description": "Impressions Diagnosed (6963/JN, Ahmed, Mary)",
              "tooth": "",
              "surface": "",
              "diagnosedProvider": "Dr. Ahmed",
              "fee": 250.00,
              "insuranceEstimate": 0.00,
              "status": "Planned"
            },
            {
              "id": "PROC-002",
              "code": "Z6000",
              "description": "Impressions Diagnosed (6963/JN, Ahmed, Meier)",
              "tooth": "",
              "surface": "",
              "diagnosedProvider": "Dr. Ahmed",
              "fee": 250.00,
              "insuranceEstimate": 0.00,
              "status": "Planned"
            }
          ]
        }
      ],
      "createdDate": "2024-01-15T10:30:00Z",
      "status": "Active"
    }
  ]
}
```

**Status Codes:**
- `200 OK`: Success
- `401 Unauthorized`: Missing or invalid authentication token
- `404 Not Found`: Patient not found
- `500 Internal Server Error`: Server error

---

## Database Schema

### Tables Created

1. **appointment_statuses** - Stores appointment status types with colors
2. **appointment_types** - Stores appointment types (optional)
3. **procedure_categories** - Stores procedure categories
4. **procedure_codes** - Stores procedure codes with requirements and defaults
5. **treatment_plans** - Stores treatment plans for patients
6. **treatment_plan_phases** - Stores phases within treatment plans
7. **treatment_plan_procedures** - Stores procedures within phases
8. **appointment_treatments** - Links procedures to appointments

### Tables Updated

1. **scheduler_appointments** - Added fields:
   - `lab` (BOOLEAN)
   - `lab_dds` (VARCHAR)
   - `lab_cost` (DECIMAL)
   - `lab_sent_on` (DATE)
   - `lab_due_on` (DATE)
   - `lab_recvd_on` (DATE)
   - `missed` (BOOLEAN)
   - `cancelled` (BOOLEAN)
   - `campaign_id` (VARCHAR)
   - `treatment_plan_id` (VARCHAR)
   - `treatment_plan_phase_id` (VARCHAR)

All tables are created in the `tenant_1` schema for multi-tenant support.

---

## Setup Instructions

### 1. Run the SQL Setup Script

Execute the SQL script to create all tables, constraints, indexes, and seed data:

```bash
psql -U your_user -d your_database -f app/api/v1/scheduler/sql/setup_new_apis.sql
```

Or using Python:

```python
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="your_database",
    user="your_user",
    password="your_password"
)
cur = conn.cursor()

with open('app/api/v1/scheduler/sql/setup_new_apis.sql', 'r') as f:
    cur.execute(f.read())

conn.commit()
cur.close()
conn.close()
```

### 2. Verify Tables Created

Check that all tables exist:

```sql
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'tenant_1' 
AND table_name IN (
    'appointment_statuses',
    'appointment_types',
    'procedure_categories',
    'procedure_codes',
    'treatment_plans',
    'treatment_plan_phases',
    'treatment_plan_procedures',
    'appointment_treatments'
);
```

### 3. Verify Seed Data

Check that seed data was inserted:

```sql
-- Check appointment statuses
SELECT COUNT(*) FROM tenant_1.appointment_statuses; -- Should be 10

-- Check procedure categories
SELECT COUNT(*) FROM tenant_1.procedure_categories; -- Should be 11

-- Check procedure codes
SELECT COUNT(*) FROM tenant_1.procedure_codes; -- Should be 30+
```

### 4. Test the APIs

Use the FastAPI docs to test the endpoints:

```
http://localhost:8000/docs
```

Or use curl:

```bash
# Get appointment statuses
curl -X GET "http://localhost:8000/api/v1/scheduler/appointment-statuses" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Get procedure codes
curl -X GET "http://localhost:8000/api/v1/procedures/codes?category=DIAGNOSTIC" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Get treatment plans
curl -X GET "http://localhost:8000/api/v1/patients/900097/treatment-plans" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

## Summary

### New APIs Implemented

1. ✅ `GET /api/v1/scheduler/appointment-statuses` - Get appointment status types
2. ✅ `GET /api/v1/scheduler/appointment-types` - Get appointment types
3. ✅ `GET /api/v1/procedures/codes` - Get procedure codes with filtering
4. ✅ `GET /api/v1/procedures/categories` - Get procedure categories
5. ✅ `GET /api/v1/patients/{patient_id}/treatment-plans` - Get patient treatment plans

### Database Tables Created

- ✅ `appointment_statuses`
- ✅ `appointment_types`
- ✅ `procedure_categories`
- ✅ `procedure_codes`
- ✅ `treatment_plans`
- ✅ `treatment_plan_phases`
- ✅ `treatment_plan_procedures`
- ✅ `appointment_treatments`

### Database Tables Updated

- ✅ `scheduler_appointments` (added lab fields, flags, campaign, treatment plan linkage)

### Seed Data Included

- ✅ 10 appointment statuses with colors
- ✅ 4 appointment types
- ✅ 11 procedure categories
- ✅ 30+ procedure codes across multiple categories

All APIs are fully functional and ready for use by the frontend!
