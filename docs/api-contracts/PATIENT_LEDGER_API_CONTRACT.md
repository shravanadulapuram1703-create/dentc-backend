# Patient Ledger API Contract

This document defines all backend APIs required to support the Patient Ledger module with complete workflow support.

## Table of Contents
1. [Ledger Entries](#ledger-entries)
2. [Balances & Aging](#balances--aging)
3. [Procedures](#procedures)
4. [Claims](#claims)
5. [Payments](#payments)
6. [Adjustments](#adjustments)
7. [Metadata APIs](#metadata-apis)

---

## Ledger Entries

### GET /api/v1/patients/{patientId}/ledger

Get paginated ledger entries for a patient.

**Path Parameters:**
- `patientId` (string, required): Patient numeric ID

**Query Parameters:**
- `date_from` (string, optional): Filter from date (YYYY-MM-DD)
- `date_to` (string, optional): Filter to date (YYYY-MM-DD)
- `transaction_type` (string, optional): Filter by type (`procedure`, `payment`, `adjustment`, `claim_event`)
- `status` (string, optional): Filter by status (`not_sent`, `sent`, `paid`, `partial`, `denied`, `posted`)
- `limit` (integer, optional): Page size (default: 25, max: 100)
- `offset` (integer, optional): Pagination offset (default: 0)
- `sort_by` (string, optional): Sort field (`date`, `amount`, `provider`, `code`) (default: `date`)
- `sort_order` (string, optional): Sort direction (`asc`, `desc`) (default: `desc`)

**Response Schema:**
```json
{
  "ledger_entries": [
    {
      "id": "string",
      "transaction_id": "string",
      "posted_date": "YYYY-MM-DD",
      "patient_id": "string",
      "patient_name": "string",
      "office_id": "string",
      "office_name": "string",
      "apply_to": "string", // "P" (Patient) or "R" (Responsible Party)
      "code": "string", // CDT code, "PMT", "CLM-P", "ADJ", etc.
      "tooth": "string", // Tooth number or empty
      "surface": "string", // Surface codes or empty
      "type": "string", // "P" (Production) or "C" (Collection)
      "has_notes": boolean,
      "has_eob": boolean,
      "has_attachments": boolean,
      "description": "string",
      "billing_order": "string", // "P", "S", etc.
      "duration_minutes": integer,
      "provider_id": "string",
      "provider_name": "string",
      "est_patient": number,
      "est_insurance": number,
      "posted_amount": number, // Positive for charges, negative for payments/adjustments
      "running_balance": number,
      "created_by": "string",
      "created_at": "YYYY-MM-DDTHH:mm:ssZ",
      "transaction_type": "string", // "procedure", "patient_payment", "insurance_payment", "adjustment", "claim_event"
      "status": "string", // "not_sent", "sent", "paid", "partial", "denied", "posted", ""
      "procedure_id": "string | null", // If transaction_type is "procedure"
      "claim_id": "string | null", // If transaction_type is "claim_event"
      "payment_id": "string | null", // If transaction_type is "payment"
      "adjustment_id": "string | null" // If transaction_type is "adjustment"
    }
  ],
  "pagination": {
    "total": integer,
    "limit": integer,
    "offset": integer,
    "has_more": boolean
  }
}
```

**Error Responses:**
- `400 Bad Request`: Invalid patient ID or query parameters
- `404 Not Found`: Patient not found
- `500 Internal Server Error`: Server error

---

## Balances & Aging

### GET /api/v1/patients/{patientId}/balances

Get account balances and aging information for a patient.

**Path Parameters:**
- `patientId` (string, required): Patient numeric ID

**Response Schema:**
```json
{
  "account_balance": number,
  "patient_balance": number,
  "insurance_balance": number,
  "estimated_insurance": number,
  "estimated_patient": number,
  "aging": {
    "current": number, // 0-30 days
    "age_30": number, // 31-60 days
    "age_60": number, // 61-90 days
    "age_90": number, // 91-120 days
    "age_120": number // 120+ days
  },
  "recent_activity": {
    "today_charges": number,
    "last_insurance_payment": {
      "amount": number,
      "date": "YYYY-MM-DD"
    },
    "last_patient_payment": {
      "amount": number,
      "date": "YYYY-MM-DD"
    }
  }
}
```

**Error Responses:**
- `404 Not Found`: Patient not found
- `500 Internal Server Error`: Server error

---

## Procedures

### POST /api/v1/patients/{patientId}/procedures

Add a new procedure to the patient ledger.

**Path Parameters:**
- `patientId` (string, required): Patient numeric ID

**Request Schema:**
```json
{
  "procedure_code": "string", // Required: CDT code (e.g., "D0150")
  "date_of_service": "YYYY-MM-DD", // Required
  "provider_id": "string", // Required: Treating provider ID
  "office_id": "string", // Required: Office where procedure performed
  "tooth": "string | null", // Optional: Tooth number
  "surface": "string | null", // Optional: Surface codes (e.g., "MOD")
  "quadrant": "string | null", // Optional: Quadrant (1-4)
  "materials": ["string"] | null, // Optional: Material codes
  "duration_minutes": integer, // Optional
  "fee": number, // Required: Procedure fee
  "est_patient": number, // Required: Estimated patient portion
  "est_insurance": number, // Required: Estimated insurance portion
  "billing_order": "string", // Optional: "P" (Primary), "S" (Secondary), etc.
  "notes": "string | null", // Optional: Procedure notes
  "apply_to": "string" // Optional: "P" (Patient) or "R" (Responsible Party), default: "P"
}
```

**Response Schema:**
```json
{
  "procedure_id": "string",
  "ledger_entry_id": "string",
  "transaction_id": "string",
  "posted_date": "YYYY-MM-DD",
  "running_balance": number,
  "status": "string", // "not_sent"
  "created_at": "YYYY-MM-DDTHH:mm:ssZ"
}
```

**Error Responses:**
- `400 Bad Request`: Invalid request data, missing required fields, or validation errors
- `404 Not Found`: Patient, provider, or office not found
- `422 Unprocessable Entity`: Business rule violations (e.g., invalid procedure code, missing required fields for procedure type)
- `500 Internal Server Error`: Server error

**Validation Rules:**
- Procedure code must be valid CDT code
- Date of service cannot be in the future
- Fee must be positive
- est_patient + est_insurance should equal fee (warning if not)
- If procedure requires tooth/surface/quadrant/materials, those fields must be provided

---

### GET /api/v1/patients/{patientId}/procedures/{procedureId}

Get details of a specific procedure.

**Path Parameters:**
- `patientId` (string, required): Patient numeric ID
- `procedureId` (string, required): Procedure ID

**Response Schema:**
```json
{
  "procedure_id": "string",
  "procedure_code": "string",
  "date_of_service": "YYYY-MM-DD",
  "provider_id": "string",
  "provider_name": "string",
  "office_id": "string",
  "office_name": "string",
  "tooth": "string | null",
  "surface": "string | null",
  "quadrant": "string | null",
  "materials": ["string"] | null,
  "duration_minutes": integer,
  "fee": number,
  "est_patient": number,
  "est_insurance": number,
  "billing_order": "string",
  "notes": "string | null",
  "status": "string",
  "claim_id": "string | null",
  "ledger_entry_id": "string",
  "created_by": "string",
  "created_at": "YYYY-MM-DDTHH:mm:ssZ",
  "updated_at": "YYYY-MM-DDTHH:mm:ssZ"
}
```

---

### PUT /api/v1/patients/{patientId}/procedures/{procedureId}

Update an existing procedure (only if not sent to insurance).

**Path Parameters:**
- `patientId` (string, required): Patient numeric ID
- `procedureId` (string, required): Procedure ID

**Request Schema:** (Same as POST, all fields optional except those being updated)

**Response Schema:** (Same as GET)

**Error Responses:**
- `400 Bad Request`: Invalid request data
- `403 Forbidden`: Procedure already sent to insurance, cannot be modified
- `404 Not Found`: Procedure not found
- `422 Unprocessable Entity`: Business rule violations

---

### DELETE /api/v1/patients/{patientId}/procedures/{procedureId}

Delete a procedure (only if not sent to insurance).

**Path Parameters:**
- `patientId` (string, required): Patient numeric ID
- `procedureId` (string, required): Procedure ID

**Response:** `204 No Content`

**Error Responses:**
- `403 Forbidden`: Procedure already sent to insurance, cannot be deleted
- `404 Not Found`: Procedure not found
- `500 Internal Server Error`: Server error

---

## Claims

### POST /api/v1/patients/{patientId}/claims

Create a new claim from selected procedures.

**Path Parameters:**
- `patientId` (string, required): Patient numeric ID

**Request Schema:**
```json
{
  "procedure_ids": ["string"], // Required: Array of procedure IDs to include in claim
  "claim_type": "string", // Required: "dental", "medical"
  "billing_order": "string", // Required: "primary", "secondary", etc.
  "date_of_service_from": "YYYY-MM-DD", // Optional: Earliest DOS
  "date_of_service_to": "YYYY-MM-DD", // Optional: Latest DOS
  "notes": "string | null" // Optional: Claim notes
}
```

**Response Schema:**
```json
{
  "claim_id": "string",
  "claim_number": "string", // Auto-generated claim number
  "status": "string", // "created", "sent", "paid", "partial", "denied", "closed"
  "claim_type": "string",
  "billing_order": "string",
  "date_of_service_from": "YYYY-MM-DD",
  "date_of_service_to": "YYYY-MM-DD",
  "total_submitted_fees": number,
  "total_fee": number,
  "total_est_insurance": number,
  "procedures": [
    {
      "procedure_id": "string",
      "procedure_code": "string",
      "date_of_service": "YYYY-MM-DD",
      "fee": number,
      "est_insurance": number
    }
  ],
  "created_by": "string",
  "created_at": "YYYY-MM-DDTHH:mm:ssZ"
}
```

**Error Responses:**
- `400 Bad Request`: Invalid request data, no procedures selected, or procedures already in a claim
- `404 Not Found`: Patient or procedures not found
- `422 Unprocessable Entity`: Business rule violations (e.g., procedures from different dates, already sent)
- `500 Internal Server Error`: Server error

---

### GET /api/v1/patients/{patientId}/claims/{claimId}

Get detailed claim information.

**Path Parameters:**
- `patientId` (string, required): Patient numeric ID
- `claimId` (string, required): Claim ID

**Response Schema:**
```json
{
  "claim_id": "string",
  "claim_number": "string",
  "status": "string",
  "claim_type": "string",
  "billing_order": "string",
  "date_of_service_from": "YYYY-MM-DD",
  "date_of_service_to": "YYYY-MM-DD",
  "created_date": "YYYY-MM-DD",
  "created_time": "HH:mm:ss",
  "created_by": "string",
  "last_status_update_date": "YYYY-MM-DD | null",
  "claim_sent_date": "YYYY-MM-DD | null",
  "claim_sent_status": "string | null",
  "claim_close_date": "YYYY-MM-DD | null",
  "claim_closed_by": "string | null",
  "dxc_attachment_id": "string | null",
  "icd10_codes": "string | null",
  "patient_info": {
    "patient_id": "string",
    "patient_name": "string",
    "patient_dob": "YYYY-MM-DD",
    "subscriber_name": "string",
    "subscriber_id": "string",
    "subscriber_dob": "YYYY-MM-DD",
    "responsible_party_name": "string",
    "responsible_party_id": "string",
    "responsible_party_dob": "YYYY-MM-DD"
  },
  "coverage_info": {
    "insurance_carrier": "string",
    "carrier_phone": "string | null",
    "group_plan": "string | null",
    "benefits_used": "string | null",
    "employer_name": "string | null",
    "deductibles_used": "string | null"
  },
  "billing_dentist": {
    "provider_id": "string",
    "provider_name": "string"
  },
  "treating_dentist": {
    "provider_id": "string",
    "provider_name": "string"
  },
  "amounts": {
    "total_submitted_fees": number,
    "total_fee": number,
    "total_est_insurance": number,
    "total_insurance_paid": number,
    "variance": number
  },
  "payment_info": {
    "check_number": "string | null",
    "bank_number": "string | null",
    "eob_number": "string | null"
  },
  "notes": "string | null",
  "attachment_required": boolean,
  "procedures": [
    {
      "procedure_id": "string",
      "dos": "YYYY-MM-DD",
      "code": "string",
      "tooth": "string | null",
      "surface": "string | null",
      "description": "string",
      "bref": "string", // Benefit reference
      "submitted": number,
      "fee": number,
      "est_ins": number,
      "ins_paid": number,
      "ins_overpayment": number,
      "ins_allocated": number,
      "overpayment_disbursement": number,
      "write_off_1": number,
      "write_off_2": number,
      "write_off_3": number,
      "other_insurance": number,
      "reason_code": "string | null"
    }
  ],
  "attachments": [
    {
      "attachment_id": "string",
      "attachment_type": "string",
      "required": boolean,
      "provided": boolean,
      "file_name": "string | null",
      "uploaded_at": "YYYY-MM-DDTHH:mm:ssZ | null"
    }
  ]
}
```

---

### PUT /api/v1/patients/{patientId}/claims/{claimId}

Update claim information (only if not sent).

**Path Parameters:**
- `patientId` (string, required): Patient numeric ID
- `claimId` (string, required): Claim ID

**Request Schema:**
```json
{
  "notes": "string | null",
  "icd10_codes": "string | null",
  "payment_info": {
    "check_number": "string | null",
    "bank_number": "string | null",
    "eob_number": "string | null"
  }
}
```

**Response Schema:** (Same as GET)

**Error Responses:**
- `400 Bad Request`: Invalid request data
- `403 Forbidden`: Claim already sent, cannot be modified
- `404 Not Found`: Claim not found

---

### POST /api/v1/patients/{patientId}/claims/{claimId}/send

Send claim to batch processing/insurance.

**Path Parameters:**
- `patientId` (string, required): Patient numeric ID
- `claimId` (string, required): Claim ID

**Request Schema:**
```json
{
  "batch_id": "string | null", // Optional: Specific batch ID, or null for auto-assignment
  "send_method": "string" // Required: "electronic", "paper", "fax"
}
```

**Response Schema:**
```json
{
  "claim_id": "string",
  "batch_id": "string",
  "status": "string", // "sent"
  "sent_date": "YYYY-MM-DD",
  "sent_time": "HH:mm:ss",
  "sent_by": "string",
  "send_method": "string"
}
```

**Error Responses:**
- `400 Bad Request`: Invalid request data
- `403 Forbidden`: Claim already sent or cannot be sent (missing required data)
- `404 Not Found`: Claim not found
- `422 Unprocessable Entity`: Validation errors (e.g., missing attachments, invalid claim data)

---

### GET /api/v1/patients/{patientId}/claims

Get list of claims for a patient.

**Path Parameters:**
- `patientId` (string, required): Patient numeric ID

**Query Parameters:**
- `status` (string, optional): Filter by status
- `limit` (integer, optional): Page size (default: 25)
- `offset` (integer, optional): Pagination offset (default: 0)

**Response Schema:**
```json
{
  "claims": [
    {
      "claim_id": "string",
      "claim_number": "string",
      "status": "string",
      "claim_type": "string",
      "date_of_service_from": "YYYY-MM-DD",
      "date_of_service_to": "YYYY-MM-DD",
      "total_fee": number,
      "total_est_insurance": number,
      "created_date": "YYYY-MM-DD",
      "created_by": "string"
    }
  ],
  "pagination": {
    "total": integer,
    "limit": integer,
    "offset": integer,
    "has_more": boolean
  }
}
```

---

## Payments

### POST /api/v1/patients/{patientId}/payments

Add a patient or insurance payment to the ledger.

**Path Parameters:**
- `patientId` (string, required): Patient numeric ID

**Request Schema:**
```json
{
  "payment_date": "YYYY-MM-DD", // Required
  "payment_amount": number, // Required: Positive amount
  "payment_type": "string", // Required: "patient" or "insurance"
  "payment_method": "string", // Required: Payment code (e.g., "H0007" for Check)
  "apply_to": "string", // Required: "P" (Patient) or "R" (Responsible Party)
  "provider_id": "string | null", // Optional: Provider ID if payment is for specific provider
  "procedure_ids": ["string"], // Optional: Array of procedure IDs to apply payment to
  "check_number": "string | null", // Optional: Check number
  "bank_number": "string | null", // Optional: Bank/routing number
  "notes": "string | null" // Optional: Payment notes
}
```

**Response Schema:**
```json
{
  "payment_id": "string",
  "ledger_entry_id": "string",
  "transaction_id": "string",
  "posted_date": "YYYY-MM-DD",
  "running_balance": number,
  "status": "string", // "posted"
  "created_at": "YYYY-MM-DDTHH:mm:ssZ"
}
```

**Error Responses:**
- `400 Bad Request`: Invalid request data, missing required fields
- `404 Not Found`: Patient, provider, or procedures not found
- `422 Unprocessable Entity`: Business rule violations (e.g., payment amount exceeds balance)
- `500 Internal Server Error`: Server error

---

### GET /api/v1/patients/{patientId}/payments/{paymentId}

Get payment details.

**Path Parameters:**
- `patientId` (string, required): Patient numeric ID
- `paymentId` (string, required): Payment ID

**Response Schema:**
```json
{
  "payment_id": "string",
  "payment_date": "YYYY-MM-DD",
  "payment_amount": number,
  "payment_type": "string",
  "payment_method": "string",
  "apply_to": "string",
  "provider_id": "string | null",
  "provider_name": "string | null",
  "procedure_ids": ["string"],
  "check_number": "string | null",
  "bank_number": "string | null",
  "notes": "string | null",
  "ledger_entry_id": "string",
  "created_by": "string",
  "created_at": "YYYY-MM-DDTHH:mm:ssZ"
}
```

---

## Adjustments

### POST /api/v1/patients/{patientId}/adjustments

Add an adjustment to the patient ledger.

**Path Parameters:**
- `patientId` (string, required): Patient numeric ID

**Request Schema:**
```json
{
  "adjustment_date": "YYYY-MM-DD", // Required
  "adjustment_amount": number, // Required: Negative amount (reduces balance)
  "adjustment_code": "string", // Required: Adjustment code (e.g., "ADJ01")
  "adjustment_reason": "string", // Required: Description/reason
  "apply_to": "string", // Required: "P" (Patient) or "R" (Responsible Party)
  "procedure_ids": ["string"], // Optional: Array of procedure IDs to apply adjustment to
  "notes": "string | null" // Optional: Adjustment notes
}
```

**Response Schema:**
```json
{
  "adjustment_id": "string",
  "ledger_entry_id": "string",
  "transaction_id": "string",
  "posted_date": "YYYY-MM-DD",
  "running_balance": number,
  "status": "string", // "posted"
  "created_at": "YYYY-MM-DDTHH:mm:ssZ"
}
```

**Error Responses:**
- `400 Bad Request`: Invalid request data, missing required fields
- `404 Not Found`: Patient or procedures not found
- `422 Unprocessable Entity`: Business rule violations
- `500 Internal Server Error`: Server error

---

### GET /api/v1/patients/{patientId}/adjustments/{adjustmentId}

Get adjustment details.

**Path Parameters:**
- `patientId` (string, required): Patient numeric ID
- `adjustmentId` (string, required): Adjustment ID

**Response Schema:**
```json
{
  "adjustment_id": "string",
  "adjustment_date": "YYYY-MM-DD",
  "adjustment_amount": number,
  "adjustment_code": "string",
  "adjustment_reason": "string",
  "apply_to": "string",
  "procedure_ids": ["string"],
  "notes": "string | null",
  "ledger_entry_id": "string",
  "created_by": "string",
  "created_at": "YYYY-MM-DDTHH:mm:ssZ"
}
```

---

## Metadata APIs

### GET /api/v1/metadata/procedure-codes

Get procedure codes with categories and requirements.

**Query Parameters:**
- `category` (string, optional): Filter by category
- `search` (string, optional): Search by code or description
- `limit` (integer, optional): Page size (default: 1000)

**Response Schema:**
```json
{
  "procedure_codes": [
    {
      "code": "string", // CDT code (e.g., "D0150")
      "user_code": "string | null", // Custom user code
      "description": "string",
      "category": "string", // e.g., "DIAGNOSTIC", "PREVENTIVE", etc.
      "requirements": {
        "tooth": boolean,
        "surface": boolean,
        "quadrant": boolean,
        "materials": boolean
      },
      "is_active": boolean
    }
  ],
  "categories": ["string"] // List of all available categories
}
```

---

### GET /api/v1/metadata/payment-codes

Get payment method codes.

**Response Schema:**
```json
{
  "payment_codes": [
    {
      "code": "string", // e.g., "H0007"
      "description": "string", // e.g., "PMT DST-Check"
      "type": "string", // "Cash", "Check", "Credit Card", "Debit Card", "E-Check", "Third-Party"
      "is_active": boolean
    }
  ]
}
```

---

### GET /api/v1/metadata/adjustment-codes

Get adjustment reason codes.

**Response Schema:**
```json
{
  "adjustment_codes": [
    {
      "code": "string", // e.g., "ADJ01"
      "description": "string", // e.g., "ADJ OFF - Courtesy Discount"
      "is_active": boolean
    }
  ]
}
```

---

### GET /api/v1/metadata/claim-statuses

Get available claim statuses.

**Response Schema:**
```json
{
  "claim_statuses": [
    {
      "code": "string", // e.g., "created", "sent", "paid"
      "display_name": "string", // e.g., "Claim Created, Not Sent"
      "description": "string | null"
    }
  ]
}
```

---

### GET /api/v1/metadata/transaction-types

Get available transaction types.

**Response Schema:**
```json
{
  "transaction_types": [
    {
      "code": "string", // e.g., "procedure", "patient_payment"
      "display_name": "string", // e.g., "Procedure"
      "description": "string | null"
    }
  ]
}
```

---

### GET /api/v1/offices/{officeId}/providers

Get providers for an office.

**Path Parameters:**
- `officeId` (string, required): Office ID

**Response Schema:**
```json
{
  "providers": [
    {
      "provider_id": "string",
      "provider_name": "string",
      "npi": "string | null",
      "is_active": boolean
    }
  ]
}
```

---

## Error Response Format

All error responses follow this format:

```json
{
  "error": {
    "code": "string", // Error code (e.g., "VALIDATION_ERROR", "NOT_FOUND")
    "message": "string", // Human-readable error message
    "details": {
      // Additional error details (field-specific errors, etc.)
    }
  }
}
```

**Common Error Codes:**
- `VALIDATION_ERROR`: Request validation failed
- `NOT_FOUND`: Resource not found
- `FORBIDDEN`: Operation not allowed (e.g., modifying sent claim)
- `BUSINESS_RULE_VIOLATION`: Business logic violation
- `INTERNAL_SERVER_ERROR`: Server error

---

## Notes

1. **Date Formats**: All dates use ISO 8601 format (YYYY-MM-DD for dates, YYYY-MM-DDTHH:mm:ssZ for timestamps)
2. **Amounts**: All monetary amounts are in decimal format (e.g., 123.45)
3. **IDs**: All IDs are strings (may be numeric strings)
4. **Pagination**: All list endpoints support pagination with `limit` and `offset`
5. **Authentication**: All endpoints require authentication (JWT token in Authorization header)
6. **Authorization**: Users must have appropriate permissions to access/modify patient data
