# Scheduler Module — Backend Implementation Notes (for the UI team)

> **Status:** Backend gaps addressed, persisted (`recondental_migrated`, Alembic `a7b8c9d0e1f2`),
> in `openapi.json`. **Regenerate Orval** (`npm run api:sync`).
> **Date:** 2026-06-02 · backend `/api/v1`.

---

## ✅ Backend changes shipped

### Gap 1 — Operatory → Provider
`operatories.provider_id` added; `OperatoryRead` now returns `provider_id` (nullable FK to providers).
Drop the `provider: ""` stub; resolve the provider name from the providers list, and wire
operatory-selection auto-fill from `operatory.provider_id`.

### Gap 4 — Appointment statuses + colors (backend-driven)
`definitions` gained `color` + `sort_order`; `DefinitionRead` exposes them. Seeded canonical groups
(`scripts/seed_account_definitions.py`):
- `GET /definitions?group_code=appt_status` → 10 statuses **with `color` + `sort_order`**
  (`key1` = code, `description` = label, `color` = hex, `sort_order` = order).
- `appt_type` and `procedure_type` groups also seeded.
Replace the hardcoded status array **and** `getStatusColor()` map with this response.

### Gap 5 — Status-transition timestamps are now **server-owned**
`PATCH /api/v1/appointments/{id}/status` body `{ "status": "Confirmed" }`. The server stamps
`confirmed_on` / `checked_in_on` / `checked_out_on` and sets `is_missed` / `is_cancelled` based on the
status, and returns the denormalized row. **Stop sending timestamps from the client.** (Status name
matching is lenient: "In Reception", "Checked Out", "No Show", etc. are normalized.)

### Gap 6 — Patient context aggregate
`GET /api/v1/patients/{id}/context` → `{ patient (PatientRead), balance, insurance[], visit{ first_visit, last_visit, next_recall } }`.
Replace the hardcoded `sessionStorage` patient object with this call (keyed by the numeric `patient_id`).

### Gap 7 / 9 — Denormalized calendar feed (kills the N+1)
`GET /api/v1/appointments/scheduler?date_from=&date_to=&office_id=` → **array** of appointments with
`patient_name` ("Last, First"), `provider_name`, `operatory_name` resolved server-side, plus status,
times, timestamps, `is_blocked`. Use this for day/week/month — **no `size<=200` cap** (it returns the
full range), so it doubles as the week/month fetch. Drop `resolvePatientNames` and the per-id fan-out.

### Gap 8 — Responsible party + patient type
`patients.responsible_party_id` and `patients.patient_type` added; both on `PatientRead`. Bind the real
fields; remove the `respId: "R-001"` / `patientType: "General"` placeholders.

---

## ℹ️ Frontend-only / confirmations (no backend change)

- **Gap 2 (office scoping):** `operatories`/`providers` list endpoints already accept `office_id` — thread
  it through. **`definitions` is tenant-scoped and has no `office_id`** — do **not** send that param
  (it would be ignored). Scheduler config = `GET /api/v1/offices/{office_id}`
  (`slot_interval_minutes`, `schedule_start_hour`, `schedule_end_hour`). Build the `"OFF-1" → 1` extractor FE-side.
- **Gap 3 (new patient mid-scheduling):** `AppointmentCreate.patient_id` is `number | null`.
  `null` = a **blocked/!patient slot** (intentional). New patient = **two-step**: `POST /patients` →
  take the numeric `id` → `POST /appointments` with `patient_id: number`. We did **not** add a nested
  patient-create on the appointment endpoint; stop sending `"NEW"`/`chart_no` as `patient_id` (it 422s).
- **Gap 9 (week/month range):** generic `GET /appointments?date_from&date_to` works but is capped at
  `size<=200`. Prefer the new `/appointments/scheduler` feed for ranges (uncapped).
- **Gap 10 (procedure_label):** intentionally **free-text** (no FK). Options come from
  `GET /definitions?group_code=procedure_type` (seeded). Send the label; no server-side validation.
- **Gap 11 (cut/copy/paste/reschedule/print):** reschedule = `PATCH /appointments/{id}` (date/time/op);
  cut/copy/paste are client-side. **Print (routing slip / walkout report) is NOT built** — there is no
  report/PDF generation backend yet. Gate those buttons or send us the report specs to build
  `POST /reports/...` in a later pass.

---

## ⚠️ Notes / assumptions
- `/appointments/scheduler` returns a **plain JSON array** (a bounded calendar feed), not the
  `{ items, meta }` envelope. If you need pagination for very large ranges, tell us and we'll wrap it.
- Status timestamps are **server-owned** — treat `confirmed_on`/`checked_in_on`/`checked_out_on` as
  read-only on the client.
- `patient_access_level`/login-restriction style enforcement is out of scope here; these scheduler
  fields are data only.

## Operation ids (Orval)
`list_scheduler_appointments`, `update_appointment_status`, `get_patient_context`; plus the existing
`list_operatories`/`get_operatory` (now with `provider_id`), `list_definitions` (now with `color`/`sort_order`),
and `list_patients`/`get_patient` (now with `responsible_party_id`/`patient_type`).
