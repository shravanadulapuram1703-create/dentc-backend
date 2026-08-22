# Add / Edit Appointment — audit, fixes and backend gaps

Scope: the **ADD / EDIT APPOINTMENT** screen reached from the scheduler
(right-click a slot → Add Appointment → *Existing Patient* → search → SELECT, or
double-click an existing appointment).

Files: `src/components/modals/AddEditAppointmentForm.tsx`,
`src/components/modals/NewAppointmentModal.tsx`,
`src/components/modals/TxPlansTab.tsx`,
`src/components/modals/AppointmentProcedurePicker.tsx` (new),
`src/services/appointmentProceduresApi.ts` (new),
`src/services/schedulerApi.ts`.

---

## 1. Defects found and fixed (frontend)

| # | Symptom | Root cause | Fix |
|---|---------|-----------|-----|
| 1 | Birthdate blank / wrong; phones and e-mail wrong | The form was seeded only from the thin `PatientSearchResult`. The **edit** path seeded a placeholder shell — `birthdate: "01/01/1990"`, `phone: "(555) 000-0000"`, `ssn: "***-**-****"`, `chartNumber: "CH-001"` — that was never replaced. | The form now loads the real `PatientRead` (`GET /patients/{id}`) and drives Personal + Contact from it. The placeholder shell carries identity only. |
| 2 | E-mail always showed `john.smith@email.com` | `email: patient.email \|\| "john.smith@email.com"` — a hardcoded literal default. | Removed; the field renders the record's e-mail (blank when there is none). |
| 3 | Work / Home phone always blank | The search converter never mapped `work_phone` / `phone`; the form had no source for them. | Mapped: Cell ← `cell_phone`, Work ← `work_phone`, Home ← `phone` (there is no `home_phone` column). |
| 4 | Edits to e-mail / phones silently vanished | Contact values were only used when *creating* a new patient; for an existing patient nothing was written. | On save, changed demographics/contact are PATCHed to `/patients/{id}`. |
| 5 | Birthdate could never be supplied for a patient whose record has none | The field was `disabled` yet validation hard-required it → the appointment could not be saved at all. | Personal fields stay read-only when the record holds a value and become editable (amber border) when it does not; what is typed is written back to the patient. |
| 6 | **Wrong patient's** treatment plans / procedures | `patient.patientId` is the **chart_no**, not the backend id, and was passed to `fetchTreatmentPlans` and to `AddProcedure` as `patient_id`. Chart numbers collide with real ids (chart_no `818` belongs to *Rohit Gupta*, id `801`; patient id `818` is *Nino Esposito*). | Everything downstream now uses the resolved numeric id (`patient.numericId`, falling back to a `chart_no` lookup). |
| 7 | **Add Procedure** inserted a fixture | `handleAddTreatment` appended a hardcoded `D0120 "Periodic Oral Evaluation"`, tooth `1`, `$50`. | Opens `AppointmentProcedurePicker`: browse/search the full catalogue, satisfy the code's tooth/surface/quadrant/material requirements, pick the provider, price from the fee schedule. |
| 8 | Every procedure added to an appointment was **lost on save** | The form built a `treatments` array and passed it to `createAppointment`/`updateAppointment`, which never forwarded it — `AppointmentCreate`/`AppointmentUpdate` have no such field. | Lines persist to the real resource `/api/v1/appointment-procedures` (create / PATCH / DELETE reconciliation) after the appointment is saved, and load back when editing. |
| 9 | Tx Plans tree was always empty | `fetchTreatmentPlans` returned `phases: []` — plan items were never fetched. | Loads `/treatment-plan-items` per plan and groups by `phase_id` (falling back to `billing_order`). |
| 10 | Tx Plans **Add…** was a stub | `alert('Open Treatment Plan creation modal')`. | Runs the same flow as the patient's Treatment Plan screen: creates a real `treatment_plan_item` (creating the plan when the patient has none), priced by `resolveProcedureFee`. |
| 11 | Quick Add showed only ~200 of ~1,120 codes, and the category list was derived from that slice | `listProcedureCodes` caps `size` at 200 and the tab filters client-side. | Uses the shared paged+cached `loadProcedureCodes()` — 1,121 codes and 16 real categories. |
| 12 | Quick Add invented the estimates | `estPatient: defaultFee * 0.3`, `estInsurance: defaultFee * 0.7`. | Priced with `resolveProcedureFee` against the patient/office/provider fee schedule (e.g. D2391 → $92.00 from *Delta Dental Premier - Excel*). |
| 13 | "By Explosion Code" filter did nothing | Input was rendered with no state or handler. | Removed (there is no explosion-code concept on this backend — see gap **APPT-6**). |
| 14 | Treatments grid was mostly read-only | Only the provider cell was editable; TH/Surf/Duration/Fee/Status were static text. | Status, tooth, surface, bill-to, duration, provider, units and fee are all editable; est. patient re-derives from fee − est. insurance. |
| 15 | Missed / Cancelled checkboxes never reached the backend on **create** | `createAppointment` did not map them to `is_missed` / `is_cancelled`. | Mapped. |
| 16 | Deleted procedures reappeared | See gap **APPT-PROC-4** below. | Archived rows filtered client-side (also in the appointment details pop-out). |
| 17 | Search results showed every patient as living in the selected office | `office: currentOffice` was hardcoded on each row. | Shows the patient's own `home_office_code` / `home_office_name`. |
| 18 | Gender dropped when creating a patient from this screen | Only `"M"`/`"F"`/`"O"` were forwarded, but the backend stores free text (`"Male"`, `"Female"`). | Forwards whatever the record carries. |
| 19 | **A deleted appointment came back on the scheduler as soon as another appointment was created** | `DELETE /appointments/{id}` is a **soft** delete and the calendar feed still returns the row (gap **SCHED-DEL-1**). The delete handler only removed it from local state, so it vanished until the next refetch — which is exactly what creating an appointment triggers. | `fetchAppointments` now fetches the archived ids for the same range from `GET /appointments?is_archived=true` (in parallel with the feed) and subtracts them. Same subtraction applied to the Appointment Report; `is_archived: false` added to the other appointment list calls (dashboard KPIs, report metrics, lab tracking, patient overview, details pop-out "upcoming"). |

---

## 2. Backend gaps

### `appointment-procedures`

| ID | Gap | Impact | Ask |
|----|-----|--------|-----|
| **APPT-PROC-1** | No `duration` column on `AppointmentProcedureRead` / `Create`. | Per-procedure duration cannot be stored; **Calc Time** works only within a session, and reloading an appointment shows `0` unless the procedure code carries `default_duration_minutes`. | Add `duration_minutes` (nullable int). |
| **APPT-PROC-2** | No `provider_units` column. | The legacy "P. Units" column cannot be stored (always 1). | Add `provider_units` (int, default 1). |
| **APPT-PROC-3** | No `bill_to` column. | Patient-vs-insurance billing intent per line cannot be stored. | Add `bill_to` (`P`/`I`). |
| **APPT-PROC-4** | `DELETE /appointment-procedures/{id}` is a **soft** delete (sets `is_archived: true`) and `GET /appointment-procedures` has **no `is_archived` filter** and returns archived rows. | Removed procedures reappear on reload; every client must filter. Confirmed live: DELETE 10126 → 204, then the row still came back with `is_archived: true`. | Add an `is_archived` query filter (defaulting to `false`), as `/treatment-plan-items` already has. |

### Appointment

| ID | Gap | Impact | Ask |
|----|-----|--------|-----|
| **SCHED-DEL-1** | `DELETE /appointments/{id}` is a **soft** delete (returns 204, sets `is_archived: true`, row survives), but `GET /appointments/scheduler` **does not filter archived rows and `AppointmentSchedulerRead` does not even expose `is_archived`** — so the calendar feed hands deleted appointments straight back and the client has no field to filter on. `GET /appointments` *does* support `is_archived`, so the workaround is a second request per range to collect tombstone ids and subtract them. Verified live: after `DELETE APPT-8f908d24-…` → 204 and `is_archived: true`, `/appointments/scheduler` still returned the row; with two deleted plus one live appointment the feed returned **3** while `/appointments?is_archived=false` returned **1**. | Deleted appointments reappear on every refetch (creating another appointment, changing the date, reloading). Costs an extra list call per calendar fetch as a workaround, and every other consumer of the feed has the same defect. | Either (a) exclude archived rows from `/appointments/scheduler` by default, or (b) add an `is_archived` query param **and** expose `is_archived` on `AppointmentSchedulerRead`. (a) is preferred — it matches what every caller wants and removes the extra round-trip. |
| **SCHED-DEL-2** | There is no way to **restore** a soft-deleted appointment: `AppointmentUpdate` has `is_archived`, but nothing in the UI or API surfaces archived appointments to pick from. | Soft delete gives no user-visible benefit today; it only creates the reappearance bug. | Confirm whether soft delete is intentional. If it is, expose an "archived appointments" view/filter; if not, make DELETE a hard delete. |
| **APPT-5** | No `lab_dds` field on `AppointmentCreate`/`Update` (the read model has `lab_cost`, `lab_sent_on`, `lab_due_on`, `lab_received_on`). | The LAB section's **DDS** input cannot be saved. | Add `lab_dds`. |
| **APPT-6** | No "explosion code" concept (a legacy code that expands to a set of procedures). | The legacy "By Explosion Code" filter cannot be implemented; it has been removed from the UI. | Confirm whether this is in scope; if so, expose an explosion-code resource. |
| **APPT-7** | `campaign_id` is free text with no campaign resource to pick from. | The Campaign ID field is an unvalidated text box. | Expose a campaigns list, or confirm free text is intended. |

### Procedure codes

| ID | Gap | Impact | Ask |
|----|-----|--------|-----|
| **APPT-8** | `requires_tooth` / `requires_surface` / `requires_quadrant` / `requires_lab` are **`false` across the catalogue** (verified on D2391 "Resin Composite One Surface Posterior", which clinically requires both a tooth and a surface). | Tooth/surface enforcement can never fire automatically — the picker has to offer a manual "Edit" instead. | Seed the requirement flags from the ADA code set. |
| **APPT-9** | `default_fee` is `0.00` for most codes and `default_duration_minutes` is null. | Fees come entirely from fee schedules; codes with no schedule entry price at 0. Durations default to 30 min. | Seed defaults, or confirm fee schedules are the only intended source. |
| **APPT-10** | No `category` taxonomy endpoint; categories are derived by scanning all codes. | Requires loading the full catalogue to render category buttons. | Expose `GET /procedure-code-categories`. |

### Patients

| ID | Gap | Impact | Ask |
|----|-----|--------|-----|
| **APPT-11** | No `home_phone` column — `phone` doubles as the home number. | The three-phone legacy layout maps Home → `phone`. Documented, not blocking. | Confirm the mapping is intended. |
| **APPT-12** | `chart_no` is **not unique** (chart_no `818` is held by more than one patient). | A chart-number lookup can be ambiguous; only the numeric id is safe as a key. | Confirm whether chart_no should be unique per tenant. |

---

## 3. Live verification

Against local backend `127.0.0.1:8000`, frontend `:5173`, office `Excel Dental- Moon` (OFF-4).

* Patient **Ayaan, allu** (id 83862) — birthdate `01/03/2018`, e-mail and cell loaded from and written back to `/patients/83862`.
* Appointment `APPT-8f908d24-…` created with two procedure lines, then edited:
  * `D2391` tooth 19 / surface MO / fee `$92.00` (fee schedule "Delta Dental Premier - Excel").
  * `00170` carried `treatment_plan_id: 7a18c435-…` from the Tx Plans tree.
  * Deleting `00170` and adding `D0150` ($50.00) round-tripped correctly through `/appointment-procedures`.
* Tx Plans **Add…** created `treatment_plan_item` `9a03101b-…` (`D1110`, fee `$55.00`, `phase_id: 1`, `provider_id: PRV-180`).
* Quick Add lists **1,121** codes across **16** categories.

### Deleted-appointment regression (SCHED-DEL-1)

Reproduced and fixed on 2026-08-20, office OFF-4, date 2026-08-19:

1. `DELETE /appointments/APPT-8f908d24-…` → `204`; `GET` by id → `is_archived: true`;
   `GET /appointments/scheduler` → **still returns the row**.
2. Created `APPT-deltest-0001`, deleted it from the scheduler's right-click menu.
3. Created a third appointment through the UI (09:00).
4. Backend feed for that day now returns **3** rows; `?is_archived=false` returns **1**.
   The scheduler renders **1** block — the two deleted appointments no longer return
   after the post-create refetch.
