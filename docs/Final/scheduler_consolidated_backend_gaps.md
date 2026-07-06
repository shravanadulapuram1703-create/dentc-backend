# Scheduler Module — Consolidated Backend Gaps (for Backend Team)

**Owner:** Frontend • **Module:** Scheduler (`/scheduler`, `feature/phase_data_migration`)
**Scope:** every backend/API gap found while building the Scheduler to legacy (Denticon
*M03 — Understanding Appointments*) parity, plus the latest enhancement round
(provider colors, office-hours timeline, operator names, $ balance badge).

This is the single hand-off doc. It supersedes/rolls up:
- `scheduler_backend_devreport.md` (module-wide audit — mostly **resolved**)
- `scheduler_appointments_backend_devreport.md` (appointment-interaction gaps)

Each gap: **what the UI needs → what the backend exposes today → FE workaround → the ask.**
The FE degrades gracefully for every open item (nothing is silently dropped).

---

## Summary table

| ID | Priority | Gap | FE workaround today |
|----|----------|-----|---------------------|
| **G1** | P1 | Feed lacks per-block enrichment: `has_alert`, age/gender, services, **insurance eligibility** | daily fan-out over `/patient-alerts`; eligibility icon **not rendered** |
| **G2** | P1 | Feed lacks patient **account balance** ($ badge) | daily fan-out over `/patients/{id}/balance` |
| **G3** | P2 | Status PATCH accepts only `{status}` — **cancellation note / reason / call-list not persisted** | dialog collects data, logged only, **not saved** |
| **G4** | P2 | No **family / account same-day** appointments feed | Family section rendered empty |
| **G5** | P2 | No `created_by` / `updated_by` (user) on `AppointmentRead` | pop-out shows dates only, no user attribution |
| **G6** | P2 | No per-line **`est_patient`** (coordination-of-benefits) on appointment procedures | FE derives `max(fee − ins_est, 0)` — ignores 2° ins / write-offs |
| **G7** | P2 | No **per-provider / per-weekday working hours** (+ breaks) to drive column-level gray-out | gray-out uses the single office-level start/end for all columns |
| **G8** | P3 | No `posted_on` timestamp for the status-grid **Posted** cell | Posted cell blank |
| **G9** | P3 | No appointment **Print** report (routing slip / walkout / day sheet) endpoint | Print actions removed |
| **D1** | data | `appt_status` definitions unseeded (colors/order) | FE falls back to built-in S·C·U·L·R·A·O·H letters+colors |
| **D2** | data | Provider `scheduler_color` unset for most providers | FE falls back to a stable generated palette |

> **Confirmed already supported (no gap):** denormalized `patient_name`/`provider_name`/
> `operatory_name` on `GET /appointments/scheduler`; office `schedule_start_hour` /
> `schedule_end_hour` / `slot_interval_minutes` on `GET /offices/{id}`; provider
> `scheduler_color` field on `GET /providers`. These power operator names, the office-hours
> timeline, and provider colors respectively.

---

## P1 — removes N+1 fan-outs / unblocks a missing feature

### G1 — Denormalize per-block enrichment onto the scheduler feed
**UI (legacy M03 p.4/18):** each block shows patient **age/gender**, **attached services**, a
**medical-alert** red cross, and an **insurance-eligibility** icon (green = eligible / red = not /
gray = unknown). Hover reveals confirmation & same-day status, responsible-party type, preferred
language, lab tracking, new-patient placeholder.
**Today:** `AppointmentSchedulerRead` carries none of these — no `has_alert`, no age/gender, no
service summary, **no insurance eligibility**.
**FE workaround:** medical-alert badges come from a capped (≤40/day), daily-view-only, non-blocking
fan-out over `GET /patient-alerts?patient_id`. Age/gender + services show only in the on-demand
Details pop-out. **The insurance-eligibility icon is not rendered — no data source.**
**Ask:** add to `AppointmentSchedulerRead`: `has_alert: bool`, `patient_age: int`,
`patient_gender: str`, `service_summary: str` (or count), and
`insurance_eligibility: 'eligible'|'ineligible'|'unknown'|null`.

### G2 — Denormalize the patient account balance onto the feed
**UI:** a **$ badge** on each block when the patient owes a balance; the Details pop-out shows the
account / patient / insurance breakdown.
**Today:** balance is per-patient only via `GET /patients/{id}/balance` (`PatientBalance`); the feed
has no balance field.
**FE workaround:** capped, daily-view-only, non-blocking fan-out over `GET /patients/{id}/balance`
(batched with the G1 alerts call). The pop-out reuses the balance from `GET /patients/{id}/context`
(no extra call there).
**Ask:** add `account_balance` (and ideally `patient_balance`) to `AppointmentSchedulerRead`, **or**
a batch `GET /patients/balances?ids=`. Either removes the per-day fan-out.

---

## P2 — feature completeness / correctness

### G3 — Persist cancellation metadata (note / reason / call-list) + cancelled list
**UI (M03 p.16):** the Cancel dialog captures a **cancellation note**, an **Add to Call List** flag,
and a **cancellation reason** (Automated / Rescheduled / by email / by office / NOT rescheduled /
same day / No reason).
**Today:** `PATCH /appointments/{id}/status` accepts only `{status}`. No field persists the note,
reason, or call-list flag; there is no cancelled-appointments / call-list resource.
**FE workaround:** the dialog collects everything and logs it; **it is not saved**.
**Ask:** extend the status PATCH body (`cancellation_note`, `cancellation_reason`,
`add_to_call_list`), or add a dedicated cancel endpoint + a cancelled-appointments / call-list resource.

### G4 — Family / account same-day appointments feed
**UI:** the Details pop-out lists *"Family Appointment(s) for {date}"* — same-day appointments for
other members of the patient's account / responsible party.
**Today:** neither the feed nor `GET /appointments` can filter by responsible-party / account;
`AppointmentSchedulerRead` carries no responsible-party linkage.
**FE workaround:** the Family section renders empty (client-side resolution would be an N+1 over
every same-day appointment's patient context).
**Ask:** add `responsible_party_id` to the feed, or
`GET /appointments?responsible_party_id=&date=` (or `GET /patients/{id}/family-appointments?date=`).

### G5 — `created_by` / `updated_by` user on `AppointmentRead`
**UI:** the pop-out shows *"Created: (date) JENNYLMS   Modified: (date) PDDS4363"* — **who**
created/modified.
**Today:** `AppointmentRead` has `created_at` / `updated_at` timestamps but no user fields.
**FE workaround:** dates shown, user attribution omitted.
**Ask:** add `created_by` / `updated_by` (user id + resolved login/name).

### G6 — Per-line `est_patient` (coordination of benefits)
**UI:** the pop-out / edit grid shows an **Est. Pat.** per procedure and an appointment total.
**Today:** `AppointmentProcedureRead` has `fee` and `insurance_estimate` (strings) but no `est_patient`.
**FE workaround:** derives `est_patient = max(fee − insurance_estimate, 0)` per line — ignores
secondary insurance, write-offs, adjustments.
**Ask:** add computed `est_patient` per line (+ ideally `est_patient_total` per appointment) with
full COB logic.

### G7 — Per-provider / per-weekday working hours for column-level gray-out
**UI:** the calendar shows the full 24 h but **grays out + disables** slots outside working hours.
Legacy grays each provider/operatory **column** by that provider's own schedule (and breaks), and
the edit form has a per-provider **Short-Notice** availability grid (Mon–Fri × AM/PM).
**Today:** only a single office-level `schedule_start_hour` / `schedule_end_hour` exists. There is
**no** per-provider or per-weekday working-hours resource, and no break/lunch blocks. (Provider Setup
"Schedules" tab is a known gated area — no backing endpoint.)
**FE workaround:** the gray-out uses the one office-level start/end for **every** column; provider-
and weekday-specific hours/breaks are not reflected.
**Ask:** expose per-provider (and per-weekday) working hours + break blocks, e.g.
`GET /providers/{id}/schedules` or `GET /offices/{id}/hours?weekday=`, ideally surfaced per column on
the scheduler feed/config.

---

## P3 — nice to have

### G8 — `posted_on` timestamp
`AppointmentRead.is_posted` is a boolean only (and the feed omits `is_posted`). The status-grid
**Posted** cell is left blank. **Ask:** add `posted_on` to `AppointmentRead` and surface
`is_posted`/`posted_on` on the feed.

### G9 — Appointment Print / report endpoint
No backend report for routing slip / walkout / day sheet. Print actions are removed from the UI.
**Ask:** add an appointment/day report endpoint (server-rendered PDF or a structured payload the FE
can render).

---

## Data / seeding notes (not code gaps)

- **D1 — `appt_status` definitions:** seed `group_code = appt_status` with the ten legacy statuses
  (Scheduled, Confirmed, Unconfirmed, Left Message, In Reception, Available, In Operatory, Checked
  Out, Missed, Cancelled) + `color` + `sort_order`. The FE reads these automatically; until then it
  overlays built-in S·C·U·L·R·A·O·H letters/colors.
- **D2 — Provider `scheduler_color`:** the field exists on `GET /providers` but is `null` for most
  providers. Providers with a color set (e.g. `#e7081f`) render it exactly; the rest fall back to a
  stable generated palette. Seeding colors makes the scheduler match Provider Setup for everyone.

---

_Resolved in the earlier round (migration `a7b8c9d0e1f2`) and retained here for context: operatory
`provider_id`; `appt_status` colors/order plumbing; server-owned status PATCH; `GET
/patients/{id}/context`; the denormalized `GET /appointments/scheduler` feed (kills the per-cell
patient N+1); responsible-party / patient-type on `PatientRead`; office scoping. Only the items above
remain open._
