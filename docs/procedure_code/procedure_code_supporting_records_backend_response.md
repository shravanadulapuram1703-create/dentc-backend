# Procedure Codes — Supporting-Records Requirements (PROC-7) — Backend Response

Date: 2026-09-10
Answers: `procedure_code_supporting_records_backend_devreport.md` (PROC-7a…7d) and the
open items of `procedure_codes_backend_devreport.md` §5 (PROC-6, PROC-7).
Alembic: `aee911131850` (**applied to the dev DB** — 1,122 codes, all five flags `false`).
Tests: `tests/test_procedure_supporting_records.py` (17, green).

---

## 0. Summary

| Gap | Status | Where |
|---|---|---|
| PROC-7a five flags on `procedure_codes`, on all three schemas + list | ✅ | `app/db/models/codes.py`, `app/schemas/procedure_code.py` (factory-derived) |
| PROC-7b advertised in `/metadata/procedure-entry-rules` | ✅ advisory + error codes + the rule table | `procedure_rules_service.rules_metadata` |
| PROC-7c "satisfied" defined + readiness endpoints + enforcement | ✅ enforced at **claim submit** (422 + override); advisory on posting | `app/services/supporting_records_service.py`, `app/api/v1/supporting_records.py` |
| PROC-7c sub-gap: document ↔ procedure / claim link | ✅ `patient_documents.procedure_id` / `claim_id` | upload form fields + list filters |
| PROC-7d claim Enclosures pre-population | ✅ derived on `GET /insurance-claims/{id}/readiness` (no fill-out column exists yet) | `_enclosures()` |
| PROC-6 fee-schedules latency | already shipped: `GET /fee-schedules/options` (id/name/fee_type projection) | `app/api/v1/fee_schedules.py` |
| Legacy backfill of the five flags | ❌ not possible — `Codes.txt` has no such columns | see §1 |

---

## 1. PROC-7a — the columns

Five `BOOLEAN NOT NULL DEFAULT FALSE` columns, named exactly as the frontend already
sends them: `requires_attachment`, `requires_perio_chart`, `requires_photo`,
`requires_xray`, `requires_missing_tooth_info`. They sit next to `requires_tooth` on the
model, so the schema factory derives the same shape the report asked for:

- `ProcedureCodeRead` — `bool` (required) on **list and detail**.
- `ProcedureCodeCreate` / `ProcedureCodeUpdate` — `bool | None = None` (omitted = unchanged /
  default false).

`PATCH /procedure-codes/00170 {"requires_xray": true}` now round-trips (the report's
acceptance curls 1–3 are the first test in the file).

**Backfill:** none. `s10_procedure_codes` reads `TOOTHREQ / SURFREQ / QUADREQ / LABREQ`
from `Codes.txt`; the export carries nothing of the attachment / x-ray / perio shape, so
every migrated code lands on `false` and the practice sets them in Setup (Charting tab).
The migration is not touched.

## 2. PROC-7b — metadata

`GET /metadata/procedure-entry-rules` now carries:

- the five flags under **`advisory`** (not `enforced`) with the sentence that says where
  they *are* enforced;
- `error_codes` gains `supporting_records_missing` (the 422 on submit) plus the
  per-procedure codes `attachment_required`, `perio_chart_required`, `photo_required`,
  `xray_required`, `missing_tooth_info_required`;
- a new **`supporting_records`** block: `flags`, `enforced_at: "claim_submit"`,
  `enforce_on_submit` (the live setting), `override`, the three readiness URLs,
  `perio_max_age_months`, and **`rules[]`** — `{flag, key, label, stage, satisfied_when,
  error_code}` — so the UI renders the checklist from the same table the server judges by.

## 3. PROC-7c — what "satisfied" means, and where it is enforced

One home: `app/services/supporting_records_service.py`. The rule table:

| Flag | `key` | `stage` | Satisfied when… |
|---|---|---|---|
| `requires_attachment` | `attachment` | **claim** | a `patient_documents` row is linked to the procedure (`procedure_id`) or its claim (`claim_id`), **or** the claim has a non-deleted `claim_attachments` row. Before the charge exists it is **`deferred`**, never `missing` — the pop-up can say "will need an attachment" without claiming it is already late. |
| `requires_perio_chart` | `perio_chart` | post | a non-voided `perio_exams` row with `exam_date ≤ DOS`, and within `perio_max_age_months` of the DOS when that is set (query param, else `SUPPORTING_RECORDS_PERIO_MAX_AGE_MONTHS`, default unset = any age). |
| `requires_photo` | `photo` | post | a `patient_documents` row typed `PH`, or a DICOM study with a photographic modality (`XC`/`ES`). |
| `requires_xray` | `xray` | post | a `patient_documents` row typed `XR`, or a DICOM study dated `≤ DOS` (null date counts) with a radiographic modality (`IO PX DX CR RG XA RF CT`). `?strict_tooth=true` narrows to instances whose `tooth_numbers` include the tooth. |
| `requires_missing_tooth_info` | `missing_tooth_info` | post | an active `chart_conditions` row charted `MISSING`/`EXTRACTED`/`BRIDGE_PONTIC`/… **with** an `activity_date`, **or** a posted non-void extraction charge (`D7111`–`D7251`) — its DOS *is* the extraction date. Tooth is not matched (the missing tooth is by definition not the one being restored). |

Two things deliberately do **not** count: document upload time is not capture date, so
`patient_documents` are never DOS-filtered; and the legacy `image_details` rows carry no
type, so they are reported as `untyped_legacy_images` in the evidence and never satisfy a
rule ("unknown" and "on file" are different answers).

### Endpoints

```
GET /patients/{patient_id}/procedure-readiness?procedure_code=D2740&tooth=30&date_of_service=2026-09-10
      [&perio_max_age_months=6][&strict_tooth=true]
GET /patient-procedures/{procedure_id}/readiness          # tooth/DOS/claim from the row
GET /insurance-claims/{claim_id}/readiness                # every non-void line + enclosures
```

`ProcedureReadiness` = `{requires[], satisfied[], missing[], deferred[], ready, evidence{key→…},
rules{key→{label,stage,satisfied_when,error_code}}}` — the shape the report sketched, plus
`deferred` and the per-key evidence (counts, latest exam/study date, tagged-instance count,
charted teeth / extractions) so the UI can say *why*.

`ClaimReadiness` = `{ready, enforced_on_submit, procedures[ProcedureReadiness],
missing[{procedure_id, procedure_code, tooth, date_of_service, record, code}], enclosures}`.
`missing` is byte-for-byte the 422 body the submit returns.

### Enforcement — decided

- **Posting a charge / a treatment-plan item: advisory, never a 422.** The record is
  normally captured after the chair (x-ray taken, narrative written, photo uploaded), so a
  block on `POST patient_procedures` would refuse the very charge the record is about.
  There is no inline warning on the POST either — the readiness endpoint *is* the warning,
  and it is what every screen renders (a per-row readiness block on the 200-row
  `/patient-procedures` list would be 200 × 5 queries).
- **Claim submission: enforced.** `POST /insurance-claims/{id}/submit` runs the claim
  readiness first — before anything is written — and is a **422
  `supporting_records_missing`** with `details.missing[]` while any non-void line lacks a
  record. `ClaimSubmitRequest.allow_missing_records: true` overrides (a carrier may accept
  a claim the practice knows is thin; refusing outright would push staff to un-flag the
  code), and `ClaimSubmitResult.missing_records_overridden` reports that it was used.
  `SUPPORTING_RECORDS_ENFORCE_ON_SUBMIT=false` turns the gate into report-only.
- **Claim creation: deliberately not gated.** The frontend's Create Claim is
  `POST /insurance-claims` followed by `PATCH /patient-procedures{claim_id}` per line; a
  422 on the PATCH would leave a half-built claim.

### Document ↔ procedure / claim link (the sub-gap)

`patient_documents.procedure_id` (FK `patient_procedures`) and `claim_id` (FK
`insurance_claims`), both nullable, on `PatientDocumentRead`, as **form fields on
`POST /patient-documents`** and as **filters on `GET /patient-documents`**. Validated same
patient (422 `document_procedure_mismatch` / `document_claim_mismatch` — a mis-pointed id
would render in the wrong chart *and* count as "attached" for the wrong charge). A
document linked to a claimed charge inherits the charge's `claim_id`. Blank form values
mean "no link".

## 4. PROC-7d — Enclosures

`GET /insurance-claims/{id}/readiness → enclosures`:
`{radiographs, oral_images, models, narratives, perio_charts, other, attachments_enclosed,
required_attachment_types[], missing_attachment_types[]}` — counts from the claim's
`claim_attachments` (by `attachment_type`, INS-PAY-8 codes) plus `patient_documents`
linked to the claim (`XR`→radiographs, `PH`→oral images); `required_attachment_types` is
what the claim's codes ask for (`requires_xray`→`XRAY`, `requires_photo`→`PHOTO`,
`requires_perio_chart`→`PERIO`, `requires_attachment`→`NARRATIVE`). `models` is always 0
(no model/impression attachment type exists). This is **derived, not persisted**: the ADA
fill-out (CLM-FO-*) has no columns yet; when it does, this block is the value to seed.

## 5. Acceptance checklist (from the report)

- [x] 5 columns on `procedure_codes`, default false, NOT NULL (`aee911131850`, applied)
- [x] `ProcedureCodeRead` returns them as booleans (list + detail)
- [x] `ProcedureCodeCreate` / `ProcedureCodeUpdate` accept them (nullable = unchanged)
- [x] `openapi.json` regenerated (461 paths) — frontend runs `npm run api:sync`
- [x] `/metadata/procedure-entry-rules` lists them under `advisory` + rule table + error codes
- [x] PROC-7c readiness helper (three reads) + documented satisfaction rules
- [x] PROC-7c enforcement at claim submit with override
- [x] PROC-7d enclosures (derived)

## 6. Frontend switch-over

1. `npm run api:sync` — the five fields appear on `ProcedureCodeRead/Create/Update`;
   `resolveProcedureCodeExtras` goes server-first automatically.
2. Delete the localStorage fallback and the amber note in `ChartingTab.tsx`.
3. Add Procedure pop-up / treatment-plan post: call
   `GET /patients/{id}/procedure-readiness` with code + tooth + DOS and render
   `missing` (warn) / `deferred` (info) using `rules[key].label`.
4. Claim fill-out: `GET /insurance-claims/{id}/readiness` → checklist from `missing`,
   Enclosures box from `enclosures`; on a 422 `supporting_records_missing` from submit,
   show `details.missing` and offer "Send anyway" → resubmit with
   `allow_missing_records: true`.
5. Document upload from the ledger / claim: send `procedure_id` (and/or `claim_id`) so
   `requires_attachment` can be satisfied per charge.

> **Restart the dev server** (`uvicorn … --reload` picks up the new router, but a server
> started without `--reload` will still serve the old schema and drop the flags).
