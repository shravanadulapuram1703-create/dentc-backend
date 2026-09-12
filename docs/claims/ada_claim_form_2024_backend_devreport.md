# ADA Dental Claim Form (2024) — backend dev report

> **Audience:** Backend team
> **Date:** 2026-09-11
> **Frontend:** `src/features/claims/ada/**` (model, assembler, jsPDF renderer, pre-flight), wired to
> **DIRECT PRINT** on `/patient/:patientId/claim/:claimId`
> **Spec:** *ADA Dental Claim Form Completion Instructions, Version 2024* (© ADA, 2023 Jun 02). The paper
> form's data content must be in harmony with the HIPAA 837D transaction, so every column asked for
> below is also needed by the e-claim builder (CLM-FO-5).
> **Related reports:** `docs/account-ledger/claim_fillout_backend_devreport.md` (CLM-FO-1…5),
> `docs/print/patient_print_backend_devreport.md` (PRINT-1…10)

## 1. How the form is produced today

The frontend assembles all 58 items client-side from existing resources and renders the PDF with
jsPDF. Each item's source, and whether the backend has a home for it, is in the map below. Items whose
row reads **none** print blank (or from a `localStorage` stop-gap) — those are the gaps in §2.

| ADA item | Printed from | Backend home |
|---|---|---|
| 1 Type of transaction | `insurance_claims.is_preauth`; EPSDT switch | `is_preauth` ✅ · EPSDT **none** (ADA-BE-2) |
| 2 Predetermination number | fill-out | **none** (CLM-FO-1) |
| 3 / 3a Payer name, address, Payer ID | `insurance_carriers.name/address/address2/city/state/zip/payer_id` | ✅ |
| 4–11a Other coverage | second `patient_insurance` slot → `insurance_subscribers`, `insurance_plans`, `insurance_carriers` | ✅ (derived by billing_order; see ADA-BE-9) |
| 12 Subscriber name/address | `insurance_subscribers.sub_last_name/sub_first_name/sub_mi/sub_address/sub_address2/sub_city/sub_state/sub_zip` | ✅ (no suffix, ADA-BE-10) |
| 13–17 | `sub_dob`, `sub_gender`, `sub_member_id`, `group_number` (subscriber → plan), employer name (`employers` / `insurance_plans.employer_name`) | ✅ |
| 18 Relationship | `patient_insurance.relationship` (free text: Self/Spouse/Child/Dependent/Other) | ✅ (un-enumerated, T5) |
| 19 Reserved | — | — |
| 20–23 Patient | `patients.last_name/first_name/middle_initial/address_line1/2/city/state/zip/dob/gender/chart_no` | ✅ (no suffix, ADA-BE-10) |
| 24 Procedure date | `patient_procedures.date_of_service` | ✅ |
| 25 Area of oral cavity | `patient_procedures.quadrant` + `procedure_codes.requires_quadrant/tooth_area` | ✅ (token set undocumented, ADA-BE-11) |
| 26 Tooth system | derived ("JP") | — |
| 27 Tooth number(s) | `patient_procedures.tooth` | ✅ |
| 28 Surface | `patient_procedures.surface` (normalised) | ✅ |
| 29 Procedure code | `patient_procedures.procedure_code` | ✅ |
| 29a Diagnosis pointer | — (all lines → "A" when ICD present) | **none** (ADA-BE-3) |
| 29b Quantity | — ("01") | **none** (ADA-BE-4) |
| 30 Description | `procedure_codes.description` (one GET per code) | ✅ |
| 31 Fee | `patient_procedures.fee` | ✅ |
| 31a Other fees | — | **none** (ADA-BE-5) |
| 32 Total fee | Σ lines per form | derived |
| 33 Missing teeth | `chart_conditions` + `patient_procedures` (extractions/implants) via the restorative bridge | ✅ derived (no per-claim override, ADA-BE-6) |
| 34 / 34a Diagnosis codes | fill-out ICD 1–4 | **none** (CLM-FO-1/3) |
| 35 Remarks | fill-out remarks + COB note | **none** (CLM-FO-1/2) |
| 36 Patient consent signature on file | fill-out `signature_on_file` | **none** (CLM-FO-1; `patient_signatures` not linked, ADA-BE-7) |
| 37 Assignment of benefits | `patients.assign_benefits` | ✅ |
| 38 Place of treatment | fill-out `place_of_treatment` | **none** (CLM-FO-1/4) |
| 39 Enclosures | `/insurance-claims/{id}/readiness.enclosures` + fill-out counts | ✅ (derived) |
| 39a Date last SRP | last completed D4341/D4342 in `patient_procedures` (two list calls) | ✅ derived (override **none**, ADA-BE-2) |
| 40–42 Orthodontics | fill-out | **none** (CLM-FO-1) |
| 43–44 Prosthesis | fill-out | **none** (CLM-FO-1) |
| 45–47 Accident | fill-out | **none** (CLM-FO-1) |
| 48 Billing entity name/address | `offices.corporate_name` (fallback `name`), `address_line1/2/city/state/zip` | ✅ |
| 49 Billing NPI | `providers.npi` of `insurance_claims.billing_provider_id` → `offices.billing_provider_id` → treating | ⚠️ no **office/entity Type 2 NPI** (ADA-BE-8) |
| 50 Billing license | `providers.license` (blank when corporation) | ✅ |
| 51 SSN / TIN | `offices.tax_id` → `providers.tax_id` | ✅ |
| 52 Billing phone | `offices.phone` → `providers.phone` | ✅ |
| 52a / 58 Additional provider ID | `provider_insurance_ids.ins_id` for (provider, carrier) | ✅ |
| 53 Treating dentist name + date | `providers.name` of `treating_provider_id` (fallback: majority provider on the procedures) | ✅ (`treating_provider_id` is null on claims created from the ledger, ADA-BE-12) |
| 53a Locum tenens | switch | **none** (ADA-BE-2) |
| 54 / 55 Treating NPI / license | `providers.npi`, `providers.license` | ✅ |
| 56 Treatment location | `offices.address_line1/2/city/state/zip` | ✅ (no "physical vs mailing" distinction, ADA-BE-13) |
| 56a Provider specialty code | `providers.specialty` (free text) → taxonomy code by keyword | ⚠️ (ADA-BE-14) |
| 57 Treating phone | `providers.phone` → `offices.phone` | ✅ |

**Calls per print:** `GET /patients/{id}`, `/insurance-carriers/{id}`, `/patient-insurance?patient_id` (×2, D and
M) + one subscriber/plan/carrier/employer GET per slot, `/providers/{id}` (×1–2), `/offices/{id}`,
`/chart-conditions?patient_id&size=200`, `/patient-procedures?patient_id&size=200`,
`/patient-procedures?procedure_code=D4341|D4342`, `/provider-insurance-ids?provider_id&carrier_id` (×2),
`/procedure-codes/{code}` per distinct code. About 15–20 requests, ~8 s on the dev backend.

## 2. Gaps

### ADA-BE-1 — No server-rendered ADA claim form · High

**Current status.** No `application/pdf` route exists for a claim. `PRINT-1` added
`/patients/{id}/reports/*` for four patient screens; claims were not included. The frontend renders
the form with jsPDF from ~18 requests (above), so the layout lives in the browser, nothing is
audited, and a form cannot be produced for a batch (e.g. "print all unsent paper claims").

**Ask.**
```
GET /api/v1/insurance-claims/{claim_id}/reports/ada-claim-form
      ?mode=form|overlay        # full form on plain paper, or data-only for pre-printed stock
      &offset_x=&offset_y=      # printer calibration (pt)
      -> application/pdf
```
Rendered from the canonical rows with the same item mapping as §1, one page per 10 service lines
(rule E), and a PRINT audit row (`claim_status_history` or the existing PRINT audit table) recording
user, timestamp and form version. The frontend keeps the client renderer as the fallback exactly as
`serverReport.ts` does for the patient reports.

### ADA-BE-2 — Three 2024-form boxes have no column · High

The 2024 revision added three data elements. None exist on `insurance_claims`:

| Column | ADA item | Type |
|---|---|---|
| `is_epsdt` | 1 (EPSDT / Title XIX) | bool, default false |
| `is_locum_tenens` | 53a | bool, default false |
| `date_last_srp` | 39a | date, nullable — when null the server derives it from the last completed D4341/D4342 |

They are currently kept in the per-claim `localStorage` record together with the CLM-FO-1 fields.
Please add them to whatever lands for CLM-FO-1 (claim columns or the 1:1 fill-out child).

### ADA-BE-3 — No per-procedure diagnosis pointer · High

Item 29a links each service line to one or more of the four claim-level diagnosis codes (A–D,
primary first). `patient_procedures` has no pointer column and the claim has no `icd_1…4`
(CLM-FO-3). The print points every line at "A" whenever any ICD is entered, which is wrong for
mixed-diagnosis claims and for 837D loop 2400 `SV3` pointer positions.

**Ask.** `patient_procedures.diagnosis_pointers` `varchar(4)` (letters A–D in priority order) — or a
`claim_procedure_diagnosis` link — plus `icd_1…icd_4` on the claim.

### ADA-BE-4 — No quantity on a procedure · Medium

Item 29b (01–99) has no source; every line prints "01". The instructions allow reporting the same
procedure on several teeth as one line with the teeth in Item 27 and the count in 29b. Add
`patient_procedures.quantity int default 1` (also the 837D `SV304` units).

### ADA-BE-5 — No "Other Fee(s)" (31a) · Low

State sales tax and regulatory charges must print in 31a and be included in 32. There is no
claim-level `other_fees` column; `procedure_codes.taxable` / `sales_tax_code` exist but no tax amount is
computed or stored. Add `insurance_claims.other_fees numeric(10,2)` (or compute from taxable lines).

### ADA-BE-6 — Missing-teeth information is derived only · Medium

Item 33 is built from `chart_conditions` (MISSING / extraction / implant families) plus completed
extraction procedures. Two problems:

1. The page cap: `size=200` on `chart-conditions` and `patient-procedures` — a heavily charted patient
   can exceed it and lose "missing" rows. A `GET /patients/{id}/tooth-status` (per-tooth present /
   missing / implant, already needed by Perio ↔ Restorative INTEG-1) would remove the fan-out.
2. Billing sometimes needs to mark teeth for a specific claim without charting (legacy had a 32-box
   grid on the claim). Add `insurance_claims.missing_teeth varchar(120)` (comma list) that overrides
   the derived set when present.

### ADA-BE-7 — Patient consent signature not linked to the claim · Medium

Item 36 "Signature on File" is a fill-out checkbox. `patient_signatures` exists (SIG phase) with
`signature_type`, but nothing marks a consent as the HIPAA/treatment consent that authorises the claim
statement. Add a `signature_type = 'claim_consent'` (or expose `has_claim_consent` on the patient) so
the print can assert "Signature on File" from a real captured signature and the e-claim can set the
release-of-information indicator (837D `CLM09`).

### ADA-BE-8 — No billing-entity NPI on the office · High

Item 49 requires the **Type 2 (organisation) NPI** when a corporation/group bills. `offices` has
`corporate_name`, `tax_id`, `billing_provider_id`, `use_billing_license` but no `npi`. The print
falls back to the billing provider's Type 1 NPI, which is wrong for incorporated practices (and is
rejected by some payers when paired with a corporate TIN). Add `offices.npi varchar(10)` (+ optional
`offices.taxonomy_code`), and expose both on `OfficeRead`/`OfficeUpdate`.

### ADA-BE-9 — Other-coverage selection is inferred from `billing_order` · Medium

Items 4–11 must describe the *other* plan (secondary when billing primary, primary when billing
secondary). The claim row carries `ins_plan_id` for the billed plan only; the frontend re-reads
`patient-insurance` and picks the other active dental slot by tier, then medical. Two subscribers with
the same plan, or a patient whose slots changed after the claim was created, print the wrong "other"
plan. Add `insurance_claims.other_ins_plan_id` (nullable) captured when the claim is created, and
`has_other_coverage` (CLM-FO-1) as the explicit Item 4 flag.

### ADA-BE-10 — No name suffix anywhere · Low

Items 5, 12 and 20 are "Last, First, Middle Initial, **Suffix**". `patients`, `responsible_parties`
and `insurance_subscribers` have `title` (prefix) but no `suffix`. 837D NM107 needs it. Add
`suffix varchar(10)` to the three tables.

### ADA-BE-11 — Quadrant/arch tokens are undocumented · Low

`patient_procedures.quadrant` is free text. The print maps `UR/UL/LL/LR/UA/LA/FM` (and the legacy
numeric `1/2/3/4`) to the ADA two-digit codes `10/20/30/40/01/02/00`. Please confirm the migrated
value set (or store the ADA code directly) and expose it in `/metadata/procedure-entry-rules`.

### ADA-BE-12 — `treating_provider_id` / `billing_provider_id` are null on ledger-created claims · Medium

`POST /insurance-claims` from the ledger leaves both null (verified on claim
`ff1f14fe-1dad-4bb2-99d8-553bd09628f4`). The print falls back to the majority provider on the
procedures and the office's billing provider. Please default `treating_provider_id` to the provider
of the procedures being claimed (reject if they differ across providers, or split the claim —
`providers.print_separate_claim_form` already exists for this) and `billing_provider_id` to
`offices.billing_provider_id`.

### ADA-BE-13 — No physical vs mailing address on the office · Low

Item 56 must be the **physical** treatment location (street address, never a P.O. Box); Item 48
may be the billing/mailing address. `offices` has one address. Offices that bill through a P.O. Box
cannot print a compliant Item 56. Add `treatment_address_line1/2/city/state/zip` (nullable, falls
back to the main address), or a `service_location` child.

### ADA-BE-14 — Provider specialty is free text; the form needs a taxonomy code · Medium

Item 56a takes a Healthcare Provider Taxonomy code (122300000X, 1223G0001X, 1223E0200X, …).
`providers.specialty` is an un-enumerated string (`provider_specialty` definitions group). The print
keyword-maps it (endo → 1223E0200X …) and defaults to 122300000X "Dentist". Add
`providers.taxonomy_code varchar(10)` (or seed the `provider_specialty` definition group with the
taxonomy code as the item code) — also required for 837D `PRV03`.

### Also affecting the form (already reported elsewhere)

| Gap | Effect on the form |
|---|---|
| CLM-FO-1 | Items 2, 34a, 35, 36, 38, 40–47 come from `localStorage` — invisible to other workstations and to the e-claim |
| CLM-FO-2 | Remarks (35) is not persisted at all |
| CLM-FO-3 | ICD library unseeded → Items 34/34a usually blank |
| CLM-FO-4 | Place of service (38) hard-coded list |
| CLM-FO-5 | None of the above reaches `POST /insurance-claims/{id}/submit` |
| PROV-INSID | `provider_insurance_ids` has no Setup editor; values exist only from migration |
| T5 | `patient_insurance.relationship`, `sub_gender`, `patients.gender` are free text; mapped to Self/Spouse/Dependent/Other and M/F/U client-side |
| INS-8 | Unstable pagination on `patient-insurance` / `chart-conditions` can drop a slot or a missing-tooth row |

## 3. Priority

1. **ADA-BE-8** (entity NPI) and **ADA-BE-2** (2024 boxes) — without them a corporate practice cannot
   print a compliant form.
2. **ADA-BE-3** (diagnosis pointers) + CLM-FO-1/3 — required whenever a payer or Medicaid asks for
   ICD-10-CM.
3. **ADA-BE-12** (provider ids on the claim row) — removes guesswork from Items 49–58.
4. **ADA-BE-1** (server PDF + audit) — same pattern as PRINT-1; the frontend fallback stays.
5. ADA-BE-6/7/9/14 — correctness of Items 33, 36, 4–11, 56a.
6. ADA-BE-4/5/10/11/13 — completeness polish.

## 4. Verification notes

Live-verified against the local backend (`admin`, tenant 1) on claim
`ff1f14fe-1dad-4bb2-99d8-553bd09628f4` (patient 83928, carrier 78 CIGNA (UCR), plan 37874,
subscriber 65312, office 2, provider PRV-100). All 18 lookups returned 200; the assembled form and the
printed PDF matched the rows (Items 3/3a, 12–18, 20–23, 24/29–32, 38–40, 43, 48, 51, 53, 56, 56a). Blanks on
this claim (49, 52, 54, 55, 57) trace to missing provider/office columns, not to the mapping — see
the data-quality section of the UI report.
