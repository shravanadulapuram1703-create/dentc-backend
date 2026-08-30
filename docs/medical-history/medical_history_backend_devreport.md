# Patient Medical History — backend gap report

**Module:** Patient Medical History (`/patient/:patientId/medical-history`)
**Legacy screen:** Denticon "Patient Medical History" — Medical Alerts · Dental Questionnaire ·
Medical Questionnaire · Signature, plus the `***Copy Medical History***` picker.
**Frontend status:** shipped and live-verified against the local backend (`:8000`).
**Date:** 2026-08-29

---

## 0. What the frontend now does

One screen owns all four legacy tabs. Before it existed, medical alerts and the questionnaires
could only be entered while *registering* a patient — anything skipped at intake could never be
filled in afterwards, from anywhere in the app.

| Tab | Backend resource | Verb usage |
|---|---|---|
| Medical Alerts | `/api/v1/patient-medical-alerts` | list / create / update / delete per row |
| Dental Questionnaire | `/api/v1/patient-questionnaire-responses` (`questionnaire_type=dental`) | list / create / update / delete per row |
| Medical Questionnaire | same resource (`questionnaire_type=medical`) | as above |
| — Emergency Contact block | `/api/v1/patient-emergency-contacts` | mirrored (see MH-11) |
| Signature | `/api/v1/patient-signatures` | list / create |
| Header strip | `/api/v1/patients/{id}/overview` | single aggregate read |
| Catalogs | `/api/v1/definition-groups` + `/api/v1/definitions` | see MH-1 |

Answers are reconciled by row id: answered rows are created or patched, rows reset to **Not
Answered** are deleted. Repeated saves are idempotent.

**Everything below was reproduced against the running backend, not inferred from the schema.**

---

## Priority 1 — clinical-record integrity

### MH-6 · A signature is not linked to what was signed  🔴 **highest priority**

`patient_signatures` rows carry only:

```
patient_id, legacy_id, signature_data, signature_len, device_source,
is_user_sig, created_by, id, created_at
```

*(verified: `GET /api/v1/patient-signatures?patient_id=83867`)*

There is **no reference to the medical-history content that was signed** — no version id, no
snapshot hash, no "answers as of" timestamp. A patient can sign, staff can then change any answer,
and nothing in the data records that the signature predates the change. For a medical history —
a legal record used to justify treatment decisions — this is the gap that matters most.

There is also no `signature_type`, so a medical-history signature, a consent signature and a
financial-policy signature are indistinguishable rows on the same patient.

**Asks**
1. Add a signable snapshot: either version the medical history and store
   `medical_history_version_id` on the signature, or store a content hash + `signed_at`.
2. Add `signature_type` (`medical_history` | `consent` | `financial` | …).
3. Add `signed_by_user_id` distinct from `created_by` (who operated the pad vs who is attesting).

### MH-8 · No audit trail on answers

`patient_medical_alerts` and `patient_questionnaire_responses` both expose `created_by` and
`updated_at`, but **no `updated_by`** *(verified — see key lists in §Appendix)*, and no history.
Legacy prints "Modified By / Modified On" on this screen; we can render the timestamp but have to
leave the person blank.

**Ask:** `updated_by` on both resources, and ideally an append-only change log — for a medical
record, "who changed this answer and when" should be answerable.

### MH-16 · No "when was this questionnaire last completed"

`patient_questionnaire_responses` timestamps each *row*, not each *completion*. Practices
re-verify medical history at recall intervals; there is no field that says "the patient reviewed
and confirmed this on DD/MM/YYYY". Row `updated_at` is not the same thing — editing one answer
does not mean the whole form was reviewed.

**Ask:** a per-patient, per-questionnaire `last_completed_at` / `last_reviewed_by`, or fold it
into the versioning from MH-6.

---

## Priority 2 — the API shape forces N+1 traffic

### MH-2 · No composite read

Opening the screen currently costs, at minimum:

- `GET /patient-medical-alerts?patient_id=…`
- `GET /patient-questionnaire-responses?patient_id=…`
- `GET /patient-signatures?patient_id=…`
- `GET /patient-emergency-contacts?patient_id=…`
- `GET /patients/{id}/overview` (header strip)
- `GET /definition-groups?size=200` **× 3** (once per catalog type)
- `GET /definitions?group_code=…` **× N**, sequential, one per group

**Ask:** `GET /api/v1/patients/{id}/medical-history` returning alerts + both questionnaires +
signatures + the resolved catalogs in one payload. `/patients/{id}/overview` already proves this
shape works well.

### MH-3 · No composite write — "No to all alerts" is up to 88 HTTP requests

Legacy's **NO TO ALL ALERTS** button sets every unanswered row to No. With the ~88-item legacy
catalog and an empty patient, that is 88 sequential `POST /patient-medical-alerts` calls on Save.
Browsers cap ~6 connections per host, and this backend already saturates that (the Patient
Overview's per-member enrichment competes for the same pool), so the save visibly crawls.

**Ask:** `PUT /api/v1/patients/{id}/medical-history` accepting the whole document
(alerts[] + questionnaire_responses[] + comments) and reconciling server-side in one transaction.
This also removes the risk of a half-saved medical history when the tab is closed mid-save —
today each row is its own transaction.

### MH-4 · No server-side copy for "Copy Medical History"

Legacy's `***Copy Medical History***` picker is implemented client-side: read the source
patient's rows, then write them onto the target one row at a time. That means copying a fully
answered history is ~90 reads followed by ~90 writes from the browser, it is not atomic, and
nothing server-side records that chart B's history was copied from chart A.

**Ask:** `POST /api/v1/patients/{id}/medical-history/copy-from/{source_patient_id}`
with a `scope` of `all | alerts | dental | medical`, returning the new document, and writing an
audit entry naming the source patient. Copying medical answers between charts is exactly the kind
of operation that should be attributable.

---

## Priority 3 — data model / seeding

### MH-1 · Alert & questionnaire catalogs are not seeded

`GET /definition-groups` returns only stray test rows for all three types *(verified)*:

| group_code | group_type | description |
|---|---|---|
| `MEDALERT_TEST` | `MEDALERT` | "Test" |
| `DENTQUEST_TEST` | `DENTQUEST` | "test" |
| `MEDQUEST_TEST` | `MEDQUEST` | "test" |

Each holds fewer than 10 definitions, so the frontend rejects them (a `MIN_TENANT_CATALOG_ITEMS`
guard, or a single test row would replace ~90 real alerts) and renders the verbatim legacy
catalog from `src/features/add-patient/legacyCatalogs.ts` instead. The screen shows an
informational banner saying so.

**Consequence to resolve before go-live:** answers are keyed by a code the *frontend* derives
from the label (`toCode("Latex Rubber") → "latex_rubber"`). When the catalogs are finally seeded,
the seeded `key1` values **must match those derived codes**, or every already-answered row
silently orphans.

**Asks**
1. Seed `MEDALERT` / `DENTQUEST` / `MEDQUEST` from the legacy list (the frontend file is a
   verbatim transcription and can be handed over as the source of truth).
2. Use the same `toCode(label)` convention for `key1`, or tell us the codes you will use so we
   can migrate the existing rows.
3. `key2` carries the input kind (`text` | `date` | `textarea`, else Yes/No) — please keep it.

### MH-5 · `response = "unknown"` has no defined meaning

The enum is `yes | no | unknown`, but legacy models three states as **NO / NOT ANSWERED / YES**
and "not answered" is naturally the *absence* of a row. The frontend therefore never writes
`unknown`, and deletes the row when the user resets to Not Answered.

**Ask:** confirm whether `unknown` is meant to be an explicit third answer (in which case
"not answered" needs to stop being modelled as absence, so the two are distinguishable) or is
vestigial and can be dropped.

### MH-13 · "Additional Comments" is stored as a magic alert row

The Medical Alerts tab has a 100-character comments box with nowhere to live, so both this screen
and the Add-Patient wizard write it as an alert row with the reserved code
`ADDITIONAL_COMMENTS`. It is a convention shared by two modules with nothing enforcing it, and it
pollutes the alert list for any other consumer.

**Ask:** a first-class `comments` field on the medical-history document (or on a per-patient
medical-history header row).

### MH-14 · An answered patient alert cannot drive a flash alert or block charges

Three overlapping concepts exist and none of them connect:

| Resource | Has `blocks_charges` | Has `is_flash_alert` | Is a patient's answer |
|---|---|---|---|
| `patient_medical_alerts` | ✗ | ✗ | ✓ |
| `patient_alerts` | ✓ | ✗ | ✓ (free-text `alert`) |
| `definitions` (Setup catalog) | — | ✓ | ✗ (it is the catalog) |

So a patient answering **Yes** to "Latex Rubber" produces a row that no scheduler popover or
charge gate can act on, even though the Setup catalog can mark that alert as a flash alert.

**Ask:** either surface the catalog's `is_flash_alert` / `blocks_charges` on the patient's
answered rows, or have the backend propagate a Yes answer into `patient_alerts`.

### MH-11 · Emergency contact is stored in two places

The legacy Medical Questionnaire includes an Emergency Contact block, and there is also a real
`patient_emergency_contacts` resource that the rest of the app reads. The frontend currently
writes both and prefers the real resource on read, to stop the two drifting.

**Ask:** decide which is authoritative. Our preference: keep `patient_emergency_contacts`, and
drop those three questions from the questionnaire catalog.

### MH-12 · Nothing enforces contradictory alerts

"No Known Allergies = Yes" alongside "Penicillin = Yes", or "No Change Since Last Recorded = Yes"
alongside edits, are both storable. Legacy relies on the same honour system, so this is a
"worth knowing" rather than a regression — but a validation rule server-side would be safer than
each client re-implementing it.

---

## Priority 4 — patient search (blocks the Copy picker)

### MH-9 · `GET /patients?search=` has no relevance ranking  ⚠️ **verified reproduction**

Searching for the patient **`Rob, Leo` (id 83867)** by the term `Rob`:

```
GET /api/v1/patients?search=Rob&size=25&sort=last_name&order=asc
→ Abel, Robert #54553 · Aber, Robert #25122 · ABES, ROBIN #30446 · Abraham, Robert #69750 · …
→ does NOT contain #83867 within the first 50 results
```

The search matches hundreds of `Robert*` surnames and pages them alphabetically, so an exact
surname match is unreachable through any picker a user would tolerate. The Copy dialog had to
work around this on the client: bare numbers are resolved with a direct `GET /patients/{id}`,
`"Last, First"` input is split and re-filtered, and exact filters are merged ahead of name hits.

**Asks**
1. Rank results — exact `last_name` / `first_name` matches before substring matches.
2. Extend `search` to cover `chart_no`, `phone` and `cell_phone` (staff search by all three).

### MH-10 · The `phone` filter ignores `cell_phone`

```
Patient 83867: phone = null, cell_phone = "9092221234"
GET /api/v1/patients?phone=9092221234  →  0 results   (verified)
```

Most patients in this dataset have only a cell number, so the `phone` filter is close to useless
for lookup.

**Ask:** have `phone` match `phone` OR `cell_phone` OR `work_phone`, or add a `any_phone` filter.

---

## Priority 5 — nice to have

### MH-7 · Signatures are append-only with no supersede

There is no way to void or supersede a signature, and `PatientSignatureRead` has no `updated_at`.
The frontend takes "newest row of each `is_user_sig` value wins". A cleared signature therefore
cannot be represented at all.

**Ask:** an `is_active` / `superseded_by` field, consistent with the soft-delete pattern used
elsewhere in this API.

### MH-15 · No print/PDF endpoint

Legacy has a printer icon on this screen that renders the full medical history form. We can
generate it client-side (as done for Perio and Treatment Plans), but a server-rendered PDF would
be consistent for signed clinical records — and would be the natural place to embed the signature
snapshot from MH-6.

---

## Appendix — verified field lists

Captured live from the running backend on 2026-08-29.

```jsonc
// GET /api/v1/patient-medical-alerts?patient_id=83867
["id","tenant_id","patient_id","alert_code","alert_label","response",
 "comments","is_active","created_by","created_at","updated_at"]
// → no updated_by, no is_flash_alert, no blocks_charges

// GET /api/v1/patient-questionnaire-responses?patient_id=83867
["tenant_id","patient_id","questionnaire_type","question_code","question_text",
 "answer","is_active","created_by","id","created_at","updated_at"]
// → no updated_by, no answered_at / last_completed_at

// GET /api/v1/patient-signatures?patient_id=83867
["patient_id","legacy_id","signature_data","signature_len","device_source",
 "is_user_sig","created_by","id","created_at"]
// → no signed_at, no signature_type, no link to the signed content, no updated_at
```

---

## Summary

| # | Gap | Priority | Verified |
|---|---|---|---|
| MH-6 | Signature not linked to the answers it signed | 🔴 P1 | ✓ |
| MH-8 | No `updated_by` / change history on answers | 🔴 P1 | ✓ |
| MH-16 | No "questionnaire last completed" timestamp | 🟠 P1 | ✓ |
| MH-2 | No composite read (N+1 on every open) | 🟠 P2 | ✓ |
| MH-3 | No composite write (up to 88 POSTs per save) | 🟠 P2 | ✓ |
| MH-4 | No server-side Copy Medical History | 🟠 P2 | ✓ |
| MH-1 | MEDALERT/DENTQUEST/MEDQUEST catalogs unseeded | 🟡 P3 | ✓ |
| MH-5 | `response = "unknown"` undefined | 🟡 P3 | ✓ |
| MH-13 | Comments stored as a magic alert row | 🟡 P3 | ✓ |
| MH-14 | Answers can't drive flash alerts / charge blocks | 🟡 P3 | ✓ |
| MH-11 | Emergency contact duplicated | 🟡 P3 | ✓ |
| MH-12 | Contradictory alerts not validated | 🔵 P3 | ✓ |
| MH-9 | Patient search has no relevance ranking | 🟠 P4 | ✓ |
| MH-10 | `phone` filter ignores `cell_phone` | 🟠 P4 | ✓ |
| MH-7 | Signatures cannot be superseded/voided | 🔵 P5 | ✓ |
| MH-15 | No print/PDF endpoint | 🔵 P5 | — |
