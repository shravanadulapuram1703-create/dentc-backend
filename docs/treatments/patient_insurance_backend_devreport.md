# Patient Insurance (Add/Edit Dental/Medical Plan) — backend dev report

Frontend module: `src/features/patient-insurance/**`
Route family: `/patient/:id/insurance/{dental|medical}/{primary|secondary|tertiary|quaternary}`
Nav: new **Insurance** icon (`ShieldCheck`) in `PatientSecondaryNav`.

## What this screen maps to

The legacy Denticon "Add/Edit Primary Dental Plan" window is reconstructed by
joining three existing backend resources for one *slot*:

| Slot dimension | Stored on `patient_insurance` |
| --- | --- |
| Category (Dental / Medical) | `legacy_plan_type` = `"D"` / `"M"` |
| Order (Primary…Fourth) | `insurance_type` = `"primary"`/`"secondary"`/`"tertiary"`/`"quaternary"` |

(This matches the convention already used by `PatientOverview`.)

- **INSURANCE PLAN / CARRIER / EMPLOYER** ← `insurance_plans` + `insurance_carriers` + `employers`
- **BENEFIT INFORMATION**
  - `Ind.` / `Fam.` columns (read-only) ← plan `individual_*` / `family_*`
  - `Ind. Rem.` columns (editable) ← `patient_insurance.deductible_remaining` / `max_remaining` / `ortho_remaining`
  - `Fam. Rem.` columns (editable) ← `insurance_subscribers.family_ded_remaining` / `family_max_remaining`
- **ELIGIBILITY** ← `insurance_subscribers.effective_date` / `term_date` / `anniversary_date` / `elig_status` / `elig_verified_on` / `elig_verified_by`
- **SUBSCRIBER INFORMATION** ← `insurance_subscribers.sub_*` + `patient_insurance.relationship` (Patient Rel to Sub)
- **NOTES** ← `insurance_subscribers.notes`

Save order: upsert subscriber → upsert `patient_insurance` link (uses generated
client only, no raw axios). The **ADD NEW INS PLAN** button opens a setup-style
modal that `POST`s `insurance_plans` and selects the new plan into the screen.

## Gaps (fields shown in the legacy UI with no backend column)

- **INS-PT-1 — Marital Status.** Legacy subscriber has a Marital Status select;
  `insurance_subscribers` has no `marital_status` column. Rendered, kept in local
  form state, **not persisted**.
- **INS-PT-2 — Subscriber Phone.** Legacy "Phone" field on the subscriber block;
  no phone column on `insurance_subscribers`. Rendered, **not persisted**.
- **INS-PT-3 — Sec. Sub Rel to Prim. Sub.** Secondary/Third/Fourth slots show a
  "Sec. Sub Rel to Prim. Sub" select in the legacy screen. There is no column to
  store the secondary subscriber's relationship to the primary subscriber.
  Rendered, **not persisted**.
- **INS-PT-4 — Subscriber address line 2.** `insurance_subscribers.sub_address`
  is a single column; the legacy screen has two address lines. The frontend
  joins/splits the two lines on a newline as a stopgap.
- **INS-PT-5 — Eligibility "Update Status" stamp.** `elig_verified_on` is set
  client-side to today's date; there is no server endpoint that performs an
  eligibility re-check / real-time verification. The Carrier model exposes
  `supports_realtime_eligibility`, but no verification call exists yet.
- **INS-PT-6 — Plan "Plan Date" eligibility column.** The legacy Eligibility grid
  has separate "Plan Date" and "Sub Date" columns for Effective/Term. Only a
  single subscriber-level date is stored, so the Plan Date column is read-only/blank.

## Notes

- `insurance_plans` has ~31k rows; the plan search uses the server-side `search`
  filter (`listInsurancePlans`) capped at 25 results, like Insurance Setup.
- `patient_insurance` DELETE / deactivation is not wired from this screen yet
  (legacy has no delete here either; slots are toggled `is_active`).

---

## Backend response — IMPLEMENTED (2026-06-24)

Migration: `alembic/versions/d6e7f8a9b0c1_add_patient_insurance_gaps.py` (down_revision
`c5d6e7f8a9b0`). New columns flow through the generic CRUD schemas automatically
(`build_schemas`), so the existing `insurance-subscribers` / `patient-insurance`
endpoints expose them with no client change beyond binding the field.

| ID | Resolution |
|---|---|
| **INS-PT-1** | `insurance_subscribers.marital_status` added (write/read on the subscriber CRUD). |
| **INS-PT-2** | `insurance_subscribers.sub_phone` added. |
| **INS-PT-3** | `patient_insurance.sec_sub_rel_to_prim_sub` added (secondary subscriber's relationship to the primary). |
| **INS-PT-4** | `insurance_subscribers.sub_address2` added — second address line (FE can stop newline-splitting `sub_address`). |
| **INS-PT-5** | `POST /insurance-subscribers/{id}/verify-eligibility` — stamps `elig_status` (body or default `"verified"`), `elig_verified_on=now`, `elig_verified_by=<current user>`, optional `notes`, and echoes the carrier's `realtime_supported` flag. `method` is `"manual"` (no clearinghouse wired yet; real-time check deferred). |
| **INS-PT-6** | `insurance_subscribers.plan_effective_date` / `plan_term_date` added — the legacy "Plan Date" column, distinct from the existing subscriber `effective_date`/`term_date` ("Sub Date"). |

Also: `patient-insurance` list gains `legacy_plan_type` + `is_active` filters so a
slot is addressable by category (`D`/`M`) × order (`primary`…) × active state.

Apply with `python -c "from alembic.config import main; main(['upgrade','head'])"`.
