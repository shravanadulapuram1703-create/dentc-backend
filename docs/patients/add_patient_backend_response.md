# Add New Patient — Backend Gap Response

> Response to [`add_patient_backend_devreport.md`](add_patient_backend_devreport.md).
> All 18 gaps are addressed. Field names follow the report's suggested snake_case
> names verbatim so the frontend can bind directly.

Migration: `d5e6f7a8b9c0_add_add_patient_module_gaps` (down_revision `c4d5e6f7a8b9`).

---

## Additive `patients` columns (auto-exposed on `PatientCreate`/`PatientRead`)

| Gap | Column | Type |
|-----|--------|------|
| GAP-AP-1 | `pronouns` | string(20) |
| GAP-AP-2 | `driver_license` | string(50) |
| GAP-AP-3 | `student_status` (`none`/`part_time`/`full_time`), `school_name` | string |
| GAP-AP-4 | `preferred_hygienist_id` | string FK → `providers.id` |
| GAP-AP-5 | `fee_schedule_id` | int FK → `fee_schedules.id` |
| GAP-AP-6 | `referred_to`, `referral_to_date` | string / date |
| GAP-AP-7/15 | `responsible_party_relationship` | string(50) — `self`/`spouse`/`parent`/… |
| GAP-AP-9 | `patient_types` | JSON array of codes (`["CH","OR",…]`); single `patient_type` stays the primary tag |
| GAP-AP-10 | `assign_benefits`, `add_to_quickfill`, `no_correspondence` | bool |
| GAP-AP-11 | `hipaa_sharing_notes` | text |

`preferred_hygienist_id` and `fee_schedule_id` are added as filterable list params
on `GET /patients` too.

**GAP-AP-5 note:** only the persistence column is backend scope. Repointing
`feeSchedules.ts` at `GET /api/v1/fee-schedules` (which already exists) and
dropping the mock schedules remains the flagged frontend task.

**GAP-AP-8 (coverage-type):** treated as transient UI state feeding the insurance
sub-flow (report option (a)); no backend field added. Coverage is persisted via
the existing `patient-insurance` slots.

---

## New per-patient resources (generic CRUD)

- **GAP-AP-16 — `GET/POST /api/v1/patient-medical-alerts`**
  `{patient_id, alert_code, alert_label?, response('yes'/'no'), comments?}`.
  Filterable by `patient_id`, `alert_code`, `response`.
- **GAP-AP-17 — `GET/POST /api/v1/patient-questionnaire-responses`**
  `{patient_id, questionnaire_type('dental'/'medical'), question_code, question_text?, answer}`.
  Filterable by `patient_id`, `questionnaire_type`, `question_code`.

(The MEDALERT/DENTQUEST/MEDQUEST *catalogs* remain the existing `definitions`
groups; these tables store the per-patient *answers*. Seeding the catalogs is a
separate pick-list task.)

---

## GAP-AP-12 — Opening balances (A/R)

- `PUT /api/v1/patients/{id}/opening-balance` seeds/replaces the 5 aging buckets
  `{as_of_date?, current, over_30, over_60, over_90, over_120, notes?}` (stored in
  the new `patient_opening_balances` table, one row per patient).
- `GET /api/v1/patients/{id}/opening-balance` returns the buckets + `total`.
- Wired into `GET /api/v1/patients/{id}/balance`: the seeded A/R is folded into
  `balance`, the aging buckets, and a new `opening_balance` field. A transferred
  patient no longer always shows `$0.00`.

---

## GAP-AP-14 — Chart number auto-generation

`POST /patients` (and `/patients/register`) with no `chart_no` now assigns one
server-side (`PatientCRUD`). A supplied `chart_no` is respected.

---

## GAP-AP-13/15/18 — Composite register (atomic)

`POST /api/v1/patients/register` creates, in **one transaction**:

```jsonc
{
  "patient": { /* PatientCreate */ },
  "responsible_party": { "relationship": "self", "is_self": true },
  "medical_alerts": [ { "alert_code": "LATEX", "response": "no" } ],
  "questionnaire_responses": [ { "questionnaire_type": "dental", "question_code": "Q1", "answer": "Yes" } ],
  "recalls": [ { "recall_type": "prophy", "interval_months": 6 } ],
  "opening_balance": { "current": 25.0 }
}
```

Every sub-section is optional (serves both Quick-Save and the full wizard Finish).
A failure anywhere rolls the whole thing back, so registration never leaves a
patient with only some related records. `is_self` self-links the patient as their
own guarantor.

**GAP-AP-15 scope:** the patient↔RP *relationship* is captured
(`responsible_party_relationship`) and self-guarantor linkage is automatic. A
full standalone non-self guarantor record (name/DOB/SSN/address/employer as a
separate billing entity) is **not** added — `responsible_party_id` links an
existing party. Flag if a dedicated guarantor resource is required.

---

## Tests

`tests/test_add_patient_module.py` — column round-trip, chart-no auto-gen,
medical-alert & questionnaire CRUD, opening-balance → computed balance, and the
atomic register endpoint.
