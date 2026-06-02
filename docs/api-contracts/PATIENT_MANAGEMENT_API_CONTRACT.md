# Patient Management API Contracts

## Overview

This document defines the API contracts for patient management features, including patient search, patient details, patient creation, and related metadata endpoints. All endpoints follow RESTful conventions and use JSON for request/response bodies.

---

## Table of Contents

1. [Patient Search API](#patient-search-api) - Phase 1
2. [Patient Details API](#patient-details-api) - Phase 2
3. [Patient Create API](#patient-create-api) - Phase 2
4. [Patient Update API](#patient-update-api) - Phase 2
5. [Patient Metadata APIs](#patient-metadata-apis) - Phase 2
6. [Common Response Formats](#common-response-formats)

---

## Patient Search API

### Endpoint: `GET /api/v1/patients/search`

**Purpose:** Advanced patient search with field-specific search criteria and filters.

**Request Parameters (Query String):**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `search_by` | string | Yes | Field to search in (see Search By Options below) |
| `search_value` | string | Yes | The search term/value |
| `search_for` | string | No | `"patient"` or `"responsible"` (default: `"patient"`) |
| `patient_type` | string | No | `"general"`, `"ortho"`, or omit for both |
| `search_scope` | string | No | `"current"`, `"all"`, or `"group"` (default: `"all"`) |
| `include_inactive` | boolean | No | Include inactive patients (default: `false`) |
| `office_id` | string | No | Numeric office ID (required if `search_scope` is `"current"`) |
| `limit` | integer | No | Maximum results (1-1000, default: 100) |
| `offset` | integer | No | Pagination offset (default: 0) |

**Search By Options:**

The `search_by` parameter accepts one of the following values:

- `lastName` - Search by last name
- `firstName` - Search by first name
- `preferredName` - Search by preferred name
- `patientType` - Search by patient type
- `medicaidId` - Search by Medicaid ID
- `chartNumber` - Search by chart number
- `ssn` - Search by SSN (partial or full)
- `email` - Search by email address
- `birthDate` - Search by birth date (format: YYYY-MM-DD or MM/DD/YYYY)
- `homePhone` - Search by home phone number
- `cellPhone` - Search by cell phone number
- `workPhone` - Search by work phone number
- `patientId` - Search by patient ID
- `responsiblePartyId` - Search by responsible party ID
- `responsiblePartyType` - Search by responsible party type
- `subscriberId` - Search by subscriber ID

**Response Schema:**

```json
{
  "patients": [
    {
      "id": 123,
      "chart_no": "CH-001",
      "first_name": "John",
      "last_name": "Smith",
      "dob": "1980-05-15",
      "gender": "M",
      "phone": "555-123-4567",
      "email": "john.smith@email.com",
      "home_office_id": 108,
      "home_office_name": "Cranberry Main",
      "patient_type": "General",
      "is_active": true,
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-03-20T14:45:00Z"
    }
  ],
  "total": 1,
  "limit": 100,
  "offset": 0
}
```

**Field Descriptions:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Unique patient database ID |
| `chart_no` | string | Patient chart number (unique identifier) |
| `first_name` | string | Patient first name |
| `last_name` | string | Patient last name |
| `dob` | string | Date of birth (YYYY-MM-DD format) |
| `gender` | string | Gender: `"M"`, `"F"`, or `"O"` |
| `phone` | string | Primary phone number |
| `email` | string | Email address (optional) |
| `home_office_id` | integer | Home office ID |
| `home_office_name` | string | Home office name |
| `patient_type` | string | `"General"` or `"Ortho"` |
| `is_active` | boolean | Whether patient is active |
| `created_at` | string | ISO 8601 timestamp |
| `updated_at` | string | ISO 8601 timestamp or null |

**Example Request:**

```
GET /api/v1/patients/search?search_by=lastName&search_value=Smith&search_scope=all&patient_type=general&limit=50&offset=0
```

**Example Response:**

```json
{
  "patients": [
    {
      "id": 123,
      "chart_no": "CH-001",
      "first_name": "John",
      "last_name": "Smith",
      "dob": "1980-05-15",
      "gender": "M",
      "phone": "555-123-4567",
      "email": "john.smith@email.com",
      "home_office_id": 108,
      "home_office_name": "Cranberry Main",
      "patient_type": "General",
      "is_active": true,
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-03-20T14:45:00Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

**Error Responses:**

- `400 Bad Request` - Invalid search parameters
- `401 Unauthorized` - Missing or invalid authentication token
- `403 Forbidden` - User doesn't have permission to search patients
- `422 Unprocessable Entity` - Validation error (e.g., invalid `search_by` value)

**Business Rules:**

1. **Search By Field:** The search MUST only search in the specified `search_by` field. Do not search across multiple fields.
2. **Search Scope:**
   - `"current"` - Only search patients in the specified `office_id`
   - `"all"` - Search across all offices the user has access to
   - `"group"` - Search within the office group (if applicable)
3. **Patient Type Filter:**
   - If `patient_type` is `"general"`, return only general patients
   - If `patient_type` is `"ortho"`, return only orthodontic patients
   - If omitted, return both types
4. **Inactive Patients:** Only include inactive patients if `include_inactive` is `true`
5. **Responsible Party Search:** If `search_for` is `"responsible"`, search should match responsible party fields instead of patient fields

---

## Patient Details API

### Endpoint: `GET /api/v1/patients/{patientId}`

**Purpose:** Get complete patient details including demographics, contact info, insurance, responsible party, appointments, recalls, and balances.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `patientId` | string | Yes | Patient chart number or ID |

**Response Schema:**

```json
{
  "id": 123,
  "chart_no": "CH-001",
  "first_name": "John",
  "last_name": "Smith",
  "preferred_name": "Johnny",
  "dob": "1980-05-15",
  "gender": "M",
  "title": "Mr.",
  "pronouns": "He/Him",
  "marital_status": "Married",
  
  "address": {
    "address_line_1": "123 Main St",
    "address_line_2": "Apt 4B",
    "city": "Pittsburgh",
    "state": "PA",
    "zip": "15201",
    "country": "USA"
  },
  
  "contact": {
    "home_phone": "555-123-4567",
    "cell_phone": "555-123-4568",
    "work_phone": "555-123-4569",
    "email": "john.smith@email.com",
    "preferred_contact": "Cell Phone"
  },
  
  "office": {
    "home_office_id": 108,
    "home_office_name": "Cranberry Main",
    "home_office_code": "OFF-108"
  },
  
  "provider": {
    "preferred_provider_id": "PROV-001",
    "preferred_provider_name": "Dr. Smith",
    "preferred_hygienist_id": "HYG-001",
    "preferred_hygienist_name": "Jane Doe"
  },
  
  "fee_schedule": {
    "fee_schedule_id": "FS-007",
    "fee_schedule_name": "CP-50"
  },
  
  "patient_type": "General",
  "patient_flags": {
    "is_active": true,
    "is_ortho": false,
    "is_child": false,
    "is_collection_problem": false,
    "is_employee_family": false,
    "is_short_notice": false,
    "is_senior": false,
    "is_spanish_speaking": false,
    "assign_benefits": true,
    "hipaa_agreement": true,
    "no_correspondence": false,
    "no_auto_email": false,
    "no_auto_sms": false,
    "add_to_quickfill": false
  },
  
  "responsible_party": {
    "id": "RP-001",
    "name": "Smith, John (Self)",
    "type": "Cash",
    "relationship": "Self",
    "phone": "555-123-4567",
    "email": "john.smith@email.com",
    "home_office": "Cranberry Main"
  },
  
  "insurance": {
    "primary_dental": {
      "carrier_name": "Delta Dental",
      "plan_name": "Premium Plan",
      "group_number": "GRP-001",
      "subscriber_id": "SUB-001",
      "subscriber_name": "Smith, John",
      "relationship": "Self",
      "carrier_phone": "555-999-0000",
      "individual_max_remaining": 1500.00,
      "individual_deductible_remaining": 50.00,
      "is_active": true
    },
    "secondary_dental": null,
    "primary_medical": null,
    "secondary_medical": null
  },
  
  "account_members": [
    {
      "id": 123,
      "name": "Smith, John",
      "age": 44,
      "gender": "M",
      "next_visit": "2025-04-20",
      "recall": "6 months",
      "last_visit": "2024-03-15",
      "is_active": true
    }
  ],
  
  "appointments": [
    {
      "id": "APT-001",
      "date": "2025-04-20",
      "time": "10:00",
      "office": "Cranberry Main",
      "operatory": "OP3",
      "procedure": "Prophylaxis - Adult",
      "provider": "Dr. Smith",
      "duration": 30,
      "status": "Confirmed",
      "last_updated": "2024-03-20",
      "member": "Smith, John"
    }
  ],
  
  "recalls": [
    {
      "code": "D110",
      "age_range": "6 M -12",
      "next_date": "2026-04-27",
      "frequency": "Prophylaxis - Adult"
    }
  ],
  
  "balances": {
    "account_balance": -177.73,
    "today_charges": 0.00,
    "today_est_insurance": 0.00,
    "today_est_patient": 0.00,
    "last_insurance_payment": 93.98,
    "last_insurance_payment_date": "2020-10-03",
    "last_patient_payment": 32.10,
    "last_patient_payment_date": "2020-04-22",
    "aging": {
      "current": -177.73,
      "over_30": 0.00,
      "over_60": 0.00,
      "over_90": 0.00,
      "over_120": 0.00
    }
  },
  
  "clinical": {
    "first_visit": "2015-09-04",
    "last_visit": "2024-03-15",
    "next_visit": "2025-04-20",
    "next_recall": "2026-04-27",
    "last_pano_chart": "2023-08-16",
    "medical_alerts": [
      {
        "alert": "Allergic to Penicillin",
        "date": "2015-08-12T13:37:00Z",
        "entered_by": "PT"
      }
    ]
  },
  
  "notes": {
    "patient_notes": "Patient prefers morning appointments",
    "hipaa_sharing": "Full sharing allowed"
  },
  
  "referral": {
    "referral_type": "Patient",
    "referred_by": "",
    "referred_to": "",
    "referral_to_date": null
  },
  
  "preferences": {
    "preferred_language": "English",
    "contact_preference": "Cell Phone"
  },
  
  "created_at": "2015-09-04T10:00:00Z",
  "updated_at": "2024-03-20T14:45:00Z"
}
```

**Error Responses:**

- `404 Not Found` - Patient not found
- `401 Unauthorized` - Missing or invalid authentication token
- `403 Forbidden` - User doesn't have permission to view this patient

---

## Patient Create API

### Endpoint: `POST /api/v1/patients`

**Purpose:** Create a new patient with complete information.

**Request Body Schema:**

```json
{
  "identity": {
    "first_name": "John",
    "last_name": "Smith",
    "preferred_name": "Johnny",
    "dob": "1980-05-15",
    "gender": "M",
    "title": "Mr.",
    "pronouns": "He/Him",
    "marital_status": "Married"
  },
  
  "address": {
    "address_line_1": "123 Main St",
    "address_line_2": "Apt 4B",
    "city": "Pittsburgh",
    "state": "PA",
    "zip": "15201",
    "country": "USA"
  },
  
  "contact": {
    "home_phone": "555-123-4567",
    "cell_phone": "555-123-4568",
    "work_phone": "555-123-4569",
    "email": "john.smith@email.com",
    "preferred_contact": "Cell Phone"
  },
  
  "office": {
    "home_office_id": 108
  },
  
  "provider": {
    "preferred_provider_id": "PROV-001",
    "preferred_hygienist_id": "HYG-001"
  },
  
  "fee_schedule": {
    "fee_schedule_id": "FS-007"
  },
  
  "patient_type": "General",
  "patient_flags": {
    "is_ortho": false,
    "is_child": false,
    "is_collection_problem": false,
    "is_employee_family": false,
    "is_short_notice": false,
    "is_senior": false,
    "is_spanish_speaking": false,
    "assign_benefits": true,
    "hipaa_agreement": true,
    "no_correspondence": false,
    "no_auto_email": false,
    "no_auto_sms": false,
    "add_to_quickfill": false
  },
  
  "responsible_party": {
    "relationship": "Self",
    "responsible_party_id": null
  },
  
  "coverage": {
    "no_coverage": false,
    "primary_dental": true,
    "secondary_dental": false,
    "primary_medical": false,
    "secondary_medical": false
  },
  
  "referral": {
    "referral_type": "Patient",
    "referred_by": "",
    "referred_to": "",
    "referral_to_date": null
  },
  
  "guardian": {
    "guardian_name": "",
    "guardian_phone": ""
  },
  
  "notes": {
    "patient_notes": "Patient prefers morning appointments",
    "hipaa_sharing": "Full sharing allowed"
  },
  
  "starting_balances": {
    "current": 0.00,
    "over_30": 0.00,
    "over_60": 0.00,
    "over_90": 0.00,
    "over_120": 0.00
  }
}
```

**Required Fields:**

- `identity.first_name`
- `identity.last_name`
- `identity.dob`
- `office.home_office_id`

**Response Schema:**

Same as Patient Details API response (see above).

**Error Responses:**

- `400 Bad Request` - Invalid request data
- `422 Unprocessable Entity` - Validation errors
- `401 Unauthorized` - Missing or invalid authentication token
- `403 Forbidden` - User doesn't have permission to create patients
- `409 Conflict` - Duplicate patient (based on duplicate check rules)

---

## Patient Update API

### Endpoint: `PUT /api/v1/patients/{patientId}`

**Purpose:** Update an existing patient's information.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `patientId` | string | Yes | Patient chart number or ID |

**Request Body Schema:**

Same as Patient Create API, but all fields are optional (only include fields to update).

**Response Schema:**

Same as Patient Details API response.

**Error Responses:**

- `404 Not Found` - Patient not found
- `400 Bad Request` - Invalid request data
- `422 Unprocessable Entity` - Validation errors
- `401 Unauthorized` - Missing or invalid authentication token
- `403 Forbidden` - User doesn't have permission to update this patient

---

## Patient Metadata APIs

### Endpoint: `GET /api/v1/patients/metadata`

**Purpose:** Fetch all patient metadata in a single call (recommended for AddNewPatient form initialization).

**Response Schema:**

```json
{
  "titles": [
    { "code": "MR", "name": "Mr.", "description": "Mister" },
    { "code": "MRS", "name": "Mrs.", "description": "Missus" },
    { "code": "MS", "name": "Ms.", "description": "Miss" },
    { "code": "DR", "name": "Dr.", "description": "Doctor" }
  ],
  "pronouns": [
    { "code": "HE_HIM", "name": "He/Him", "description": "He/Him pronouns" },
    { "code": "SHE_HER", "name": "She/Her", "description": "She/Her pronouns" },
    { "code": "THEY_THEM", "name": "They/Them", "description": "They/Them pronouns" }
  ],
  "states": [
    { "code": "PA", "name": "Pennsylvania" },
    { "code": "CA", "name": "California" },
    { "code": "NY", "name": "New York" }
  ],
  "marital_statuses": [
    { "code": "SINGLE", "name": "Single" },
    { "code": "MARRIED", "name": "Married" },
    { "code": "WIDOWED", "name": "Widowed" },
    { "code": "DIVORCED", "name": "Divorced" }
  ],
  "genders": [
    { "code": "M", "name": "Male" },
    { "code": "F", "name": "Female" },
    { "code": "O", "name": "Not Specified / Unknown" }
  ],
  "responsible_party_relationships": [
    { "code": "SELF", "name": "Self", "description": "Patient is responsible party" },
    { "code": "SPOUSE", "name": "Spouse", "description": "Spouse is responsible party" },
    { "code": "CHILD", "name": "Child", "description": "Child relationship" },
    { "code": "OTHER", "name": "Other", "description": "Other relationship" },
    { "code": "NONE", "name": "None", "description": "No responsible party" }
  ],
  "contact_preferences": [
    { "code": "NO_PREFERENCE", "name": "No Preference" },
    { "code": "CALL_CELL", "name": "Call my Cell" },
    { "code": "CALL_HOME", "name": "Call my Home" },
    { "code": "CALL_WORK", "name": "Call my Work" },
    { "code": "TEXT_CELL", "name": "Text my Cell" },
    { "code": "EMAIL", "name": "Email me" }
  ],
  "referral_types": [
    { "code": "PATIENT", "name": "Patient", "description": "Self-referred patient" },
    { "code": "DIRECT", "name": "Direct", "description": "Direct referral" },
    { "code": "PHYSICIAN", "name": "Physician", "description": "Referred by physician" },
    { "code": "ONLINE", "name": "Online", "description": "Online referral" }
  ],
  "patient_types": [
    {
      "code": "CH",
      "name": "Child",
      "description": "Child patient"
    },
    {
      "code": "CP",
      "name": "Collection Problem",
      "description": "Collection Problem, See Notes"
    },
    {
      "code": "EF",
      "name": "Employee & Family",
      "description": "Employee & Family"
    },
    {
      "code": "OR",
      "name": "Ortho Patient",
      "description": "Orthodontic patient"
    },
    {
      "code": "SN",
      "name": "Short Notice Appointment",
      "description": "Short Notice Appointment"
    },
    {
      "code": "SR",
      "name": "Senior Citizen",
      "description": "Senior Citizen"
    },
    {
      "code": "SS",
      "name": "Spanish Speaking",
      "description": "Spanish Speaking"
    },
    {
      "code": "UP",
      "name": "Update Information",
      "description": "Update Information"
    }
  ]
}
```

**Alternative Individual Endpoints:**

If you prefer to fetch metadata separately:

### 1. Get Titles

**Endpoint:** `GET /api/v1/patients/metadata/titles`

**Response Schema:**

```json
{
  "titles": [
    { "code": "MR", "name": "Mr.", "description": "Mister" },
    { "code": "MRS", "name": "Mrs.", "description": "Missus" }
  ]
}
```

### 2. Get Pronouns

**Endpoint:** `GET /api/v1/patients/metadata/pronouns`

**Response Schema:**

```json
{
  "pronouns": [
    { "code": "HE_HIM", "name": "He/Him", "description": "He/Him pronouns" }
  ]
}
```

### 3. Get States

**Endpoint:** `GET /api/v1/patients/metadata/states`

**Response Schema:**

```json
{
  "states": [
    { "code": "PA", "name": "Pennsylvania" },
    { "code": "CA", "name": "California" }
  ]
}
```

### 4. Get Marital Statuses

**Endpoint:** `GET /api/v1/patients/metadata/marital-statuses`

**Response Schema:**

```json
{
  "marital_statuses": [
    { "code": "SINGLE", "name": "Single" },
    { "code": "MARRIED", "name": "Married" }
  ]
}
```

### 5. Get Genders

**Endpoint:** `GET /api/v1/patients/metadata/genders`

**Response Schema:**

```json
{
  "genders": [
    { "code": "M", "name": "Male" },
    { "code": "F", "name": "Female" },
    { "code": "O", "name": "Not Specified / Unknown" }
  ]
}
```

### 6. Get Patient Types

**Endpoint:** `GET /api/v1/patients/metadata/patient-types`

**Response Schema:**

```json
{
  "patient_types": [
    {
      "code": "CH",
      "name": "Child",
      "description": "Child patient"
    },
    {
      "code": "OR",
      "name": "Ortho Patient",
      "description": "Orthodontic patient"
    }
  ]
}
```

### 7. Get Referral Types

**Endpoint:** `GET /api/v1/patients/metadata/referral-types`

**Response Schema:**

```json
{
  "referral_types": [
    {
      "code": "PATIENT",
      "name": "Patient",
      "description": "Self-referred patient"
    },
    {
      "code": "DENTIST",
      "name": "Dentist",
      "description": "Referred by dentist"
    }
  ]
}
```

### 8. Get Responsible Party Relationships

**Endpoint:** `GET /api/v1/patients/metadata/responsible-party-relationships`

**Response Schema:**

```json
{
  "relationships": [
    {
      "code": "SELF",
      "name": "Self",
      "description": "Patient is responsible party"
    },
    {
      "code": "SPOUSE",
      "name": "Spouse",
      "description": "Spouse is responsible party"
    }
  ]
}
```

### 9. Get Contact Preferences

**Endpoint:** `GET /api/v1/patients/metadata/contact-preferences`

**Response Schema:**

```json
{
  "contact_preferences": [
    {
      "code": "NO_PREFERENCE",
      "name": "No Preference"
    },
    {
      "code": "HOME_PHONE",
      "name": "Home Phone"
    },
    {
      "code": "CELL_PHONE",
      "name": "Cell Phone"
    },
    {
      "code": "EMAIL",
      "name": "Email"
    }
  ]
}
```

### 10. Get Fee Schedules

**Endpoint:** `GET /api/v1/patients/metadata/fee-schedules`

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `office_id` | string | No | Filter by office ID |

**Response Schema:**

```json
{
  "fee_schedules": [
    {
      "fee_schedule_id": "FS-007",
      "fee_schedule_name": "CP-50",
      "description": "United Concordia PPO Plan",
      "office_id": 108,
      "office_name": "Cranberry Main"
    }
  ]
}
```

### 11. Check Duplicate Patient

**Endpoint:** `POST /api/v1/patients/check-duplicate`

**Purpose:** Check if a patient with similar information already exists (used before creating new patient).

**Request Body:**

```json
{
  "first_name": "John",
  "last_name": "Smith",
  "dob": "1980-05-15",
  "phone": "555-123-4567",
  "email": "john.smith@email.com"
}
```

**Response Schema:**

```json
{
  "has_duplicates": true,
  "duplicates": [
    {
      "id": 123,
      "chart_no": "CH-001",
      "name": "Smith, John",
      "dob": "1980-05-15",
      "phone": "555-123-4567",
      "match_score": 0.95,
      "match_reasons": ["Name match", "DOB match", "Phone match"]
    }
  ]
}
```

---

## Common Response Formats

### Success Response

All successful responses follow this structure:

```json
{
  "data": { ... },
  "message": "Operation successful" // Optional
}
```

### Error Response

All error responses follow this structure:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": "Additional error details (optional)"
  }
}
```

### Pagination

Paginated responses include:

```json
{
  "data": [ ... ],
  "total": 100,
  "limit": 50,
  "offset": 0,
  "has_more": true
}
```

---

## Authentication

All endpoints require authentication via JWT token in the Authorization header:

```
Authorization: Bearer <access_token>
```

---

## Data Formats

- **Dates:** ISO 8601 format (YYYY-MM-DD) or YYYY-MM-DDTHH:MM:SSZ for timestamps
- **Phone Numbers:** Format: "XXX-XXX-XXXX" or "XXXXXXXXXX" (backend should normalize)
- **Currency:** Decimal numbers (e.g., 150.00)
- **Boolean:** `true` or `false`
- **Field Names:** snake_case in API, camelCase in frontend (transformation required)

---

## Implementation Notes

### Backend Requirements

1. **Search Implementation:**
   - Implement field-specific search (only search in the specified `search_by` field)
   - Support partial matching for text fields
   - Support exact matching for IDs, chart numbers, SSN
   - Support date range matching for birth dates

2. **Search Scope:**
   - `current`: Filter by `office_id` in patient's `home_office_id`
   - `all`: No office filtering (but respect user's office access permissions)
   - `group`: Filter by office group (if office groups are implemented)

3. **Patient Type:**
   - Store patient type as flags or a single field
   - Filter based on orthodontic vs. general patient designation

4. **Inactive Patients:**
   - Maintain an `is_active` flag in the patients table
   - Only return inactive patients when `include_inactive` is `true`

5. **Responsible Party Search:**
   - When `search_for` is `"responsible"`, search in responsible_party table
   - Join with patients table to return patient records linked to matching responsible parties

### Frontend Implementation

1. **Data Transformation:**
   - Convert snake_case API responses to camelCase for frontend
   - Convert camelCase frontend requests to snake_case for API
   - Format dates between MM/DD/YYYY (UI) and YYYY-MM-DD (API)

2. **Error Handling:**
   - Display user-friendly error messages
   - Handle 404, 401, 403, 422 errors gracefully
   - Show loading states during API calls

3. **Validation:**
   - Client-side validation before API calls
   - Display validation errors from API responses

---

## Testing

### Test Cases

1. **Search Tests:**
   - Search by each `search_by` option
   - Test search scope filters
   - Test patient type filters
   - Test inactive patient inclusion
   - Test pagination

2. **Create Tests:**
   - Create patient with all fields
   - Create patient with minimal required fields
   - Test duplicate detection
   - Test validation errors

3. **Update Tests:**
   - Update single field
   - Update multiple fields
   - Test partial updates

4. **Details Tests:**
   - Fetch patient by chart number
   - Fetch patient by ID
   - Test 404 for non-existent patient

---

## Version History

- **v1.0.0** (2026-01-20): Initial API contract specification

---

## Support

For questions or clarifications about this API contract, please contact the development team.
