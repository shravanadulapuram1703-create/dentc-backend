# Edit Treatment window + Tx Plan → New Appt — backend response

**Reports answered:** `treatment_plan_backend_devreport.md` (the 2026-09-08 Edit
Treatment re-audit, PLAN-9/11/16/17/18/19/20/24/25/26/27/28/29 + the PLAN-3
confirmation) and `tx_plan_new_appointment_backend_devreport.md` (PLAN-APPT-1…7).
**Alembic:** `9de6ac649cba` — **applied to the dev DB** (`recondental_migrated`).
**Tests:** `tests/test_treatment_plan_edit_gaps.py` (25 cases) + the existing
treatment-plan / procedure-entry / scheduler suites; full suite green.
**OpenAPI:** regenerated (`openapi.json`, 466 paths) — regenerate the Orval client.

Where the code lives: [app/services/treatment_service.py](../../app/services/treatment_service.py)
(item CRUD, link state machines, re-estimate, book-from-plan),
[app/services/appointment_service.py](../../app/services/appointment_service.py) (new —
the appointment-side hooks), [app/api/v1/treatment.py](../../app/api/v1/treatment.py),
[app/api/v1/procedure_codes.py](../../app/api/v1/procedure_codes.py) (eligibility),
[app/schemas/treatment.py](../../app/schemas/treatment.py).

---

## 1. Already there before this pass (confirmed, no change)

| Gap | Status |
|---|---|
| PLAN-1/2/5/10/14 item columns | ✅ since `feature/phase_data_migration` |
| PLAN-12 `GET /patients/{id}/treatment-plan-items` | ✅ paged envelope (PROC-INT-4) |
| PLAN-13 item delete with insurance-details | ✅ soft delete + cascade-archive |
| PLAN-6 `GET /treatment-plans/{id}/report` | ✅ (now also carries `deductible_applied` per line for the PLAN-21 tilde) |
| PLAN-7 `patient-consents` | ✅ |
| PLAN-20 `scheduled` / `completed` | ✅ (`completed` server-derived — 422 `status_requires_charge` is correct) |
| PLAN-APPT-6 provider office scoping | ✅ PROV-1 (`GET /providers?office_id=` unions `provider_offices` + home office) |
| Perf — item PATCH 15–30 s | ✅ was redis-py's default connect retry (MA-8); both clients fail fast now |
| PLAN-8 documents list empty | ✅ resolved earlier (list is patient-scoped, not office-scoped) |

**PLAN-3 confirmation:** yes, `POST /treatment-plans/{id}/re-estimate` writes the
per-item `treatment-plan-insurance-details` row (`estimated_ins`, `estimated_pat`,
`deductible`, `coverage_pct`, `annual_max_rem`, `ins_plan_id`) — the ADVANCED panel
can read it. **But it had a real bug** (§2.1).

---

## 2. What changed

### 2.1 PLAN-3 — the re-estimate matcher was returning 0 % on every migrated plan

`re_estimate` compared the ADA code lexically against the coverage band
(`start_code <= code <= end_code`). Migrated plans band on **Denticon coverage-
category codes** (`01`, `03A`, `11B` — the FEE-1 finding), so `D2740` never fell
inside `03A`–`03A` and every migrated plan estimated 0 % insurance. Only the few
plans banded on real ADA ranges worked, which is why "Re-Estimate does nothing"
looked intermittent. It now uses the **same ranked, category-aware matcher** as the
charge estimate engine (`estimate_service.match_coverage_rule`), so a plan and a
charge can never disagree about which band a code is in. Each `ReEstimateLine`
reports `coverage_category` and `rule_start_code` so the UI can show *why*.

`?use_new_fees=true` is the legacy **Use New Fees** checkbox, server-side: every
line is re-priced through the fee resolver (assignment → plan → office default →
code default) and `fee_schedule_id` is stamped (PLAN-29). "Use New Billing Order"
still has nothing to do server-side — `billing_order` on the item is free text.

### 2.2 Edit Treatment window fields — all on `treatment_plan_items`

| Gap | Column(s) | Behaviour |
|---|---|---|
| **PLAN-17** | `notes` TEXT | The NOTES box. **Move it here** — the insurance-detail row was the wrong home (an uninsured patient's note forced an empty insurance row into existence). `treatment-plan-insurance-details.notes` still exists and is not touched. |
| **PLAN-18** | `accepted_date`, `scheduled_date` | `accepted_date` is **stamped server-side the first time status becomes `accepted`** (office-local date) unless the body supplies one; re-accepting later keeps the original. `scheduled_date` follows the soonest live appointment the item is booked on (§2.4) and can also be set by hand. |
| **PLAN-19 / APPT-7** | `duration_minutes` INT nullable | Nullable on purpose (unset ≠ 0). Falls back to `procedure_codes.default_duration_minutes`, then 30. Inherited by the appointment line and the posted charge. |
| **PLAN-25** | `created_by`, `updated_by` FK users | Stamped by the CRUD engine from the token; `created_by_name` / `updated_by_name` embedded on every read (batched, no lookup). |
| **PLAN-27** | `referral_id` FK referrals, `referral_type` (`in`/`out`) | Tenant-checked (422 `referral_not_found`), type normalised case-insensitively (422 `invalid_referral_type`). `referral_name` embedded on read. |
| **PLAN-28** | `update_end_date_at_posting`, `re_estimate_at_posting` BOOL | Honoured by `POST /treatment-plan-items/{id}/post`: the first forces `end_date` = service date even when one is set; the second recomputes the insurance estimate from *today's* coverage (charge estimate engine) before pricing the charge. Both overridable per call in `PostPlanItemRequest`. |
| **PLAN-29** | `fee_schedule_id` FK fee_schedules | `fee` is now **optional on create**: an omitted fee is priced server-side (same resolver as charges) and the schedule recorded. An explicit fee always wins; the schedule is recorded beside it only when it is the one that would have produced that exact amount, so "Fee Schedule Used" never lies. `fee_schedule_name` on read. |
| **PLAN-11** | `counselor_user_id` FK users | The Treatment Counselor field, tenant-checked; `counselor_name` on read; filterable. A fuller case-presentation resource (presented date / outcome) is still not modelled — say if the window needs it. |
| **PLAN-20** | — | Status enum gains `internal_referral` and `external_referral`. Full list at `GET /metadata/treatment-plan-rules`. |

### 2.3 PLAN-26 — ICD-10 cross coding

New table `treatment_plan_item_icd_codes` (`plan_item_id`, `icd_code_id`, `ordinal`,
unique per pair, `ON DELETE CASCADE`). Wire shape on the item:

* write `icd_code_ids: int[]` on `POST`/`PATCH /treatment-plan-items` — replaces the
  set, order = `ordinal`, `[]` = **clear all**, unknown ids → 422
  `icd_code_not_found` with `details.missing`;
* or `PUT /treatment-plan-items/{id}/icd-codes {"icd_code_ids": [...]}`;
* read `icd_code_ids` + `icd_codes[] {id, code, icd10, description, ordinal}`
  embedded (one query per page).

### 2.4 PLAN-APPT-1/2/5 — the item ↔ appointment link

* **`appointment_procedures.treatment_plan_item_id`** (FK, indexed, filterable). The
  plan id alone could not tell two identical open items apart.
* **`TreatmentPlanItemRead.appointment_id`** (soonest live booking) and
  **`appointment_ids[]`** — *derived* from the line FK, the same way `procedure_id`
  is derived from the charge FK, so there is one source of truth. Archived lines and
  cancelled / deleted appointments are excluded.
* **Booking flips the item to `scheduled`**, and the item remembers where it came
  from in **`status_before_scheduled`**. Cancel (`PATCH /appointments/{id}/status`
  or a generic PATCH setting `is_cancelled`), DELETE (soft archive), or archiving /
  re-pointing the line puts it **back to exactly that status** (or `accepted` if it
  was never recorded); un-cancel / `POST …/restore` books it again. A completed
  item is never touched. Every path goes through two functions
  (`schedule_item` / `release_scheduled_item`), so the status endpoint and the
  generic CRUD cannot disagree.
* **`POST /appointment-procedures` with `treatment_plan_item_id`** (your existing
  save path) now validates the item against the appointment's patient/plan (422
  `plan_item_patient_mismatch` / `plan_item_plan_mismatch` / `item_completed` /
  `item_archived`), inherits code / tooth / surface / description / fee / estimate /
  provider / duration where the payload left them blank, and books the item.
* **`POST /treatment-plans/{plan_id}/book`** (PLAN-APPT-5) — one transaction:

  ```json
  { "item_ids": ["…"], "date": "2026-10-01", "start_time": "09:00:00",
    "duration": null, "provider_id": null, "operatory_id": null, "office_id": null,
    "appointment_id": null, "notes": null, "status": null }
  ```

  Defaults: provider = first item's provider → any item's provider → the chosen
  operatory's column provider → patient's preferred provider (422
  `provider_required`); office = plan office → patient home office; operatory =
  provider's `default_operatory_id` if in that office → the office chair whose
  `provider_id` matches → none; duration = Σ item durations; line `status = "TP"`.
  Returns the appointment, the lines, the (now scheduled) items, and
  `provider_source` / `operatory_source` so the form can say how it defaulted.
  409 `item_already_scheduled` (with `details.bookings {item_id: [appointment_id]}`);
  nothing is written on any failure.

### 2.5 PLAN-APPT-3 — provider on plan items

* `s27b` wrote the diagnosing provider into **`diagnosed_by`** as the Denticon
  PROVIDERID (= `providers.legacy_id`) and never filled `provider_id`. New item
  creates now **default `provider_id`** from `diagnosed_by` (id or legacy id) →
  the plan's majority provider → the patient's preferred provider. It stays
  **nullable**: making it required would 422 the add-procedure panel, which does
  not always know a provider. Booking also adopts the appointment's provider onto a
  provider-less item.
* `scripts/backfill_treatment_plan_item_providers.py` — **applied**:
  693 of 728 provider-less items resolved from `diagnosed_by`; 33 remain, of which
  31 would resolve by plan-majority and 1 by preferred provider (`--from-plan
  --from-patient`, inference, **not applied**), 1 unresolvable.

### 2.6 PLAN-APPT-4 — provider → operatory

* **`providers.default_operatory_id`** (writable via `PATCH /providers/{id}`,
  validated to sit in an office the provider serves — 422
  `operatory_not_in_provider_office`). Used by book-from-plan.
* `scripts/backfill_operatory_providers.py` derives `operatories.provider_id` and
  `providers.default_operatory_id` from booking history (≥ 60 % share **and** ≥ 10
  appointments). Dry run on the migrated tenant: 25 chairs + 1 provider default
  clear both bars, 15 pairs rest on < 10 appointments, 19 are genuinely shared
  (no 60 % majority). **Not applied** — a wrong default puts every booking in the
  wrong column; confirm the printed pairs, then `--apply`.

### 2.7 PLAN-16 — eligibility, batched

* `GET /procedure-codes/eligibility?codes=D1110,D2740` → per code `restricted` +
  `provider_ids`, plus `eligible_for_all` (intersection for a multi-row Change
  Provider; `null` when nothing is restricted) and `restricted_provider_ids`.
* `GET /procedure-codes/{code}/providers` — the reverse lookup.
* **Semantics confirmed:** an empty assignment set means **unrestricted**. There is
  **no legacy source to seed from** — the Denticon export has no provider↔ADA
  eligibility file (`PROVIDERINSID.txt` is carrier ids, `PROVIDERROUTESLIP.txt` route
  slips), so assignments are a Setup task via `PUT /providers/{id}/procedure-codes`.
  The narrowing activates automatically once any assignment exists.

### 2.8 PLAN-9 — pre-auth status

`treatment_plan_insurance_details.preauth_status` (`sent` | `closed` | null, case-
insensitive, 422 `invalid_preauth_status`) + server-stamped `preauth_status_at`
(moves only when the status changes). Filterable. The full lifecycle (submission to
a clearinghouse) is still out of scope — no clearinghouse is contracted.

### 2.9 PLAN-24 — archived rows hidden by default

`GET /treatment-plan-items` and `GET /treatment-plan-insurance-details` now exclude
`is_archived=true` rows unless the caller asks (`?is_archived=true` surfaces the
tombstones). The FE's `is_archived=false` on every call can go.

### 2.10 Rides along — a tenancy hole

`treatment_plan_items` and `treatment_plan_insurance_details` carry no `tenant_id`,
and the generic engine only scopes models that do — so any tenant could read,
PATCH or delete any item / detail by id. Both CRUDs now scope through item → plan →
patient (foreign rows are 404).

---

## 3. Data / deferred

| Item | Status |
|---|---|
| Test residue (plan `ZZ AUDIT RESIDUE…`, items `0ba0b8e5…`/`ab41d012…`, details 1/2/3, appointment `APPT-7100447c…` + line 10131) | **Deleted** from the dev DB after checking nothing referenced them. Item `37093a0c…` keeps `PRV-100` (that is now correct data). `OPR-101.provider_id` was already null. |
| Migrated item ↔ appointment-line link | **Not reconstructable**: both derive from `AppointmentDetails.APPTDYD` but `appointment_procedures` kept no legacy id. Needs a re-import step if wanted. |
| PLAN-21 tilde | `deductible_applied` per line is on the report payload; render `~` when it is > 0. |
| PLAN-22 cash / card Est Pat split | Needs a second fee source; not modelled. |
| PLAN-23 Topaz in the plan PDF | The Topaz module (SIG-1…10) stores the signature; embedding it in the plan PDF is an FE/print follow-up. |
| PLAN-11 case-presentation resource | Only the counselor field shipped (see §2.2). |

---

## 4. Frontend follow-ups

1. Read/write **`notes` on the item**, not on the insurance-detail row.
2. Drop `is_archived=false` from item / detail list calls (PLAN-24).
3. New Appt: call `POST /treatment-plans/{id}/book` (or keep the two-step save but send
   `treatment_plan_item_id` on each line). Read `appointment_id` on the item to render **S**.
4. Change Provider: one `GET /procedure-codes/eligibility?codes=` instead of N provider calls.
5. Re-Estimate: pass `?use_new_fees=true` for the checkbox; drop the client-side fee refresh.
6. Edit Treatment: the four remaining boxes (`internal_referral`, `external_referral`,
   Sent/Closed radios, Duration, Referral, Counselor, ICD list, posting flags, Created/
   Modified By names, Fee Schedule Used) are all live. Vocabularies at
   `GET /metadata/treatment-plan-rules`.
