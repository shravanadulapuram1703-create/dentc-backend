# ADA Dental Claim Form (2024) — backend response

> **Re:** `docs/claims/ada_claim_form_2024_backend_devreport.md` (ADA-BE-1…14)
> **Date:** 2026-09-11
> **Alembic:** `3cf1360c0100` (applied to the dev DB)
> **Tests:** `tests/test_ada_claim_form.py` (14)

Every gap in §2 is closed, and the CLM-FO-1…5 fill-out boxes the report folds in
("please add them to whatever lands for CLM-FO-1") landed with it — there was no
CLM-FO-1 yet, so the claim row now carries Items 2, 34/34a, 35, 36, 38, 40–47 as
columns and the `localStorage` record can be deleted.

## 1. What the frontend should switch to

| Was | Now |
|---|---|
| ~18 requests per print, assembled in the browser | `GET /insurance-claims/{id}/ada-claim-form` → one JSON document with all 58 items, every derived value tagged with `*_source`, plus `warnings[]` |
| jsPDF render | `GET /insurance-claims/{id}/reports/ada-claim-form?mode=form\|overlay&offset_x=&offset_y=` → `application/pdf` (audited). Keep the client renderer as the fallback, fed from the JSON above |
| no batch | `POST /insurance-claims/reports/ada-claim-form` `{claim_ids[≤200], mode, offset_x, offset_y}` → one PDF, one form per claim, in order |
| `chart-conditions?size=200` + `patient-procedures?size=200` for Item 33 | `GET /patients/{id}/tooth-status` (uncapped; `missing_teeth` is the Item 33 set) |
| keyword map for Item 56a | `ProviderRead.effective_taxonomy_code` / `effective_taxonomy_source`; catalog at `GET /metadata/provider-taxonomy-codes` |
| hard-coded vocabularies | `GET /metadata/ada-claim-form-rules` (transaction types, ICD qualifiers, pointer/quantity bounds, accident types, POS default, area-of-oral-cavity map, missing-teeth storage, signature rule, NPI rule, taxonomy catalog, warning + error codes) |
| `POST /insurance-claims` then one PATCH per line | `POST /insurance-claims` with `procedure_ids: [...]` — lines linked, providers/dates/totals/other plan defaulted, all in one transaction. The PATCH-per-line shape still works (see ADA-BE-12) |

## 2. Gap by gap

### ADA-BE-1 — server-rendered form · done
`app/services/claim_form_service.assemble` composes the form; `app/services/ada_claim_pdf.render`
draws it on US Letter with reportlab's canvas. **Rule E**: ten service lines per form —
a 12-line claim is two complete forms, each with its own Item 32 (Item 31a other fees on
the last one) and a `Page x of y` footer. `mode=overlay` draws values only at the same
coordinates for pre-printed stock; `offset_x/offset_y` (±72 pt) translate the page for
printer calibration. Every render writes an `audit_logs` row: `action='PRINT'`,
`resource_type='claim_report'`, `resource_id=<claim id>`, `patient_id`, and
`details.params` = `{claim_number, form_version: "2024", pages, mode, offset_x, offset_y}`
(`batch: N` on the batch route, one row per claim).

The layout is a fixed two-column grid carrying the ADA's item numbers, captions and
order — not a pixel copy of the ADA artwork — so a payer reading by item number finds
each value where the instructions say it is. Sample rendered from the test fixture is in
the PR description.

### ADA-BE-2 — the three 2024 boxes · done
`insurance_claims.is_epsdt`, `is_locum_tenens` (bool, default false),
`date_last_srp` (date, nullable). **NULL means derive**: the form reports the last
completed non-void `D4341`/`D4342` on or before the claim's service date and says so
(`ancillary.date_last_srp_source` = `claim | derived | none`). Item 1 prints
`transaction_type` = `epsdt` when `is_epsdt`, else `predetermination` when `is_preauth`,
else `statement`.

### ADA-BE-3 — diagnosis pointers · done
`patient_procedures.diagnosis_pointers varchar(4)` + `insurance_claims.icd_qualifier`
(`AB` ICD-10-CM default | `B` ICD-9-CM) + `icd_1…icd_4`. Pointers are normalised on
every write (`"a, b"` → `"AB"`, de-duplicated, priority order, ≤4; anything outside A–D is
422 `invalid_diagnosis_pointer`). ICD codes are stored as typed (upper-cased, shape-checked
`invalid_icd_code`) — **not** an FK to `icd_codes`, because a payer-required code the
practice has not seeded must still print. A line pointing at a blank slot is reported as
warning `pointer_without_diagnosis` (line + procedure id) rather than silently printing.

### ADA-BE-4 — quantity · done
`patient_procedures.quantity int NOT NULL default 1`, 1–99 (`invalid_quantity`), printed
`01`–`99` in Item 29b.

### ADA-BE-5 — other fees · done
`insurance_claims.other_fees numeric(10,2)`, ≥ 0, NULL = none (prints blank, not 0.00).
Added into `fees.total_fee` and Item 32 of the last form. Not computed from `taxable` lines —
no tax rate is stored anywhere and an invented one would mis-total every claim.

### ADA-BE-6 — missing teeth · done, both halves
1. `GET /patients/{id}/tooth-status` — per permanent tooth `present | missing | extracted |
   implant` with the evidence row (chart condition or extraction/implant charge) and date;
   two uncapped statements. `missing_teeth[]` is the Item 33 set.
2. `insurance_claims.missing_teeth varchar(120)` (comma list of 1–32, normalised, 422
   `invalid_missing_tooth`) overrides the derived set; `missing_teeth.source` = `claim | chart`.

### ADA-BE-7 — consent signature · done
`patient_signatures.signature_type = 'claim_consent'` is the vocabulary (published on the
rules endpoint). Item 36 is true when the claim's `signature_on_file` flag is set **or** an
active `claim_consent` signature exists — the captured signature wins
(`authorizations.signature_source` = `claim_consent_signature | claim | none`,
`consent_signature_id` / `consent_signed_at` for the e-claim's CLM09). `PatientRead.has_claim_consent`
is batched onto every patient list page.

### ADA-BE-8 — entity NPI · done
`offices.npi varchar(10)` + `offices.taxonomy_code`, on `OfficeRead`/`OfficeUpdate`. Item 49
= the office NPI when set (`billing.npi_type = "2"`), else the billing provider's Type 1 NPI
**with warning `billing_entity_npi_missing`** when the office has a `corporate_name` — that is
the pairing payers reject. Item 50 is blank when the entity bills unless
`use_billing_license` is on.

### ADA-BE-9 — other coverage · done
`insurance_claims.other_ins_plan_id` (FK) + `has_other_coverage` (nullable bool). Captured
at creation by `InsuranceClaimCRUD` (first active slot that is not the billed one, dental
before medical); a later slot change cannot re-point a printed claim. NULL
`has_other_coverage` = derive from whether an other plan resolves;
`other_coverage.plan_source` = `stored | stored_plan_only | derived | none`.

### ADA-BE-10 — suffix · done
`patients.suffix`, `responsible_parties.suffix`, `insurance_subscribers.sub_suffix` —
the subscriber column is `sub_`-prefixed like every other demographic on that table
(`sub_mi`, `sub_dob`…), so bind `sub_suffix`, not `suffix`, on the subscriber form.

### ADA-BE-11 — area of oral cavity · done
The stored token set is `UR UL LL LR UA LA FM` (validated by `procedure_rules_service`)
plus the legacy numerics `1–4`. `AREA_OF_ORAL_CAVITY` maps them to `10 20 30 40 01 02 00`
/ `10 20 30 40`, published on both `/metadata/procedure-entry-rules` and
`/metadata/ada-claim-form-rules`. A legacy quadrant-in-tooth value maps too, and is then
**not** printed in Item 27.

### ADA-BE-12 — provider ids on the claim · done
`InsuranceClaimCRUD` (registered on `/insurance-claims`) defaults at creation:
`office_id` ← patient home office; `treating_provider_id` ← majority provider of
`procedure_ids` (ties → earliest line) → patient's preferred provider;
`billing_provider_id` ← `offices.billing_provider_id` → treating; `ins_plan_id`/`carrier_id`
← the slot matching `billing_order` (default primary); `other_ins_plan_id` (ADA-BE-9);
service dates and `total_billed`/`est_insurance` ← the lines. The mix is refused (422
`claim_provider_mismatch`) **only** when one of the providers has
`print_separate_claim_form` — a mixed claim is otherwise legal and rejecting it would
break existing flows. The per-line PATCH path is covered too: the first charge attached to
a provider-less claim fills treating/billing/dates, and a separate-form provider cannot be
attached alongside. `procedure_ids` also 422s `procedure_not_found` /
`procedure_patient_mismatch` / `procedure_void` / `procedure_on_hold_claim` /
`procedure_already_claimed`.

### ADA-BE-13 — physical treatment address · done
`offices.treatment_address_line1/2`, `treatment_city/state/zip` (nullable). Item 56 uses
them when line 1 is set (`treating.location_source = treatment_address`), else the main
address; a main address that looks like a P.O. Box is warned `treatment_location_is_po_box`.

### ADA-BE-14 — taxonomy · done
`providers.taxonomy_code varchar(10)`. `ProviderRead.effective_taxonomy_code` = stored →
keyword-derived from `specialty` → `122300000X`, with `effective_taxonomy_source`. The dental
NUCC subset + keywords live once in `app/services/provider_taxonomy_service.py`; an
out-of-list code is stored verbatim (no 422 — an unfamiliar code is a lookup problem, not a
data-entry error).

### CLM-FO-1…5 (folded in)
Columns: `predetermination_number`, `remarks`, `signature_on_file`, `place_of_treatment`
(2-digit CMS POS, default `11` at print; the catalog is the existing
`/place-of-service-codes`), `is_ortho`/`ortho_appliance_date`/`ortho_months_remaining`,
`prosthesis_replacement`/`prosthesis_prior_date`, `accident_type`
(`occupational|auto|other`)/`accident_date`/`accident_state`. All validated on create and
PATCH (`invalid_*` codes on the rules endpoint). **CLM-FO-5**: `POST /insurance-claims/{id}/submit`
now assembles the form, freezes it as JSON on `claim_submissions.claim_text`
(+ `num_lines`), and returns `form_warnings[]` — the e-claim builder reads the same snapshot
the paper form printed, and a later edit cannot rewrite what was sent. `is_preauth` on the
submit body now defaults from the claim.

## 3. Not done / judgement calls

* **No Type 2 NPI, taxonomy, treatment address or suffix backfill** — none of these exist in
  the Denticon export. They are Setup fields.
* **Item 33 is permanent teeth only** (1–32), as the printed grid is. A primary tooth
  charted missing is ignored by both the form and `/tooth-status` — the endpoint answers
  the same 32-tooth grid the form draws, by design.
* **The PDF is a faithful-by-item grid, not the ADA artwork.** `mode=overlay` exists for
  practices that print on the licensed stock; the coordinates are the grid's, so calibrate
  with `offset_x/offset_y` against your stock.
* **`sub_suffix`**, not `suffix`, on subscribers (table convention).

## 4. Verification
`tests/test_ada_claim_form.py` — 14 tests: creation defaults + other-plan capture,
separate-form provider refusal (create and per-line attach), pointer/quantity rules,
fill-out vocabulary, the full assembled form (every section asserted), corporate-office
warnings, stored-override precedence + consent signature, form/overlay/batch PDF + 4 audit
rows, tenant scoping (JSON, PDF, batch, tooth-status), uncapped tooth status ranking,
provider/office reads, rules metadata, submit snapshot. Full suite green except the
pre-existing evening `today()` flake in `test_office_collections_today`.
