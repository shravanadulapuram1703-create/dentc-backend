# Patients API Documentation

## Overview

Lightweight Patients API for quick patient creation and search during appointment scheduling. This module provides essential patient management functionality that will be extended later.

## Base URL

All endpoints are prefixed with `/api/v1/patients`

## Authentication

All endpoints require authentication via Bearer token.

---

## API Endpoints

### 1. Create Patient

**Endpoint:** `POST /api/v1/patients`

**Description:** Create a new patient. Chart number is auto-generated if not provided.

**Request Body (camelCase):**

```json
{
  "firstName": "John",
  "lastName": "Doe",
  "chartNo": "CH001",           // Optional - auto-generated if not provided
  "dob": "1990-01-15",          // Optional - YYYY-MM-DD format
  "gender": "M",                // Optional - M, F, or O
  "phone": "555-1234",          // Optional
  "email": "john.doe@example.com", // Optional
  "homeOfficeId": 1             // Optional
}
```

**Success Response (201 Created):**

```json
{
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
  "updatedAt": null
}
```

**Error Responses:**

- **409 Conflict:** Chart number already exists
  ```json
  {
    "detail": "Patient with chart number 'CH001' already exists"
  }
  ```

- **422 Unprocessable Entity:** Validation error
  ```json
  {
    "detail": [
      {
        "loc": ["body", "firstName"],
        "msg": "field required",
        "type": "value_error.missing"
      }
    ]
  }
  ```

---

### 2. Get Patient List

**Endpoint:** `GET /api/v1/patients`

**Description:** Get a list of patients with optional search and pagination.

**Query Parameters:**

- `search` (optional): Search term that searches in:
  - First name
  - Last name
  - Chart number
  - Phone number
  - Email address
- `limit` (optional, default: 100): Maximum number of results (1-1000)
- `offset` (optional, default: 0): Number of results to skip for pagination

**Example Requests:**

```
GET /api/v1/patients
GET /api/v1/patients?search=John
GET /api/v1/patients?search=John&limit=50&offset=0
GET /api/v1/patients?limit=20
```

**Success Response (200 OK):**

```json
{
  "patients": [
    {
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
      "updatedAt": null
    },
    {
      "id": 2,
      "chartNo": "CH002",
      "firstName": "Jane",
      "lastName": "Smith",
      "dob": "1985-05-20",
      "gender": "F",
      "phone": "555-5678",
      "email": "jane.smith@example.com",
      "homeOfficeId": 1,
      "createdAt": "2024-01-02T10:00:00",
      "updatedAt": null
    }
  ],
  "total": 2
}
```

**Notes:**
- Results are ordered by creation date (most recent first)
- Search is case-insensitive and uses partial matching
- If no search term is provided, returns all patients (paginated)

---

### 3. Get Patient by ID

**Endpoint:** `GET /api/v1/patients/{patient_id}`

**Description:** Get a single patient by ID.

**Path Parameters:**
- `patient_id` (required): Patient ID (integer)

**Example Request:**

```
GET /api/v1/patients/1
```

**Success Response (200 OK):**

```json
{
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
  "updatedAt": null
}
```

**Error Response (404 Not Found):**

```json
{
  "detail": "Patient not found"
}
```

---

### 4. Get Patient by Chart Number

**Endpoint:** `GET /api/v1/patients/chart/{chart_no}`

**Description:** Get a patient by chart number.

**Path Parameters:**
- `chart_no` (required): Patient chart number (string)

**Example Request:**

```
GET /api/v1/patients/chart/CH001
```

**Success Response (200 OK):**

Same as Get Patient by ID.

**Error Response (404 Not Found):**

```json
{
  "detail": "Patient with chart number 'CH001' not found"
}
```

---

### 5. Update Patient

**Endpoint:** `PUT /api/v1/patients/{patient_id}`

**Description:** Update an existing patient. All fields are optional.

**Path Parameters:**
- `patient_id` (required): Patient ID (integer)

**Request Body (all fields optional):**

```json
{
  "first_name": "John",
  "last_name": "Doe",
  "dob": "1990-01-15",
  "gender": "M",
  "phone": "555-1234",
  "email": "john.doe@example.com",
  "home_office_id": 1
}
```

**Success Response (200 OK):**

Same as Get Patient by ID (with updated fields).

**Error Response (404 Not Found):**

```json
{
  "detail": "Patient not found"
}
```

---

### 6. Delete Patient

**Endpoint:** `DELETE /api/v1/patients/{patient_id}`

**Description:** Delete a patient.

**Path Parameters:**
- `patient_id` (required): Patient ID (integer)

**Success Response (200 OK):**

```json
{
  "message": "Patient deleted successfully",
  "status": "success"
}
```

**Error Response (404 Not Found):**

```json
{
  "detail": "Patient not found"
}
```

---

## Chart Number Auto-Generation

If `chartNo` is not provided when creating a patient, the system automatically generates one in the format:

- Format: `CH` + 3-digit number (e.g., `CH001`, `CH002`, `CH003`)
- The system finds the highest existing chart number and increments it
- Ensures uniqueness even if there are gaps in the sequence

**Example:**
- If the last patient has chart number `CH005`, the next patient will get `CH006`
- If no patients exist, the first patient gets `CH001`

---

## Field Validation

### Required Fields (Create)
- `firstName`: String, 1-100 characters
- `lastName`: String, 1-100 characters

### Optional Fields
- `chartNo`: String, max 50 characters, must be unique
- `dob`: Date in YYYY-MM-DD format
- `gender`: Single character (M/F/O)
- `phone`: String, max 20 characters
- `email`: Valid email address
- `homeOfficeId`: Integer

---

## Integration with Scheduler

When creating an appointment for a new patient:

1. **Create the patient first:**
   ```javascript
   POST /api/v1/patients
   {
     "firstName": "John",
     "lastName": "Doe",
     // ... other fields
   }
   ```

2. **Use the returned patient ID or chartNo in the appointment:**
   ```javascript
   POST /api/v1/scheduler/appointments
   {
     "patientId": "CH001",  // or use the chartNo from patient creation
     // ... other appointment fields
   }
   ```

---

## Error Handling

All endpoints return standard FastAPI error responses:

**400 Bad Request:**
```json
{
  "detail": "Validation error message"
}
```

**404 Not Found:**
```json
{
  "detail": "Patient not found"
}
```

**409 Conflict:**
```json
{
  "detail": "Patient with chart number 'CH001' already exists"
}
```

**422 Unprocessable Entity:**
```json
{
  "detail": [
    {
      "loc": ["body", "field_name"],
      "msg": "error message",
      "type": "error_type"
    }
  ]
}
```

**500 Internal Server Error:**
```json
{
  "detail": "Internal server error message"
}
```

---

## Testing Examples

### Create a Patient

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/patients" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "firstName": "John",
    "lastName": "Doe",
    "dob": "1990-01-15",
    "gender": "M",
    "phone": "555-1234",
    "email": "john.doe@example.com"
  }'
```

### Search Patients

```bash
curl -X GET "http://127.0.0.1:8000/api/v1/patients?search=John&limit=10" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Get Patient by ID

```bash
curl -X GET "http://127.0.0.1:8000/api/v1/patients/1" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Notes

- All timestamps are returned in ISO 8601 format
- Chart numbers are case-sensitive
- Search is case-insensitive and uses partial matching (LIKE query)
- The module uses the `tenant_1` schema for data storage
- All endpoints require authentication
