# Lab Tracking (M12) — Backend Gap Report

**Re-verified live: 2026-09-11** against the local backend (`127.0.0.1:8000`, alembic head
`9de6ac649cba`, migration `f0a1b2c3d4e5` applied). Probe patient: 83700 "Udayk, Paloju",
appointment `APPT-5512fa4c-822f-4f69-9f96-8539da835e82`. All probe writes were reverted;
the one appointment created for the POST probe (`APPT-LABPROBE-0001`) was DELETEd (soft →
`is_archived=true`, see LAB-11).

Frontend surfaces covered:

- **Add / Edit Appointment → LAB section** (`src/components/modals/AddEditAppointmentForm.tsx`,
  `src/services/schedulerApi.ts`): Lab ✓ · DDS · Lab Cost · Sent On · Due On · Recvd On.
- **Patient → Lab Tracking tab** (`src/features/lab-tracking/**`, `/patient/:id/lab-tracking`):
  Lab (vendor) · Lab Cost · Short Notice · Sent on · Due on · Recvd. on · Check-in · Lab Report ·
  Cost Report.

## 1. How lab data maps to the backend

There is **no lab-case resource**. A lab case is an **appointment** with lab fields. The
columns live on `appointments` and are exposed on `AppointmentRead` / `AppointmentCreate` /
`AppointmentUpdate`:

| Backend field       | Type (schema)                 | DB column           | Legacy control (appointment) | Legacy control (Lab Tracking) |
| ------------------- | ----------------------------- | ------------------- | ---------------------------- | ----------------------------- |
| `has_lab`           | bool                          | `Boolean`           | "Lab" checkbox               | (implicit: row exists)        |
| `lab_dds`           | string \| null (no max_length) | `String(100)`       | "DDS"                        | — (see LAB-1)                 |
| `lab_cost`          | number \| decimal-string \| null | `Numeric(10,2)`  | "Lab Cost"                   | "Lab Cost"                    |
| `lab_sent_on`       | date \| null                  | `Date`              | "Sent On"                    | "Sent on"                     |
| `lab_due_on`        | date \| null                  | `Date`              | "Due On"                     | "Due on"                      |
| `lab_received_on`   | date \| null                  | `Date`              | "Recvd On"                   | "Recvd. on"                   |

Not on the backend at all: **lab vendor** (the lab company) and **Short Notice**.
`procedure_codes.requires_lab` exists but is advisory only (`procedure_rules_service.py`).

Lab **status** (Not Sent / Sent / Overdue / Received) is not stored; the frontend derives it
from the three dates.

## 2. What was verified to work (no gap)

| Probe                                                     | Result                                                        |
| --------------------------------------------------------- | ------------------------------------------------------------- |
| `POST /appointments` with all six lab fields              | **201**, all six echoed and persisted on GET                  |
| `PATCH /appointments/{id}` `lab_dds`, `lab_cost`, 3 dates | **200**, persisted on GET                                     |
| `lab_cost: 123.456` (number)                              | 200, stored as `"123.46"` (rounded to 2 dp — acceptable)      |
| `lab_cost: "100.00"` (string)                             | 200                                                           |
| `lab_dds: null` (clear)                                   | 200, cleared                                                  |

**APPT-5 (`lab_dds` missing on create/update) is RESOLVED on the backend.** The reason the DDS
box still came back blank in the UI was a **frontend** bug: `schedulerApi.ts` never mapped
`lab_dds` in the read mapper, the create body or the update patch (the form sent it, the
service dropped it). Fixed in this session — see §5.

## 3. Gaps (backend)

Severity: **High** = data loss / user-visible failure, **Medium** = incorrect-but-recoverable,
**Low** = parity / polish.

### LAB-1 — No lab-vendor field and no Short Notice flag on the appointment  · **High**
Legacy Lab Tracking (M12) records **which lab** the case went to (vendor, e.g. "Creative
Dental") and a **Short Notice** flag. Neither exists on `appointments`:

- `lab_dds` (added by `f0a1b2c3d4e5`) is documented in the model as *"the dentist the lab
  case is for — free text"*, i.e. a DDS name, **not** the lab vendor. It is the only
  free-text lab identity column, so today the UI has to choose between mis-using it as
  the vendor or leaving the vendor unsaved (current behaviour: unsaved, flagged
  "· not saved").
- A `PATCH` carrying `short_notice` / `lab_short_notice` returns **200 and silently drops
  the keys** (see LAB-10) — nothing is stored.
- There is no vendor catalog: `GET /definitions?group_code=LAB` returns **0 rows**, no
  `LAB*` definition group exists, and there is no `/labs` resource.

**Ask:**
1. Add `lab_vendor_id` (FK) + a `labs` catalog (name, phone, address, is_active, tenant/office)
   **or** at minimum a `lab_vendor` `String(100)` + a seeded `LAB` definitions group.
2. Add `lab_short_notice: bool` (default false).
3. Confirm the intended semantics of `lab_dds` (dentist vs vendor) so the two screens can be
   bound consistently.

### LAB-2 — No lab filters on `GET /api/v1/appointments`  · **Medium**
List params are `patient_id, provider_id, operatory_id, office_id, date, status,
is_archived, date_from, date_to, search, page, size, sort, order`. `has_lab` is **silently
ignored** (verified: `?has_lab=false` still returns the `has_lab=true` row). The Lab Tracking
tab pages every appointment for the patient (size cap 200) and filters client-side.
**Ask:** accept `has_lab`, `lab_sent_from/to`, `lab_due_from/to`, `lab_received_from/to`,
and a `lab_status` (`not_sent|sent|overdue|received`) filter, or expose a
`GET /appointments/lab-cases` view.

### LAB-3 — Scheduler feed omits every lab field  · **Low**
`GET /appointments/scheduler` (`AppointmentSchedulerRead`) carries `patient_name`,
`provider_name`, `operatory_name` … but **none** of `has_lab, lab_dds, lab_cost,
lab_sent_on, lab_due_on, lab_received_on` (verified key list). `AppointmentRead` has the lab
fields but no denormalized names, so the tab resolves provider names from `/providers`.
**Ask:** add the six lab fields to `AppointmentSchedulerRead` (lets the scheduler show a
"lab" badge and lets Lab Tracking reuse the denormalized feed).

### LAB-4 — No lab report / cost aggregation / export endpoints  · **Low**
Legacy Lab Report (Not Sent / Not Received / Due) and Lab Cost Report (totals by date range)
are generated client-side with jsPDF from in-memory rows. No server aggregation or
PDF/Excel export exists.

### LAB-5 — Office-wide (cross-patient) lab tracking not possible  · **Medium**
Blocked on LAB-2: without a server-side `has_lab` filter an office-wide view would have to
page the entire appointment book.

### LAB-6 — `lab_dds` longer than 100 chars → HTTP **500**  · **High**
`AppointmentUpdate.lab_dds` has no `max_length`; the DB column is `String(100)`. A 150-char
value fails in the DB layer and surfaces as
`{"error":{"code":"internal_error","message":"An unexpected error occurred"}}`.
**Ask:** `Field(max_length=100)` on Create/Update (→ 422 with the field name).

### LAB-7 — `lab_cost` not validated: overflow → 500, negatives accepted  · **High**
- `lab_cost: "123456789.00"` (exceeds `Numeric(10,2)`) → **500** internal error.
- `lab_cost: -5` → **200**, stored `"-5.00"`.
- `lab_cost: ""` and `"1,000.00"` → **422** `decimal_parsing` (fine, but the frontend must
  send `null`, never `""`).
**Ask:** `ge=0`, `max_digits=10, decimal_places=2` on the schema so bad input is a 422.

### LAB-8 — `has_lab=false` neither clears nor rejects the other lab fields  · **Medium**
- `PATCH {"has_lab": false}` → 200; `lab_dds/lab_cost/dates` are **left intact**.
- `PATCH {"has_lab": false, "lab_sent_on": "2026-09-11"}` → 200, date stored.
Result: orphaned lab data that the Lab Tracking tab can no longer see (it filters on
`has_lab`) but that reappears the moment the checkbox is re-ticked, and that the scheduler
form still shows. **Ask:** pick one contract and enforce it server-side — either null the
five lab fields when `has_lab` flips to false, or reject lab fields when `has_lab` is false
(422), or derive `has_lab` from the presence of lab data.

### LAB-9 — No date-order validation on the three lab dates  · **Low**
`lab_sent_on=2026-09-20, lab_due_on=2026-09-10, lab_received_on=2026-09-01` → **200**.
Received-before-sent and due-before-sent are accepted. Frontend status derivation
(`received → overdue → sent → not_sent`) copes, but reports will show nonsense intervals.
**Ask:** 422 when `lab_received_on < lab_sent_on` or `lab_due_on < lab_sent_on`.

### LAB-10 — Unknown body keys are silently accepted (200)  · **Medium**
`PATCH` with `short_notice`, `lab_short_notice` (and any other unknown key) returns 200 and
drops them. The frontend cannot detect an unsupported field from the response; this is the
same behaviour as PROC-7 on procedure codes. **Ask:** `model_config = ConfigDict(extra="forbid")`
on `AppointmentCreate/Update` (or at least return the ignored keys in a warning header).

### LAB-11 — DELETE is a soft archive; archived lab cases keep `has_lab`  · **Low**
`DELETE /appointments/{id}` → 204, then `GET` still returns the row with
`is_archived=true`, `has_lab=true`, `status="Scheduled"`. Lab Tracking passes
`is_archived=false` so archived cases are hidden; any consumer that forgets the flag will
count them. **Ask:** either exclude archived rows by default on the list endpoint or
document `is_archived=false` as mandatory.

## 4. Summary table

| ID     | Gap                                                       | Severity | Status (2026-09-11)                          |
| ------ | --------------------------------------------------------- | -------- | -------------------------------------------- |
| APPT-5 | `lab_dds` missing on create/update                        | —        | **Resolved** (migration `f0a1b2c3d4e5`); FE mapping fixed |
| LAB-1  | No lab vendor / Short Notice field; no vendor catalog     | High     | Open                                         |
| LAB-2  | No `has_lab` / lab-date filters on list                   | Medium   | Open (`has_lab` param silently ignored)      |
| LAB-3  | Scheduler feed drops all lab fields                       | Low      | Open                                         |
| LAB-4  | No report / export endpoints                              | Low      | Open                                         |
| LAB-5  | Office-wide lab tracking                                  | Medium   | Blocked on LAB-2                             |
| LAB-6  | `lab_dds` > 100 chars → 500                               | High     | Open                                         |
| LAB-7  | `lab_cost` overflow → 500; negative accepted              | High     | Open                                         |
| LAB-8  | `has_lab=false` leaves orphaned lab data                  | Medium   | Open                                         |
| LAB-9  | No lab-date ordering validation                           | Low      | Open                                         |
| LAB-10 | Unknown keys silently dropped (200)                       | Medium   | Open                                         |
| LAB-11 | Soft-deleted lab cases still returned                     | Low      | Open (FE passes `is_archived=false`)         |

## 5. Frontend status (for context, not backend asks)

- **Fixed 2026-09-11:** `src/services/schedulerApi.ts` now maps `lab_dds` in `mapAppointment`,
  `createAppointment` and `updateAppointment`. The Add/Edit Appointment DDS box now saves and
  reloads.
- **Known FE limitation (follow-up):** the Add/Edit Appointment form builds its payload with
  `value || undefined`, and `undefined` keys are stripped before PATCH, so a DDS / cost / date
  that was previously saved **cannot be cleared** from that form (the Lab Tracking tab sends
  explicit `null` and can). Independent of the backend.
- Lab Tracking "Lab" (vendor) and "Short Notice" remain display-only and flagged
  "· not saved" until LAB-1 lands.
