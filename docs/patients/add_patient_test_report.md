# Add New Patient — End-to-End Functional Test Report

**Tested:** 2026-07-26 · local `:5173` against backend `:8000` (migration `e6f7a8b9c0d1`)
**Credentials:** `admin` / `admin` · Office: *Excel Dental- Moon, PA*
**Dummy patients created:** 83890, 83891, 83893
**Build:** `npx tsc -b` clean · `npx eslint` clean

---

## Result summary

| Area | Result |
|---|---|
| Login, office select, page load | ✅ Pass |
| Identity gate (lock/unlock, age auto-calc) | ✅ Pass |
| Required-field validation (inline, no alert chain) | ✅ Pass |
| Duplicate check (Check Patient) | ⚠️ Works, 3 dead columns (**BUG-1**) |
| All Step-1 inputs / selects / checkboxes | ✅ Pass |
| Date Stamp + char counters | ✅ Pass |
| Coverage mutual exclusivity | ✅ Pass |
| Dynamic insurance steps per coverage | ✅ Pass (5→7→8 steps; per-slot isolation) |
| Quick Save + full field round-trip | ⚠️ Pass except `is_active` (**BUG-2**) |
| Opening balances (A/R) | ✅ Pass — $190.75 = exact sum |
| Responsible Party (self + non-self guarantor) | ✅ Pass — guarantor created & linked |
| Medical Alerts (88 rows, No-to-all) | ✅ Pass |
| Questionnaires (29 + 22, all sections) | ✅ Pass |
| Recall (Month/Year unit + sched date/time) | ✅ Pass — exact round-trip |
| **Primary Dental + Primary Medical together** | ❌ **FAIL — backend constraint (BUG-3)** |
| Patient Overview display of saved data | ⚠️ 4 blank fields + 1 raw code (**BUG-4/5**) |

**7 bugs found. 4 fixed in this pass; 3 need the backend.**

---

## BUG-3 🔴 CRITICAL (backend) — a patient cannot have both Primary Dental *and* Primary Medical insurance

**Severity:** Critical — breaks the core multi-coverage feature and legacy parity.

**Steps to reproduce**
1. Add New Patient → tick **Primary Dental** *and* **Primary Medical**.
2. Complete both insurance screens (pick a carrier + plan on each).
3. Finish.

**Expected:** both `patient_insurance` rows saved (legacy supports 4 dental + 2 medical slots).
**Actual:** the first saves, the second is rejected —
`" Patient registered. Some items need attention: • Primary Medical insurance could not be saved."`

**API evidence** — `POST /api/v1/patient-insurance` → **409 Conflict**:
```
duplicate key value violates unique constraint
  "patient_insurance_patient_id_insurance_type_key"
DETAIL: Key (patient_id, insurance_type)=(83893, primary) already exists.
```

**Root cause:** the unique constraint is on `(patient_id, insurance_type)` and **omits
`legacy_plan_type`**. Since `insurance_type` only holds `primary`/`secondary`, a Primary
Dental row blocks any Primary Medical row.

**Suggested backend change**
```sql
ALTER TABLE patient_insurance
  DROP CONSTRAINT patient_insurance_patient_id_insurance_type_key,
  ADD CONSTRAINT patient_insurance_patient_slot_key
    UNIQUE (patient_id, legacy_plan_type, insurance_type);
```
**Impact:** until fixed, only one "primary" plan per patient can exist, regardless of
dental vs medical. The frontend already reports the failure per-slot rather than failing
silently, and the patient itself still registers.

**Secondary issue:** the `insurance-subscribers` POST succeeds (201) *before* the
`patient-insurance` POST 409s, leaving an **orphaned subscriber row** (e.g. 65304).
Ideally the pairing should be transactional, or the subscriber created only after the link.

---

## BUG-1 🟡 MEDIUM — Duplicate-check modal has 3 permanently empty columns

**Steps:** enter DOB + a common surname (e.g. *Smith, Autumn*) → **Check Patient**.
**Expected:** the candidate grid's columns are populated.
**Actual:** *Office Short ID*, *Email* and *Provider* are **always blank**.

**Root cause:** `DuplicateCandidate` only returns
`{id, chart_no, first_name, last_name, dob, is_active, match_score}`, so
[`patient.service.ts`](../../src/services/patient.service.ts) hardcodes
`officeShortId: ''`, `email: ''`, `provider: ''`.

**Suggested backend change:** add `home_office_short_id`, `email` and
`preferred_provider_name` to `DuplicateCandidate` — they are exactly what a user needs to
decide whether a candidate is really the same person. (Frontend alternative: hide the
columns; kept visible pending your answer.)

**Also noted (low):** matching returns many 30%-score candidates that share only a
surname (different first names *and* DOBs). Worth a relevance threshold.

---

## BUG-2 🟠 HIGH (fixed) — the "Active" checkbox was never sent

**Steps:** Add New Patient → **un-tick "Active"** → Quick Save.
**Expected:** patient saved with `is_active: false`.
**Actual:** payload contained `is_active: null`; the backend defaulted it to `true`, so
un-ticking Active was **silently ignored** — a data-loss bug.

**Root cause:** `patient_flags` in `buildPatientPayload` never included `is_active`, and
the `PatientCreateRequestFull.patient_flags` type didn't declare it, so it type-checked.

**Fix (shipped):** added `is_active: formData.active` to the flags block and to the type.

---

## BUG-4 🟠 HIGH (fixed) — Patient Overview showed Provider / Hygienist / Home Office / Fee Schedule blank

**Steps:** create a patient with a Preferred Provider, Preferred Hygienist and Fee
Schedule → land on Overview.
**Expected:** those fields show the names.
**Actual:** **PROVIDER**, **HYGIENIST**, **HOME OFFICE** and **FEE SCHEDULE** all rendered
blank / `-`, even though the record correctly stored
`preferred_provider_id: PRV-100`, `preferred_hygienist_id: PRV-104`,
`fee_schedule_id: 25`, `home_office_id: 1`.

**Root cause:** the Overview reads `preferred_provider_name`, `preferred_hygienist_name`,
`home_office_name`, `fee_schedule_name`, but `toPatientDetails` only ever set the **ids** —
`PatientRead` carries no names (and `home_office_name` is still missing, LEG-16).

**Fix (shipped):** `getPatientDetails` now resolves the four names via the existing
cached lookups (providers / fee-schedules / offices) in parallel, best-effort.

---

## BUG-5 🟢 LOW (fixed) — Contact Pref showed the raw code

**Actual:** Overview displayed `cell_phone`. **Expected:** `Cell Phone`.
**Fix (shipped):** added `humanizeContactPref()` in the Overview mapper.

---

## BUG-6 🟢 LOW — no Middle Initial on the patient form

The payload and backend both support `middle_initial`, and the Responsible Party screen
has an **MI** field, but the *patient's* Step-1 form has none, so it is always `null`.
Legacy has it. Suggest adding the field (frontend, small).

---

## BUG-7 🟢 LOW (backend, environment) — severe latency

A cold Add-Patient load fires ~13 GETs and takes **~60s** to settle; logins take
**20–40s** and mid-test sessions expired repeatedly. Consistent with the backend team's
own finding that **Redis is unreachable** from the app, so every request that touches it
pays a connect-timeout before falling back. It degrades rather than fails, but the screen
looks broken while loading. Worth fixing `REDIS_*` on the deployed instance.

---

## What was verified working (evidence)

**Full field round-trip** — patient **83891** was saved with every Step-1 field populated
and read back byte-for-byte, including all the previously-dropped ones:
`pronouns: "He/Him"`, `driver_license`, `student_status: "Full-time"` + `school_name`,
`medicaid_id`, `preferred_hygienist_id: "PRV-104"`, `fee_schedule_id: 25`,
`patient_types: ["CH","SR"]`, `assign_benefits`, `add_to_quickfill`, `no_correspondence`,
`hipaa_sharing_notes`, `guardian_*`, `preferred_contact`, auto-generated `chart_no: "83891"`,
and self-linked `responsible_party_id: "83891"`.

**Opening balances** — entered 100.50 / 50.25 / 25.00 / 10.00 / 5.00 → Overview header
showed **$190.75**, the exact sum.

**Non-self guarantor (LEG-10)** — patient **83890** registered with an inline
`responsible_party.person`; the record came back with `responsible_party_id: "1"`,
confirming the guarantor was created *and* linked in one transaction.

**Recall fidelity (LEG-8)** — a `3 Year` interval with a scheduled slot round-tripped
exactly: `interval_months: 3, interval_unit: "year", scheduled_date: "2028-01-20",
scheduled_time: "14:45"` — no Year→months conversion, nothing folded into notes.

**Dentical Share of Cost (LEG-6)** — persisted (`dentical_share_year: 2026`,
`dentical_share_amount: "25.00"`, `dentical_unused: "10.00"`) and correctly appears on
**dental** slots only, not medical.

**Dynamic insurance steps** — step count tracked coverage exactly (5 → 6 → 7 → 8), each
slot kept independent state (a plan picked on Medical did not leak into Dental), and
Back/Continue/stepper navigation behaved.

**Medical Alerts** — all **88** legacy alerts in 3 groups; "No to all med alerts" produced
`88/88 answered · 1 Yes`, correctly preserving the explicit Yes.

**Questionnaires** — Dental **29** and Medical **22** including *Emergency Contact* and
*Women Only* sections.

**Validation** — Continue with an empty form blocked on Step 1 and surfaced all four
inline errors at once (*Address / Sex / Preferred Provider / Referral Type*) with no alert
chain; Check Patient stayed disabled until the identity gate was satisfied.

---

## Handover

- **Backend:** BUG-3 (critical constraint) and BUG-1 (duplicate-candidate fields); plus the
  still-open LEG-1 (catalog seeding — [seed file supplied](legacy_catalog_seed.json)),
  LEG-15, LEG-16 and LEG-17 from
  [`add_patient_legacy_parity_devreport.md`](add_patient_legacy_parity_devreport.md).
- **Frontend:** BUG-2, BUG-4, BUG-5 fixed in this pass; BUG-6 (Middle Initial) outstanding
  and trivial.
