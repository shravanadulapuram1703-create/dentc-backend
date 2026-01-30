# Scheduler Module

This module implements the backend for the Scheduler functionality, following the frontend expectations document exactly.

## Structure

```
scheduler/
├── __init__.py          # Module initialization
├── models.py            # SQLAlchemy database models
├── schemas.py           # Pydantic request/response schemas
├── services.py          # Business logic layer
├── routes.py            # FastAPI route handlers
├── sql/
│   └── create_scheduler_tables.sql  # Database schema SQL script
└── README.md            # This file
```

## Features

- **Appointments Management**: Full CRUD operations for appointments
- **Operatories**: Manage dental operatories/rooms
- **Providers**: Manage dental providers (doctors, hygienists, etc.)
- **Procedure Types**: Manage procedure types with color coding
- **Scheduler Configuration**: Office-specific scheduler settings (working hours, slot intervals)

## API Endpoints

All endpoints are prefixed with `/api/v1/scheduler`.

### Appointments

- `GET /appointments` - Fetch appointments for a date range
- `GET /appointments/{appointment_id}` - Get single appointment
- `POST /appointments` - Create new appointment
- `PUT /appointments/{appointment_id}` - Update appointment
- `PATCH /appointments/{appointment_id}/status` - Update appointment status only
- `DELETE /appointments/{appointment_id}` - Delete appointment

### Operatories

- `GET /operatories` - Fetch all operatories

### Providers

- `GET /providers` - Fetch all providers

### Procedure Types

- `GET /procedure-types` - Fetch all procedure types

### Configuration

- `GET /config` - Fetch scheduler configuration

## Database Setup

1. Run the SQL script to create all necessary tables:

```bash
psql -U your_user -d your_database -f app/api/v1/scheduler/sql/create_scheduler_tables.sql
```

Or execute the SQL file directly in your PostgreSQL client.

2. The script creates:
   - `scheduler_appointments` table
   - `scheduler_operatories` table
   - `scheduler_providers` table
   - `scheduler_procedure_types` table
   - `scheduler_config` table
   - `appointment_status_enum` type

## Key Features

### Appointment Overlap Detection

The service layer automatically checks for appointment overlaps when creating or updating appointments. Appointments are considered overlapping if:
- They are for the same operatory
- They are on the same date
- Their time ranges overlap
- They are not cancelled or missed

### Patient Name Resolution

When creating or updating appointments, the backend automatically fetches the patient name from the patient database and formats it as "LastName, FirstName".

### End Time Calculation

The backend automatically calculates `end_time` from `start_time + duration` to ensure consistency.

### Office-Based Filtering

All endpoints support office-based filtering for multi-tenant support. If `office_id` is not provided, the system uses the authenticated user's office.

## Status Enum

Appointments support the following statuses:
- Scheduled
- Confirmed
- Unconfirmed
- Left Message
- In Reception
- Available
- In Operatory
- Checked Out
- Missed
- Cancelled

## Response Format

All endpoints follow the frontend expectations document exactly:

```json
{
  "appointments": [...],
  "operatories": [...],
  "providers": [...],
  "procedure_types": [...],
  "config": {...}
}
```

## Error Handling

Errors follow FastAPI standard format:

```json
{
  "detail": "Error message",
  "status_code": 400
}
```

## Authentication

All endpoints require authentication via Bearer token. The `get_current_user` dependency is used to authenticate requests.

## Notes

- The scheduler module uses separate models from the existing `appointments` model to maintain separation of concerns
- Patient IDs are stored as strings to support chart numbers
- Operatory and Provider IDs are strings (e.g., "OP1", "PROV001")
- All timestamps are stored in UTC
