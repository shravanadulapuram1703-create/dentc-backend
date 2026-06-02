# Update Patient API Contract

## Endpoint
**PUT** `/api/v1/patients/{patientId}`

## Purpose
Update an existing patient's information with full details. This endpoint supports partial updates (all fields are optional except `patientId` in the path).

---

## Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `patientId` | `integer` | Yes | Numeric patient ID (e.g., `123`), not chart number |

---

## Request Headers

```
Authorization: Bearer {access_token}
Content-Type: application/json
```

---

## Request Body Schema

The request body follows the same structure as `PatientCreateRequestFull`, but **all fields are optional** (partial update support):

```typescript
{
  identity?: {
    first_name?: string;
    last_name?: string;
    preferred_name?: string;
    dob?: string;                    // YYYY-MM-DD format
    gender?: "M" | "F" | "O";
    title?: string;
    pronouns?: string;
    marital_status?: string;
    ssn?: string;                    // Digits only, no dashes (e.g., "123456789")
  };
  
  address?: {
    address_line_1?: string;
    address_line_2?: string;
    city?: string;
    state?: string;                  // State code (e.g., "PA", "CA")
    zip?: string;
    country?: string;
  };
  
  contact?: {
    home_phone?: string;
    cell_phone?: string;
    work_phone?: string;
    email?: string;
    preferred_contact?: string;      // One of: "home_phone", "cell_phone", "work_phone", "email"
  };
  
  office?: {
    home_office_id?: number;         // Numeric office ID
  };
  
  provider?: {
    preferred_provider_id?: string;
    preferred_hygienist_id?: string;
  };
  
  fee_schedule?: {
    fee_schedule_id?: string;
  };
  
  patient_type?: string;             // "General" or "Ortho"
  
  patient_flags?: {
    is_ortho?: boolean;
    is_child?: boolean;
    is_collection_problem?: boolean;
    is_employee_family?: boolean;
    is_short_notice?: boolean;
    is_senior?: boolean;
    is_spanish_speaking?: boolean;
    assign_benefits?: boolean;
    hipaa_agreement?: boolean;
    no_correspondence?: boolean;
    no_auto_email?: boolean;
    no_auto_sms?: boolean;
    add_to_quickfill?: boolean;
  };
  
  responsible_party?: {
    relationship?: string;
    responsible_party_id?: string;
  };
  
  coverage?: {
    no_coverage?: boolean;
    primary_dental?: boolean;
    secondary_dental?: boolean;
    primary_medical?: boolean;
    secondary_medical?: boolean;
  };
  
  referral?: {
    referral_type?: string;
    referred_by?: string;
    referred_to?: string;
    referral_to_date?: string;       // YYYY-MM-DD format
  };
  
  guardian?: {
    guardian_name?: string;
    guardian_phone?: string;
  };
  
  notes?: {
    patient_notes?: string;          // Max 1000 characters
    hipaa_sharing?: string;          // Max 1000 characters
  };
  
  starting_balances?: {
    current?: number;
    over_30?: number;
    over_60?: number;
    over_90?: number;
    over_120?: number;
  };
  
  patient_types?: string[];          // Array of patient type codes (e.g., ["CH", "OR", "SR"])
}
```

---

## Example Request

### Full Update
```json
PUT /api/v1/patients/123
Content-Type: application/json
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

{
  "identity": {
    "first_name": "John",
    "last_name": "Doe",
    "preferred_name": "Johnny",
    "dob": "1990-05-15",
    "gender": "M",
    "title": "Mr.",
    "pronouns": "He/Him",
    "marital_status": "Married",
    "ssn": "123456789"
  },
  "address": {
    "address_line_1": "123 Main St",
    "address_line_2": "Apt 4B",
    "city": "Pittsburgh",
    "state": "PA",
    "zip": "15213",
    "country": "USA"
  },
  "contact": {
    "home_phone": "4125551234",
    "cell_phone": "4125555678",
    "work_phone": "4125559012",
    "email": "john.doe@example.com",
    "preferred_contact": "cell_phone"
  },
  "office": {
    "home_office_id": 108
  },
  "provider": {
    "preferred_provider_id": "PROV-001",
    "preferred_hygienist_id": "PROV-002"
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
    "responsible_party_id": "RP-001"
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
    "referred_by": "Dr. Smith",
    "referred_to": "Specialist A",
    "referral_to_date": "2025-01-20"
  },
  "guardian": {
    "guardian_name": "Jane Doe",
    "guardian_phone": "4125559999"
  },
  "notes": {
    "patient_notes": "Patient prefers morning appointments.",
    "hipaa_sharing": "Patient has authorized sharing with family members."
  },
  "starting_balances": {
    "current": 0.00,
    "over_30": 0.00,
    "over_60": 0.00,
    "over_90": 0.00,
    "over_120": 0.00
  },
  "patient_types": ["SR"]
}
```

### Partial Update (Only Contact Information)
```json
PUT /api/v1/patients/123
Content-Type: application/json
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

{
  "contact": {
    "cell_phone": "4125559999",
    "email": "newemail@example.com",
    "preferred_contact": "email"
  }
}
```

---

## Response

### Success Response (200 OK)

Returns the updated `PatientDetails` object (same structure as GET `/api/v1/patients/{patientId}`):

```json
{
  "id": 123,
  "chart_no": "CH008",
  "first_name": "John",
  "last_name": "Doe",
  "preferred_name": "Johnny",
  "dob": "1990-05-15",
  "gender": "M",
  "title": "Mr.",
  "pronouns": "He/Him",
  "marital_status": "Married",
  "address": {
    "address_line_1": "123 Main St",
    "address_line_2": "Apt 4B",
    "city": "Pittsburgh",
    "state": "PA",
    "zip": "15213",
    "country": "USA"
  },
  "contact": {
    "home_phone": "4125551234",
    "cell_phone": "4125555678",
    "work_phone": "4125559012",
    "email": "john.doe@example.com",
    "preferred_contact": "cell_phone"
  },
  "office": {
    "home_office_id": 108,
    "home_office_name": "Cranberry Dental Arts",
    "home_office_code": "OFF-108"
  },
  "provider": {
    "preferred_provider_id": "PROV-001",
    "preferred_provider_name": "Dr. Smith",
    "preferred_hygienist_id": "PROV-002",
    "preferred_hygienist_name": "Jane Hygienist"
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
    "is_senior": true,
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
    "name": "John Doe",
    "type": "Patient",
    "relationship": "Self",
    "phone": "4125551234",
    "email": "john.doe@example.com",
    "home_office": "Cranberry Dental Arts"
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
    "referred_by": "Dr. Smith",
    "referred_to": "Specialist A",
    "referral_to_date": "2025-01-20"
  },
  "guardian": {
    "guardian_name": "Jane Doe",
    "guardian_phone": "4125559999"
  },
  "notes": {
    "patient_notes": "Patient prefers morning appointments.",
    "hipaa_sharing": "Patient has authorized sharing with family members."
  },
  "starting_balances": {
    "current": 0.00,
    "over_30": 0.00,
    "over_60": 0.00,
    "over_90": 0.00,
    "over_120": 0.00
  },
  "patient_types": ["SR"],
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-20T14:45:00Z"
}
```

---

## Error Responses

### 400 Bad Request
```json
{
  "detail": "Invalid request body. Missing required fields or invalid data format."
}
```

**Common causes:**
- Invalid date format (must be YYYY-MM-DD)
- Invalid gender value (must be "M", "F", or "O")
- Invalid patient type (must be "General" or "Ortho")
- Invalid preferred_contact value
- Invalid SSN format (must be digits only)

### 401 Unauthorized
```json
{
  "detail": "Not authenticated"
}
```

### 403 Forbidden
```json
{
  "detail": "Not authorized to update this patient"
}
```

### 404 Not Found
```json
{
  "detail": "Patient not found"
}
```

**Cause:** Patient with the given `patientId` does not exist.

### 422 Unprocessable Entity
```json
{
  "detail": "Validation error",
  "errors": {
    "identity.dob": ["Invalid date format. Expected YYYY-MM-DD."],
    "contact.email": ["Invalid email format."],
    "office.home_office_id": ["Office does not exist."]
  }
}
```

---

## Field Descriptions

### Identity Fields
- **`first_name`**: Patient's first name (required for new patients, optional for updates)
- **`last_name`**: Patient's last name (required for new patients, optional for updates)
- **`preferred_name`**: Patient's preferred name/nickname
- **`dob`**: Date of birth in YYYY-MM-DD format
- **`gender`**: One of "M" (Male), "F" (Female), "O" (Other)
- **`title`**: Title (e.g., "Mr.", "Mrs.", "Ms.", "Dr.")
- **`pronouns`**: Preferred pronouns (e.g., "He/Him", "She/Her", "They/Them")
- **`marital_status`**: Marital status (e.g., "Single", "Married", "Divorced", "Widowed")
- **`ssn`**: Social Security Number (digits only, no dashes or spaces)

### Address Fields
- **`address_line_1`**: Primary address line
- **`address_line_2`**: Secondary address line (apartment, suite, etc.)
- **`city`**: City name
- **`state`**: Two-letter state code (e.g., "PA", "CA", "NY")
- **`zip`**: ZIP/postal code
- **`country`**: Country name (default: "USA")

### Contact Fields
- **`home_phone`**: Home phone number (format: digits only or formatted string)
- **`cell_phone`**: Cell/mobile phone number
- **`work_phone`**: Work phone number
- **`email`**: Email address (must be valid email format)
- **`preferred_contact`**: Preferred contact method. Must be one of:
  - `"home_phone"`
  - `"cell_phone"`
  - `"work_phone"`
  - `"email"`

### Office & Provider Fields
- **`home_office_id`**: Numeric office ID (e.g., `108`, not `"OFF-108"`)
- **`preferred_provider_id`**: Provider ID (string format, e.g., `"PROV-001"`)
- **`preferred_hygienist_id`**: Hygienist ID (string format, e.g., `"PROV-002"`)
- **`fee_schedule_id`**: Fee schedule ID (string format, e.g., `"FS-007"`)

### Patient Type & Flags
- **`patient_type`**: Either `"General"` or `"Ortho"`
- **`patient_flags`**: Object containing boolean flags:
  - `is_ortho`: Orthodontic patient
  - `is_child`: Child patient
  - `is_collection_problem`: Collection problem flag
  - `is_employee_family`: Employee & family
  - `is_short_notice`: Short notice appointment
  - `is_senior`: Senior citizen
  - `is_spanish_speaking`: Spanish speaking
  - `assign_benefits`: Assign benefits to patient
  - `hipaa_agreement`: HIPAA agreement signed
  - `no_correspondence`: No correspondence flag
  - `no_auto_email`: No automatic emails
  - `no_auto_sms`: No automatic SMS
  - `add_to_quickfill`: Add to quick-fill list
- **`patient_types`**: Array of patient type codes (e.g., `["CH", "OR", "SR"]`). Codes:
  - `"CH"`: Child
  - `"CP"`: Collection Problem
  - `"EF"`: Employee & Family
  - `"OR"`: Ortho Patient
  - `"SN"`: Short Notice Appointment
  - `"SR"`: Senior Citizen
  - `"SS"`: Spanish Speaking
  - `"UP"`: Update Information

### Responsible Party
- **`relationship`**: Relationship to responsible party (e.g., "Self", "Parent", "Guardian")
- **`responsible_party_id`**: ID of the responsible party (if different from patient)

### Coverage
- **`no_coverage`**: Patient has no insurance coverage
- **`primary_dental`**: Has primary dental insurance
- **`secondary_dental`**: Has secondary dental insurance
- **`primary_medical`**: Has primary medical insurance
- **`secondary_medical`**: Has secondary medical insurance

### Referral
- **`referral_type`**: Type of referral (e.g., "Patient", "Doctor", "Friend/Family")
- **`referred_by`**: Name of person/entity who referred the patient
- **`referred_to`**: Name of specialist/entity patient was referred to
- **`referral_to_date`**: Date of referral in YYYY-MM-DD format

### Guardian
- **`guardian_name`**: Health care guardian name
- **`guardian_phone`**: Health care guardian phone number

### Notes
- **`patient_notes`**: General patient notes (max 1000 characters)
- **`hipaa_sharing`**: HIPAA information sharing notes (max 1000 characters)

### Starting Balances
- **`current`**: Current balance (0-30 days)
- **`over_30`**: Balance over 30 days
- **`over_60`**: Balance over 60 days
- **`over_90`**: Balance over 90 days
- **`over_120`**: Balance over 120 days

---

## Business Rules

1. **Partial Updates**: All fields are optional. Only provided fields will be updated. Fields not included in the request will remain unchanged.

2. **Date Formats**: 
   - All dates must be in `YYYY-MM-DD` format (ISO 8601 date)
   - DOB must be a valid date in the past

3. **SSN Format**: 
   - SSN must be 9 digits only (no dashes, spaces, or other characters)
   - Example: `"123456789"` ✅ | `"123-45-6789"` ❌

4. **Phone Numbers**: 
   - Can be digits only or formatted strings
   - Backend should normalize to digits only for storage

5. **Email Validation**: 
   - Must be a valid email format
   - Backend should validate email format

6. **Office ID**: 
   - Must be a numeric value (e.g., `108`), not formatted string (e.g., `"OFF-108"`)
   - Office must exist in the system

7. **Provider/Hygienist IDs**: 
   - Must be valid provider IDs that exist in the system
   - Can be `null` or empty string to clear the preference

8. **Fee Schedule**: 
   - Must be a valid fee schedule ID that exists in the system
   - Can be `null` or omitted to keep existing fee schedule

9. **Patient Type**: 
   - Must be either `"General"` or `"Ortho"`
   - If `patient_flags.is_ortho` is `true`, `patient_type` should typically be `"Ortho"`

10. **Patient Types Array**: 
    - Array of codes (e.g., `["CH", "OR", "SR"]`)
    - Codes must be valid patient type codes
    - Empty array `[]` clears all patient types

11. **Preferred Contact**: 
    - Must match one of the contact fields provided
    - If `preferred_contact` is `"cell_phone"`, `contact.cell_phone` should be provided

12. **Responsible Party**: 
    - If `relationship` is `"Self"`, `responsible_party_id` should typically be the patient's own ID
    - If `relationship` is not `"Self"`, `responsible_party_id` should reference another patient/party

13. **Coverage Flags**: 
    - If `no_coverage` is `true`, all other coverage flags should typically be `false`
    - At least one coverage type should be selected if `no_coverage` is `false`

14. **Notes Length**: 
    - `patient_notes` and `hipaa_sharing` are limited to 1000 characters each
    - Backend should truncate or reject if exceeded

15. **Starting Balances**: 
    - All balance values should be non-negative numbers
    - Typically used only when creating new patients or adjusting balances

---

## Frontend Implementation Notes

### Data Transformation

1. **Date Format Conversion**:
   - Frontend displays: `MM/DD/YYYY` or `YYYY-MM-DD` (for date inputs)
   - API expects: `YYYY-MM-DD`
   - Conversion: Use `new Date(dateString).toISOString().split('T')[0]` or similar

2. **SSN Format**:
   - Frontend displays: `XXX-XX-XXXX` (formatted)
   - API expects: `123456789` (digits only)
   - Conversion: `ssn.replace(/\D/g, '')`

3. **Phone Number Format**:
   - Frontend displays: `(XXX) XXX-XXXX` (formatted)
   - API accepts: Formatted or digits only
   - Backend should normalize to digits only

4. **Gender Mapping**:
   - Frontend displays: `"Male"`, `"Female"`, `"Other"`
   - API expects: `"M"`, `"F"`, `"O"`
   - Mapping: Use metadata API to get code from display name

5. **Patient Type Flags to Array**:
   - Frontend: Checkboxes for each type (CH, CP, EF, OR, SN, SR, SS, UP)
   - API expects: Array of codes `["CH", "OR", "SR"]`
   - Conversion: Filter checked types and map to codes

6. **Preferred Contact**:
   - Frontend displays: `"Home Phone"`, `"Cell Phone"`, etc.
   - API expects: `"home_phone"`, `"cell_phone"`, etc.
   - Conversion: Convert display name to snake_case

### Naming Conventions

- **Frontend (camelCase)**: `firstName`, `lastName`, `homePhone`, `cellPhone`, `preferredContact`
- **Backend (snake_case)**: `first_name`, `last_name`, `home_phone`, `cell_phone`, `preferred_contact`
- **API Request/Response**: Use snake_case (backend convention)

---

## Testing Examples

### Test Case 1: Update Only Contact Information
```json
PUT /api/v1/patients/123
{
  "contact": {
    "cell_phone": "4125559999",
    "preferred_contact": "cell_phone"
  }
}
```

### Test Case 2: Update Patient Flags
```json
PUT /api/v1/patients/123
{
  "patient_flags": {
    "is_senior": true,
    "add_to_quickfill": true
  },
  "patient_types": ["SR"]
}
```

### Test Case 3: Update Address
```json
PUT /api/v1/patients/123
{
  "address": {
    "address_line_1": "456 New St",
    "city": "Philadelphia",
    "state": "PA",
    "zip": "19101"
  }
}
```

---

## Related Endpoints

- **GET** `/api/v1/patients/{patientId}` - Get patient details (for loading existing data)
- **POST** `/api/v1/patients` - Create new patient
- **DELETE** `/api/v1/patients/{patientId}` - Delete patient
- **GET** `/api/v1/patients/metadata` - Get patient metadata (titles, pronouns, states, etc.)

---

## Notes

- This endpoint supports **partial updates**. Only include fields that need to be updated.
- Fields not included in the request will remain unchanged in the database.
- The response returns the complete updated patient object, including all fields (updated and unchanged).
- All date fields should use ISO 8601 format (`YYYY-MM-DD`).
- All timestamps in responses use ISO 8601 format with timezone (`YYYY-MM-DDTHH:mm:ssZ`).
