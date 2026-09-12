# Add New Patient (full wizard) — Backend Response

**Date:** 2026-09-11 · **Branch:** `feature/uat-realse` · **Alembic:** `b317b3c05b47`
(revises `17559b3b70d4`) · **Reports answered:**
[add_patient_full_wizard_backend_issues.md](add_patient_full_wizard_backend_issues.md) (GAP-AP-20…26) and
GAP-AP-19 of [add_patient_backend_devreport.md](add_patient_backend_devreport.md). GAP-AP-1…18 shipped
earlier (`d5e6f7a8b9c0` / `e6f7a8b9c0d1`).

Every item below is implemented, covered by `tests/test_add_patient_wizard_gaps.py`, and described with
the contract the frontend should bind to. Frontend follow-ups are collected in §10.

---

## 0. TL;DR

| # | Gap | Status | What changed |
|---|-----|--------|--------------|
| **GAP-AP-19** | Middle name is a 10-char initial; overflow = 500 | ✅ | `patients.middle_name` + `responsible_parties.middle_name` (`VARCHAR(50)`); `middle_initial` derived server-side; every bounded string on `PatientCreate`/`Update` and the register person block carries `maxLength` → 422 |
| **GAP-AP-20** | `alert_code`/`question_code` `VARCHAR(50)`, no `maxLength`, 51+ chars = 500 | ✅ | Columns widened to **100** (incl. the `medical_history_details` snapshot); `maxLength: 100` on all six write schemas → 422 with the field path; backend `to_code` cap aligned to the FE's **50**; both numbers published |
| **GAP-AP-21** | 409 on register only; plain `POST /patients` unguarded; placeholder SSN/chart blocks everyone | ✅ | Same guard + `force_create` on `POST /patients`; synthetic identifiers never match; SSN/chart-no need one corroborating field (last name or DOB); 409 body unchanged (+ `override_field`) |
| **GAP-AP-22** | ~1.2 s per child row, no bulk | ✅ | `POST /patient-medical-alerts/bulk` + `POST /patient-questionnaire-responses/bulk` (one transaction, upsert by code, MH-12/MA-3/MH-8/MH-14 all applied); per-request catalog cache; and the composite now carries everything (-23/-24) |
| **GAP-AP-23** | `RecallIn` lacks `interval_unit`/`scheduled_date`/`scheduled_time` | ✅ | Added (LEG-17 closed) |
| **GAP-AP-24** | Insurance outside the composite | ✅ | `insurance[]` on `RegisterRequest`: subscriber (or `subscriber_id`) + link per slot, primary-first rank check, ids on `RegisterResponse` |
| **GAP-AP-25** | `resp_party_rel` seeded twice | ✅ | Lowercase set **deactivated** on every tenant, seeder emits the code set only; **the column holds the code** (`S/SP/P/G/C/D/O`), keys/labels folded on write; stored values normalised; vocabulary published on `/metadata/patient-flag-rules` |
| **GAP-AP-26** | 500s carry no diagnostic | ✅ | `DataError` → 422 (`value_too_long` / `value_out_of_range` / `invalid_value`); `IntegrityError` → 409 `constraint` (unique) or 422 (`foreign_key_violation` / `not_null_violation` / `check_violation`), with table/column/constraint; real 500s carry `details.request_id` |
| OBS-1 | Duplicate carriers, slow carrier search | ⏸ | Data hygiene, unchanged (INS-PT-13 name-availability probes already exist for new rows) |

Migration `b317b3c05b47` is **applied to the dev DB** (`recondental_migrated`).

---

## 1. What happened to patient 83928, re-read against the fix

1. Chart `123456` + SSN `123-45-6789` — both are now *synthetic identifiers* and match nothing, so the
   register would not have 409'd. Had the SSN been real, it would still need the last name or DOB to
   line up before it blocked (§3).
2. Had it 409'd anyway, `POST /patients` now returns the **same 409**, so the fallback could not have
   created the duplicate silently — and the FE no longer falls back on a 4xx, which is the right call.
3. Each of the 12 long codes is now (a) derivable identically on both sides (cap 50), (b) storable
   (column 100), and (c) rejected as a **422 naming `questionnaire_responses[i].question_code`** if a
   client ever sends >100 — never a 500, never a rolled-back registration with no hint.
4. The non-self responsible party is created by the composite (unchanged), and the composite now
   carries recalls with all their columns and insurance, so nothing needs the per-row path at
   registration time.

---

## 2. GAP-AP-20 — code length

**Columns** (`b317b3c05b47`): `patient_medical_alerts.alert_code`,
`patient_questionnaire_responses.question_code`, **and** `medical_history_details.question_code` →
`VARCHAR(100)`. The third is not in the report: the signed-version snapshot (MH-6) copies both codes into
it, so widening the sources alone would have moved the 500 to `POST …/medical-history/sign`. A pure widen —
nothing rewritten, nothing can be invalidated.

**Schemas** — `maxLength` now in `openapi.json` on `PatientMedicalAlertCreate/Update`,
`PatientQuestionnaireResponseCreate/Update`, `MedicalAlertIn`, `QuestionnaireResponseIn`, the two bulk
items (§4), `alert_label` (255), `section` (100), `questionnaire_type` (20). Overflow is a standard
`422 validation_error` whose `details[].loc` names the field, e.g.
`["body","questionnaire_responses",3,"question_code"]`.

**Derivation cap — the part that matters most.** The backend's own `to_code` (which builds the built-in
DENTQUEST/MEDQUEST/MEDALERT catalogs the Medical History document is keyed on) still sliced at **60**.
With the FE now at 50, the 12 long questions would have derived to *different* codes on the two sides and
every one of those answers would have read as Not Answered on the Medical History screen. Aligned to
**50** (`medical_history_catalog.CODE_MAX_LENGTH`). Both numbers are published:

```json
GET /api/v1/metadata/medical-history-rules → "code_convention": {
  "max_length": 50,          // what toCode() must slice to (answers are keyed by it)
  "storage_max_length": 100  // what the write schemas enforce as a 422
}
```

Please read `CATALOG_CODE_MAX_LENGTH` from `code_convention.max_length` rather than keeping the literal.
LEG-1 seeding, when it happens, uses the same `to_code`, so seeded `key1` values match what the UI sends.

---

## 3. GAP-AP-21 — one duplicate guard, two endpoints

**`POST /patients` is guarded.** `PatientCRUD.create` runs `find_strong_duplicates` and raises the same
409 as the composite. `PatientCreate` gains `force_create: boolean` (default `false`, not a column). The
409 body is unchanged and now also names the override:

```json
{"error": {"code": "duplicate_patient", "message": "…",
           "details": {"candidates": [DuplicateCandidate…], "override_field": "force_create"}}}
```

**Synthetic identifiers never match.** `is_synthetic_identifier()` (`patient_extra_service`) drops an SSN
or chart number that cannot identify anyone *before* the SQL runs, so `check-duplicate` never reports it
either: all-one-digit (`000000000`, `111111111`), keyboard runs (`123456789`, `987654321`, `123456`,
`1234` …), the never-issued SSNs (`078-05-1120`, `219-09-9999`), SSA-impossible areas/groups
(`000`/`666`/`9xx` area, `00` group, `0000` serial), and anything under four digits.

**`is_strong` tightened as asked.** SSN or chart-no now needs **one** corroborating field — `last_name`
or `dob`. A lone SSN hit under a different name *and* birthday is still returned as a candidate
(`match_on: ["ssn"]`, score 40) so the user sees it; it just does not refuse on its own. Reasoning:
`chart_no` is not unique in the migrated data (10,045 duplicated groups), and a mistyped SSN is far more
common than two records for one person under different names and DOBs. Full-name + (DOB | phone | email)
is unchanged.

---

## 4. GAP-AP-22 — bulk endpoints (and the per-request cost)

```
POST /api/v1/patient-medical-alerts/bulk           → MedicalAlertBulkResponse
POST /api/v1/patient-questionnaire-responses/bulk  → QuestionnaireResponseBulkResponse
```

```jsonc
// request
{"patient_id": 83929,
 "items": [{"alert_code": "penicillin", "response": "yes", "comments": "rash"}, …],  // ≤ 500
 "allow_contradictions": false,   // alerts only (MH-12 override)
 "replace": false}                // true = clear every stored code the payload omits
// response
{"patient_id": 83929, "created": 88, "updated": 0, "deleted": 0, "unchanged": 0,
 "contradictions": [], "items": [PatientMedicalAlertRead…]}   // items in payload order
```

* **Upsert by code** (`alert_code`; `(questionnaire_type, question_code)` for answers): an active row
  is updated in place, otherwise inserted. A null `response` **and** `comments` (alerts) or a null
  `answer` (questionnaires) resets the code to Not Answered (row deleted, MH-5).
* **One transaction, all-or-nothing.** A contradiction anywhere in the batch is a 422 and *nothing* is
  written.
* **Same rules as the single-row resource**: MH-12 contradictions judged on the merge of payload + stored
  rows, MA-3 label/section filled from the catalog, MH-8 change-log events per row, MH-14 flash-alert
  propagation once per batch.
* `replace` on questionnaires clears only the stored codes of a questionnaire *type present in the
  payload*; a type the payload does not mention is never touched.
* `questionnaire_type` is case-folded (`"Medical"` → `medical`); anything but `dental|medical` is 422
  `invalid_questionnaire_type`.

For the Medical History screen, `PUT /patients/{id}/medical-history` (MH-3) remains the full-document
replace; the bulk endpoints are for callers that hold one section.

**The 1.2 s.** The single-row alert create read the tenant MEDALERT catalog three times (guard, catalog
fill, flash-alert sync) — each two round trips to the remote DB — plus two commits and the audit row.
The catalog is now cached on the request's session (`Session.info`, invalidated by any flush touching
`definitions`/`definition_groups`), so a single-row POST is roughly half the queries; the bulk endpoint
amortises the rest to one read per batch. The remaining per-request cost is auth + audit + commit, which
is why bulk (or the composite) is the answer for 140 rows, not tuning the row path.

---

## 5. GAP-AP-23 — `RecallIn`

`interval_unit` (`month|year`, ≤10), `scheduled_date`, `scheduled_time` (`HH:MM`, ≤10) added and written
by the composite. `recall_type` ≤50, `procedure_code` ≤20 now carry `maxLength`. LEG-17 closed.

---

## 6. GAP-AP-24 — insurance on the composite

```jsonc
"insurance": [
  {"subscriber": RegisterSubscriberIn,          // InsuranceSubscriberCreate minus subscriber_patient_id
   "subscriber_is_patient": true,               // sets subscriber_patient_id = the new patient's id
   "link": RegisterInsuranceLinkIn},            // PatientInsuranceCreate minus patient_id/subscriber_id
  {"subscriber_id": 65314,                      // reuse an existing subscriber (Account Plans dependent)
   "link": {"legacy_plan_type": "D", "insurance_type": "primary", "relationship": "C"}}
]
```

* Exactly one of `subscriber` / `subscriber_id` per slot (422 otherwise); `subscriber_is_patient` only
  with an inline subscriber. `link.ins_plan_id` defaults to the subscriber's plan.
* `subscriber.ins_plan_id` must be a plan of the tenant → 422 `insurance_plan_not_found`;
  `subscriber_id` must be a subscriber of the tenant → 422 `insurance_subscriber_not_found`. Both carry
  `details.index` (the slot's position in the payload).
* **Slots are applied primary-first regardless of payload order**, so the Coverage Type rank rule
  (`missing_primary_coverage`, from `patient_rules_service.validate_coverage_slot`) judges the set the
  user built, not the order the form serialised it in. A rank failure also carries `details.index`.
* Everything is inside the registration transaction: a failing slot rolls back the patient, the
  guarantor, the alerts and any earlier subscriber — the orphaned-subscriber case cannot happen.
* `RegisterResponse.insurance[]` = `{subscriber_id, patient_insurance_id, ins_plan_id, legacy_plan_type,
  insurance_type}` **in payload order**.
* `sub_phone` / `marital_status` (the two fields the wizard collected but never sent) are ordinary
  subscriber columns and round-trip.

The two register-only components are generated from the same models as the stand-alone resources, so a
column added to `insurance_subscribers` / `patient_insurance` reaches both without a second edit.

---

## 7. GAP-AP-25 — one relationship vocabulary

* **Kept: the code set** `S / SP / P / G / C / D / O` (legacy parity; it is what
  `patient_insurance.relationship` already holds; it is the only set with *Dependent*).
* **Retired: the lowercase set** — `is_active=false` on every tenant (migration) and no longer emitted by
  `scripts/seed_account_definitions.py` (which now also retires it on older tenants via `RETIRED_KEYS`).
  Deactivated rather than deleted: `definitions` is Setup-editable, and your dropdown hooks already pass
  `is_active=true`, so the duplicate disappears without a one-way door.
* **The column holds the code.** `patients.responsible_party_relationship` is normalised on every write
  path (`POST/PATCH /patients`, `/patients/register`): a key (`spouse`), a label (`Spouse`) or a code in
  any case folds to `SP`. A value that is none of the three is stored as written (a migrated free-text
  value must not 422 an unrelated edit). Existing rows were normalised in the migration. `is_self` on the
  composite writes `S` (was `self`).
* Published so the form binds to the same thing the API stores:

```json
GET /api/v1/metadata/patient-flag-rules → "responsible_party_relationship": {
  "field": "responsible_party_relationship", "canonical": "key1",
  "definition_group": "resp_party_rel", "self_code": "S",
  "codes": [{"code":"S","label":"Self"}, {"code":"SP","label":"Spouse"}, …]}
```

Bind the dropdown's *value* to `definition.key1`, not `description`.

---

## 8. GAP-AP-26 — database errors are diagnosable

`app.core.exceptions.app_error_from_db` classifies SQLAlchemy `DataError` / `IntegrityError` (SQLSTATE +
`diag` block on Postgres, message text on SQLite so the test suite exercises the same contract) and is used
both by the global exception handlers and by `CRUDBase._commit` (which used to turn *every* integrity
error, FK and NOT NULL included, into a 409 carrying the raw driver string).

| Cause | Status | `error.code` | `details` |
|---|---|---|---|
| `22001` value too long | 422 | `value_too_long` | `max_length`, `table`, `column` (when the driver reports it), `sqlstate`, `db_message` |
| `22003` numeric overflow | 422 | `value_out_of_range` | same |
| `22P02` / `22007` / `22008` bad text/date | 422 | `invalid_value` | same |
| `23505` unique | **409** | `constraint` | `kind: "unique"`, `constraint`, `table`, `columns[]`, `values[]` |
| `23503` foreign key | 422 | `foreign_key_violation` | `kind`, `constraint`, `columns[]`, `values[]` |
| `23502` not null | 422 | `not_null_violation` | `kind`, `table`, `column` |
| `23514` check | 422 | `check_violation` | `kind`, `constraint` |
| anything else | 500 | `internal_error` | `request_id` (matches the `X-Request-ID` header and the server log line) |

Rule of thumb for the client: **4xx = your payload, do not retry; 500 = retry / fall back.** With
`details.request_id` on the 500, a bug report can be matched to the exact server log line.

**Breaking (small):** a unique violation surfaced through the generic CRUD routes used to be
`409 {"code": "conflict", "details": "<raw driver string>"}`; it is now `409 {"code": "constraint",
"details": {kind, constraint, table, columns[], values[], …}}`. Service-raised 409s
(`duplicate_patient`, `duplicate_plan_group`, `duplicate_lab_name` under `conflict`, …) are unchanged.
The FE does not branch on the old generic `conflict` for DB collisions (checked), so no client change is
required.

---

## 9. GAP-AP-19 — middle name

* `patients.middle_name` and `responsible_parties.middle_name` (`VARCHAR(50)`), on
  `PatientCreate/Update/Read`, `ResponsiblePartyCreate/Update/Read` and the register `person` block.
* `middle_initial` stays for legacy parity and is **derived** (`middle_name[0].upper()`) whenever a write
  carries `middle_name` without an explicit `middle_initial`. An explicit initial always wins. Clearing
  the name clears a *derived* initial and keeps a hand-typed one.
* `PatientCreate/Update` already carried `maxLength` on every bounded column (LAB-6 factory fix); the
  register `person` block now does too, so an 11-char `middle_initial` is a 422 on both paths.
* `#PAT_MID_INITIAL#` (letters) and the printed `Last, First M` header fall back to the full name's first
  letter / the full name. No new merge token — the catalog is pinned to the seeded corpus (LTR-5).

---

## 10. Frontend follow-ups

1. `npm run api:sync` (`openapi.json` regenerated): `PatientCreate.force_create`, `middle_name` on both
   entities, `RecallIn` ×3, `RegisterRequest.insurance[]` / `.allow_contradictions`,
   `RegisterResponse.insurance[]` / `.contradictions`, the two bulk endpoints, `maxLength` everywhere.
2. Rebind Middle Name to `middle_name`, drop `MIDDLE_NAME_MAX_LENGTH`; extend `patient_display_name`.
3. Read `CATALOG_CODE_MAX_LENGTH` from `medical-history-rules.code_convention.max_length`.
4. On Finish, send recalls and insurance inside `POST /patients/register` and delete the post-register
   `POST /patient-recalls` / `/insurance-subscribers` / `/patient-insurance` chain. The `insurance[]`
   result is in payload order.
5. The 5xx fallback path, if kept, can replace its per-row loops with the two `/bulk` endpoints.
6. "Rel. to Resp": bind the value to `key1`; the stored value is the code.
7. Error handling: branch on `error.code` (`duplicate_patient`, `value_too_long`, `constraint`,
   `foreign_key_violation`, `missing_primary_coverage`, `contradictory_medical_alerts`) — all carry a field
   path or a slot index now.

---

## 11. Verification

* Dev DB after `alembic upgrade head` (`b317b3c05b47`): `resp_party_rel` shows the 7 codes active and
  the 6 lowercase keys inactive on all **43** tenants; the 33 patients that carried a relationship now
  hold `S` (29) / `P` (3) / `SP` (1); `alert_code` / both `question_code` columns report
  `character_maximum_length = 100`, both `middle_name` columns 50.
* `pytest tests/test_add_patient_wizard_gaps.py tests/test_duplicate_patient_guard.py
  tests/test_add_patient_module.py` — 61 passed; full suite green (counts in the session summary).
* Two existing tests changed on purpose: `test_ssn_match_alone_blocks` became
  `test_ssn_plus_last_name_blocks` + `…_reported_not_strong` (GAP-AP-21 ask #2), and
  `test_new_patient_columns_persist` now expects `"self"` to read back as `"S"` (GAP-AP-25).
* Test patients 83929 / 83931 / 83932 from the report were left in place.
