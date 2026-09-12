# Treatment Plan → New Appointment — Backend Gaps Report

> **Audience:** Backend team
> **Module:** Treatment Plan "New Appt" → Scheduler → Add/Edit Appointment (also Restorative Chart "New Appt." and Patient Overview "Add New Appt")
> **Date:** 2026-09-09 (live audit against the local backend, patient 1002 / plan `8f26f012-0840-4828-8151-239218780029`)
> **Frontend fix shipped:** `src/services/schedulerHandoff.ts` + `Scheduler.tsx` / `NewAppointmentModal.tsx` / `AddEditAppointmentForm.tsx` / `TreatmentPlanPage.tsx` / `RestorativeChart.tsx` / `AppointmentsPanel.tsx`

---

## 1. The bug that was reported (frontend, fixed)

Steps: open Tx plan → select a procedure → **New Appt** → pick an open slot.
Expected: appointment created for the patient with the selected procedure(s).
Actual: the appointment had no patient and no procedures.

Root cause was entirely frontend: every "New Appt" button did a bare `navigate('/scheduler')`, so the scheduler opened cold and the New Appointment modal asked "Who is this appointment for?" again. There was no channel for "book for this patient with these plan items".

**What the frontend does now**

| Step | Behaviour |
|------|-----------|
| Tx Plan **New Appt** | Sends `{ patient_id, patient_name, plan_item_ids (selected, non-completed rows), provider_id (first selected row's provider → entry panel's provider), source }` to `/scheduler` via router state. |
| Scheduler | Holds it as a **pending booking** banner ("Booking for *Last, First* · N planned procedures — click an open slot"), consumes the router state (refresh/back cannot re-arm it), clears on successful save or Dismiss. |
| Slot click / NEW APPOINTMENT | `NewAppointmentModal` skips the chooser, loads the patient (`GET /patients/{id}`), and forwards `plan_item_ids` + `provider_id`. |
| Add/Edit Appointment form | Provider = the plan item's provider (**not** the operatory's assigned provider). Operatory = the clicked slot's operatory, else the first operatory whose `provider_id` matches, else the office default. TREATMENTS grid is seeded from the matching `treatment_plan_items` once the plans load (status `TP`, tooth/surface/fee/estimates, `treatment_plan_id` link). |
| Save | `POST /appointments` then one `POST /appointment-procedures` per line (existing sync). |

Verified live: appointment `APPT-7100447c-e7f4-44cc-a0fc-ef64c37a1067` → `patient_id 1002`, one procedure row `10131` (`D2740`, tooth 14, `TP`, `treatment_plan_id 8f26f012…`).

---

## 2. Backend gaps found on this path

Severity as used in `docs/CONSOLIDATED_BACKEND_GAPS.md`.

| Gap ID | Title | What we saw | Frontend workaround today | Ask | Severity |
|--------|-------|-------------|---------------------------|-----|----------|
| **PLAN-APPT-1** | **Booking a plan item does not mark it `scheduled`** | After the appointment + its `appointment_procedures` row (with `treatment_plan_id`) were created, `GET /treatment-plan-items/37093a0c…` still returns `status: "diagnosed"`. The Tx Plan grid keeps showing **D** (diagnosed) for a procedure that now has an appointment; legacy shows **S**. | None — the item status is left untouched (the FE could PATCH `status: "scheduled"` per item, but see PLAN-APPT-2: it has no reliable way to *un*-schedule when the appointment is cancelled/deleted). | On `POST /appointment-procedures` with a plan link, set the item to `scheduled`; on delete/cancel of the appointment, revert to the prior status. Requires PLAN-20 (enum has no `scheduled`). | High |
| **PLAN-APPT-2** | **`appointment_procedures` links the *plan*, not the *item*** | `AppointmentProcedureCreate/Read` carry `treatment_plan_id` only. Two items with the same code/tooth on one plan (or a re-planned procedure) cannot be told apart, and nothing on `TreatmentPlanItemRead` points back to an appointment (`appointment_id` / `scheduled_appointment_id` do not exist — both came back absent). | The FE seeds lines from item ids it was handed, then drops the item id on save (there is no column for it). Reconciliation elsewhere is by `code|tooth|surface`. | Add `treatment_plan_item_id` to `appointment_procedures` and expose `appointment_id` (or a list) on `TreatmentPlanItemRead`. | High |
| **PLAN-APPT-3** | **Plan items have no provider on legacy-migrated rows** | Both items on plan `8f26f012…` had `provider_id: null` **and** `diagnosed_by: null`, so "the provider chosen on the treatment plan" does not exist for migrated data and the appointment cannot default to it. | FE falls back: item `provider_id` → `diagnosed_by` → entry-panel provider → operatory's provider → first provider. | Backfill `provider_id` from the legacy plan rows (diagnosing provider) and make it required on create (`TreatmentPlanItemCreate.provider_id`). | Medium |
| **PLAN-APPT-4** | **No provider → operatory mapping** | Only `OperatoryRead.provider_id` exists (operatory → one provider). There is no `default_operatory_id` on `ProviderRead`, and in office 1 **all five operatories have `provider_id: null`**, so "select the provider's operatory by default" has nothing to key on. | FE scans the office's operatories for the first one whose `provider_id` equals the plan provider; when none matches it keeps the clicked slot / office default operatory. | Seed `operatories.provider_id` for real data, and/or add `ProviderRead.default_operatory_id` (per office). | Medium |
| **PLAN-APPT-5** | **No atomic "book from plan" endpoint** | Booking is `POST /appointments` followed by N × `POST /appointment-procedures`. A failure on any line leaves an appointment with partial or no procedures (the form warns, nothing rolls back). | Sequential calls + a warning alert on partial failure. | `POST /appointments` accepting `procedures: [...]` (or `POST /treatment-plans/{id}/book` taking item ids + slot) in one transaction. | Medium |
| **PLAN-APPT-6** | **Providers are not office-scoped (dup of NA-B6 / SCHED-2)** | The plan provider is `PRV-100` (office 1) but `GET /providers?office_id=` is unreliable, so the appointment form's provider list is the tenant-wide list; a plan provider from another office still binds but renders by id. | Full-provider fallback (see NA-B6). | Fix office scoping. | Low (tracked) |
| **PLAN-APPT-7** | **Plan item has no `duration_minutes` (dup of PLAN-19 / APPT-PROC-1)** | Seeded lines take the procedure code's `default_duration_minutes` (null for most codes → 30). The appointment's total duration cannot be derived from the plan. | Code default or 30 min; **Calc Time** is manual. | Add duration on plan items and appointment procedures. | Low (tracked) |

### Related existing gaps this flow depends on
- **APPT-PROC-1/2/3/4** (`appointment-procedures`: no duration / provider_units / bill_to; soft-delete rows come back) — `docs/scheduler/add_edit_appointment_backend_devreport.md`.
- **PLAN-20** (status enum lacks `scheduled` / `completed`) — prerequisite for PLAN-APPT-1.
- **NA-B6 / SCHED-1 / SCHED-2** (provider & operatory scoping).
- **D2 (data)** operatory `provider_id` unseeded.

---

## 3. Test residue (local dev DB)
- Appointment `APPT-7100447c-e7f4-44cc-a0fc-ef64c37a1067` (patient 1002, 2026-09-09 10:00, OPR-100) with procedure row `10131` — created by the live verification. Safe to delete.
- Plan item `37093a0c-bc95-4dd9-8d4b-a6604bce4ddf` (`D2740`, patient 1002) had `provider_id` set to `PRV-100` to verify provider defaulting.
- Operatory `OPR-101` `provider_id` was set to `PRV-100` during verification and reverted to `null` afterwards.
