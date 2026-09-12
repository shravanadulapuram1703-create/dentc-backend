# Add New Patient (full wizard) — Backend Issues Report

**Date:** 2026-09-11 · **Branch:** `feature/uat-realse-v2` · **Backend:** local `uvicorn :8000` against the shared
Postgres dev DB (`recondental_migrated`) · **Frontend:** `:5173` (Vite dev)

**Trigger:** creating a patient through the full wizard (Patient Info → Responsible Party → Insurance ×2 →
Medical Alerts → Questionnaires → Recall → Finish) produced a burst of failed
`POST /api/v1/patient-questionnaire-responses` calls in DevTools (patient **83928**, 12 requests, all answered
dental/medical questions such as *"Do you get frequent fever blisters…"*, *"Have you taken bisphosphonates…"*).

This report explains **why** those 12 requests failed, why they were sent one-by-one at all (the atomic
`/patients/register` had already been refused), what the frontend fixed on its side, and what still needs the
backend team. Every item below was reproduced against the running backend with `curl` and re-verified through
the UI after the frontend fixes.

---

## 0. TL;DR

| # | Gap | Severity | Status |
|---|-----|----------|--------|
| **GAP-AP-20** | `question_code` / `alert_code` columns are `VARCHAR(50)` with **no `max_length` in the schema**; a 51+ char code returns **HTTP 500 `internal_error`** and rolls back the whole `/patients/register` transaction. 12 of the 51 legacy questions can never be saved. | 🔴 P0 | FE worked around (codes clamped to 50). Backend: widen column **and/or** add `max_length` → 422 |
| **GAP-AP-21** | Duplicate guard is inconsistent: `/patients/register` returns **409** on *any* single-field SSN / chart-no match (no `force_create`), while plain `POST /patients` has **no duplicate check at all**. Shared dummy SSN `123456789` / chart `123456` in the dev DB trips it for almost every test patient. | 🟠 P1 | FE fixed (409 → duplicate modal → retry with `force_create`; no more silent fallback). Backend: apply the same guard to `POST /patients`, tighten `is_strong` |
| **GAP-AP-22** | Per-row child endpoints cost **~1.2 s each**; the chained path for one patient (88 alerts + 51 answers + recalls + insurance) takes **~3 minutes** and is non-atomic. No bulk endpoints exist. | 🟠 P1 | Backend: bulk create endpoints, or make the composite carry everything (see -23/-24) |
| **GAP-AP-23** | `RecallIn` (register composite) still lacks `interval_unit` / `scheduled_date` / `scheduled_time` (= LEG-17), so recalls cannot ride the atomic register. | 🟡 P2 | Backend: add the 3 fields to `RecallIn` |
| **GAP-AP-24** | Insurance (subscriber + `patient_insurance` link) is not part of `RegisterRequest`; it is attached afterwards, outside the transaction. | 🟡 P2 | Backend: `insurance: [...]` section on `RegisterRequest` |
| **GAP-AP-25** | `definitions?group_code=resp_party_rel` contains **two seed sets** (keys `self/spouse/…` *and* `S/SP/P/G/C/D/O`) → the "Rel. to Resp" dropdown lists every option twice. | 🟡 P2 | Backend: dedupe the seed, pick one key scheme |
| **GAP-AP-26** | Server 500s carry no diagnostic (`{"code":"internal_error"}`), so a client cannot tell a bad payload from an outage; `DataError`/`IntegrityError` should map to 422/409 with the field. | 🟡 P2 | Backend: exception mapping |
| OBS-1 | Insurance carrier search returns many duplicate carriers ("Aetna" × 9, same payer id) and takes 8–10 s. | 🔵 obs | Data hygiene |
| ✅ BUG-3 (old) | A patient can now hold Primary **Dental** *and* Primary **Medical** — verified, unique constraint fixed. | fixed | — |
| ✅ BUG-1 (old) | `DuplicateCandidate` now carries `email` / `home_office_short_id` / `preferred_provider_name`; FE now renders them. | fixed | — |

Test patients created during this pass (dev DB, safe to delete): **83929** (full wizard, chained fallback),
**83931** (atomic `curl` register with `force_create`), **83932** (UI Quick Save → 409 → "Create Anyway").

---

## 1. What actually happened to patient 83928 (the DevTools errors)

Reconstructed from the DB rows and the request log:

1. Step 1 was saved with chart no **`123456`** and SSN **`123-45-6789`** — both values are already on patient
   **83882** (and the SSN on 8 more patients). The backend's `_is_strong()` treats a lone SSN *or* chart-no
   match as a certain duplicate.
2. Finish → `POST /patients/register` → **409 `duplicate_patient`**. The frontend never sent `force_create`,
   and its "resilient" wrapper treated *every* error as "endpoint down" and dropped into the chained fallback:
   `POST /patients` (no duplicate check → 201) followed by one request per alert / answer / recall.
3. Each questionnaire answer whose derived `question_code` is longer than 50 characters hit
   `patient_questionnaire_responses.question_code VARCHAR(50)` → Postgres `StringDataRightTruncation` →
   **HTTP 500**. Exactly the 12 unique codes in the DevTools capture are the 12 legacy questions whose slug is
   51–60 characters (the frontend slugged to 60). The other 39 answers (≤ 50 chars) saved.
4. Side effects of step 2: the **non-self responsible party was silently dropped** (`responsible_party_id`
   NULL — only the composite knows how to create a guarantor), and the whole intake took ~2 minutes
   (patient 21:35:10 → last recall 21:37:29).

So the visible symptom (12 failed POSTs) is GAP-AP-20, but the reason the frontend was on that code path at all
is GAP-AP-21.

---

## 2. GAP-AP-20 — `question_code` / `alert_code` are `VARCHAR(50)`, overflow = HTTP 500 🔴

**Where:** `app/db/models/patients.py`

```python
class PatientMedicalAlert(...):
    alert_code: Mapped[str] = mapped_column(String(50))     # line 471
class PatientQuestionnaireResponse(...):
    question_code: Mapped[str] = mapped_column(String(50))  # line 506
```

`PatientQuestionnaireResponseCreate`, `QuestionnaireResponseIn`, `PatientMedicalAlertCreate` and
`MedicalAlertIn` expose the field as a plain `string` — **no `maxLength`** in `openapi.json`, so neither the
generated client nor a human reading the spec can know the limit.

**Repro (patient 83928, before the FE fix):**

```bash
# 51-char code → 500
curl -s -X POST http://127.0.0.1:8000/api/v1/patient-questionnaire-responses \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"patient_id":83928,"questionnaire_type":"dental",
       "question_code":"do_you_have_difficulty_in_opening_your_mouth_widely","answer":"yes"}'
# → HTTP 500 {"error":{"code":"internal_error","message":"An unexpected error occurred","details":null}}

# same request with a 50-char code → 201
```

Through `POST /patients/register` the same overflow surfaces as a 500 for the **entire** registration
(patient, guarantor, 88 alerts, opening balance all rolled back) with no hint which field was at fault.

**Affected catalog rows (frontend-derived codes, 51–60 chars):** 9 dental questions + 3 medical questions
(list in `docs/patients/legacy_catalog_seed.json` — every `key1` is now ≤ 50). No medical-alert code exceeds
50, but the column has the same latent limit and tenant-seeded alert catalogs could.

**Frontend workaround shipped (this branch):** `CATALOG_CODE_MAX_LENGTH = 50` in
`src/features/add-patient/legacyCatalogs.ts` — `toCode()` now clamps at 50 (all 50-char prefixes verified
unique per catalog; no rows with the old 60-char codes exist in the DB since they could never be written).
The seed export (`scripts/export-catalog-seed.mjs`, `legacy_catalog_seed.json`) was regenerated to match.
The Medical History screen shares `toCode()` and is therefore fixed by the same change.

**Ask:**
1. Add `max_length=50` (or whatever the column becomes) to the four Pydantic schemas so overflow is a
   **422 with the field path**, never a 500.
2. Preferably widen both columns to `VARCHAR(100)` — legacy questions are long and derived codes need room —
   and keep the FE constant in sync (it is one number).
3. When seeding DENTQUEST / MEDQUEST / MEDALERT (LEG-1), use the regenerated `legacy_catalog_seed.json`
   (codes are now 50-char) so stored answers key identically to what the UI sends.

---

## 3. GAP-AP-21 — Duplicate guard: 409 on register, nothing on `POST /patients` 🟠

**Where:** `app/services/patient_intake_service.py:116` calls `find_strong_duplicates()` unless
`force_create`; `app/services/patient_extra_service.py:_is_strong()` returns `True` for `"ssn" in match_on or
"chart_no" in match_on` on its own. `POST /patients` (generic registry CRUD) calls nothing.

**Observed:**

* `POST /patients/register` with SSN `123456789` → **409** listing 9 candidates
  (`match_on: ["ssn"], is_strong: true, match_score: 40`). The same happens for chart no `123456`.
* `POST /patients` with the identical patient body → **201**. The guard is trivially bypassed by the endpoint
  the frontend used as a fallback — and by any client that doesn't use the composite.
* The 409 body is well-formed (`error.code = "duplicate_patient"`, `error.details.candidates[]` with office /
  email / provider) — that part is good and is now consumed by the UI.

**Frontend fix shipped (this branch):**
* `registerPatientResilient` no longer falls back on **any 4xx**. A 409 `duplicate_patient` is raised as
  `DuplicatePatientError`; the wizard shows the existing "Identical Patients Found" modal with the server's
  candidates (now including Office / Email / Provider columns and the matched fields, e.g. `Match 40% (ssn)`)
  and **"Create Anyway"** re-submits the *same* atomic request with `force_create: true`. Verified: Quick Save
  → 409 → Create Anyway → `POST /patients/register` 201 (patient 83932); no `POST /patients` was issued.
* The chained fallback (still used for 5xx / network failures) now **replays the responsible party**
  (`POST /responsible-parties` + `PATCH /patients/{id}` `responsible_party_id`) instead of dropping it, and
  reports a warning if that fails.

**Ask:**
1. Run the same `find_strong_duplicates` guard (with `force_create`) on `POST /patients`, or document that
   the plain endpoint is unguarded and intended for imports only.
2. Reconsider `_is_strong` for SSN-only / chart-no-only matches: in this DB the placeholder SSN `123456789`
   and chart `123456` are shared by many records, so one shared placeholder blocks every registration. At
   minimum ignore obviously synthetic values (all-same digit, `123456789`, empty) or require
   SSN **and** (DOB or last name).
3. Keep the 409 body shape stable — the UI now depends on `error.details.candidates[]`.

---

## 4. GAP-AP-22 — Child resources are ~1.2 s per request; no bulk endpoints 🟠

Measured on the fallback path for patient 83929 (single browser tab, backend on localhost, DB remote):

| Requests | Count | Wall time |
|---|---|---|
| `POST /patient-medical-alerts` | 89 | ~105 s |
| `POST /patient-questionnaire-responses` | 48 | ~55 s |
| recalls + subscribers + insurance + emergency contact | 8 | ~10 s |
| **Total after `POST /patients`** | 145 | **~3 min** (patient `created_at` 22:59:12 → last insurance row 23:02:15) |

The atomic composite does the same work in **~5 s** (83931: 89 alerts + 51 answers + recall + RP + balance in
one 201). The Medical History screen has the same problem on first save (one POST per row).

**Ask:** either
* `POST /patient-medical-alerts/bulk` and `POST /patient-questionnaire-responses/bulk` (array in, array out,
  single transaction), **or**
* make the composite complete (GAP-AP-23 / -24) so nothing needs the per-row path at registration time, and
  add a `PUT /patients/{id}/medical-history` style replace endpoint for the MH screen (MH-xx already asks).

Also worth a look server-side: each of these POSTs is a trivial insert; 1.2 s suggests per-request work
(tenant lookups / audit / FK validation) that could be cached.

---

## 5. GAP-AP-23 — `RecallIn` lacks `interval_unit` / `scheduled_date` / `scheduled_time` 🟡

Re-flag of **LEG-17**. `PatientRecallCreate` has the three LEG-8 columns; the composite's `RecallIn` does not,
so the wizard must persist recalls through `POST /patient-recalls` **after** the register call (verified:
83929's three recalls carry `interval_unit: "year"`, `scheduled_time: "09:30"` only because they went the
standalone route). If the register succeeds and a later recall POST fails, the patient exists without the
recall and the user only gets a warning.

**Ask:** add the three fields to `RecallIn` (same types as `PatientRecallCreate`).

---

## 6. GAP-AP-24 — Insurance is outside the composite 🟡

`RegisterRequest` has no insurance section; each coverage slot is saved as `POST /insurance-subscribers` →
`POST /patient-insurance` after registration. Consequences: not atomic (a subscriber can be orphaned if the
link fails — this was BUG-3's side effect), and two extra round-trips per slot.

**Ask:** `insurance?: Array<{ subscriber: InsuranceSubscriberCreate (minus patient), link:
PatientInsuranceCreate (minus patient_id / subscriber_id) }>` on `RegisterRequest`, created inside the same
transaction, ids returned on `RegisterResponse`.

Verified positive: with both Primary Dental **and** Primary Medical selected, both `patient_insurance` rows
were created (`legacy_plan_type` D + M, `insurance_type` primary) — the old `(patient_id, insurance_type)`
unique constraint (BUG-3) is fixed.

---

## 7. GAP-AP-25 — `resp_party_rel` definitions are seeded twice 🟡

```
GET /api/v1/definitions?group_code=resp_party_rel&size=200  → 13 rows
 6816 self     Self       sort 0
 6817 spouse   Spouse     sort 1
 6818 parent   Parent     sort 2
 6819 guardian Guardian   sort 3
 6820 child    Child      sort 4
 6821 other    Other      sort 5
12513 S        Self       sort 6
12514 SP       Spouse     sort 7
12515 P        Parent     sort 8
12516 G        Guardian   sort 9
12517 C        Child      sort 10
12518 D        Dependent  sort 11
12519 O        Other      sort 12
```

The Add-Patient "Rel. to Resp" dropdown therefore shows `Self, Spouse, Parent, Guardian, Child, Other, Self,
Spouse, Parent, Guardian, Child, Dependent, Other`. Two key schemes also mean `responsible_party_relationship`
values are not comparable across records (`spouse` vs `SP` vs the label `Spouse` that the wizard currently
stores).

**Ask:** deactivate one set (keep the code-style `S/SP/P/G/C/D/O` set if legacy parity matters — it has
`Dependent`), and state which value the patient column should hold (key or description).

---

## 8. GAP-AP-26 — 500 responses carry no diagnostic 🟡

Every server-side failure comes back as
`{"error":{"code":"internal_error","message":"An unexpected error occurred","details":null}}`. For the
register composite this hides *which* of 140 rows overflowed a column, and a client cannot distinguish "bad
payload" (do not retry) from "server down" (retry / fall back). The frontend's fallback logic was written
around exactly that ambiguity.

**Ask:** map SQLAlchemy `DataError` → 422 (`value_too_long`, with table/column), `IntegrityError` → 409
(`constraint`, with the constraint name). Keep 500 for the genuinely unexpected.

---

## 9. Observations (no action required, FYI)

* **OBS-1** — `GET /insurance-carriers?search=Aetna` returns 25 rows of which 9 are literally named
  "Aetna" (payer `60054` / `06126`); carrier and plan searches take 8–10 s each. Plan lists for one carrier
  contain many duplicate group numbers. Data hygiene from the migration.
* `MedicalAlertIn.response` is an unconstrained `string` in the composite but a `yes|no|unknown` enum on
  `PatientMedicalAlertCreate` (already noted in the Medical History report).
* `PatientRead` has no `sex` key — the value is under `gender`; `home_phone` is under `phone`; free-text
  notes under `patient_notes`. All fine, just naming asymmetries with `PatientCreate`.
* Backend token lifetime (1 h) is shorter than one slow fallback run plus verification; not a bug, but it
  makes the ~3 min chained path feel like a hang when it expires mid-way.

---

## 10. Frontend changes shipped with this report (for completeness)

| File | Change |
|---|---|
| `src/features/add-patient/legacyCatalogs.ts` | `CATALOG_CODE_MAX_LENGTH = 50`; `toCode()` clamps at 50 (was 60) |
| `scripts/export-catalog-seed.mjs`, `docs/patients/legacy_catalog_seed.json` | seed regenerated with 50-char codes (12 rows changed) |
| `src/services/patientApi.ts` | `registerPatientResilient`: 409 `duplicate_patient` → `DuplicatePatientError`; no fallback on 4xx; fallback replays the responsible party |
| `src/services/patient.service.ts`, `src/types/patient.ts` | `DuplicatePatient` view-model → snake_case (`dob`, `home_office_short_id`, `patient_id`), shared `toDuplicatePatient()` now maps office / email / provider / `match_on` |
| `src/components/pages/AddNewPatient.tsx` | one `runRegistration(full, forceCreate)` for Quick Save + Finish; 409 opens the duplicate modal; "Create Anyway" retries with `force_create`; modal columns no longer blank |
| `src/features/add-patient/wizardModel.ts` | subscriber `sub_phone` + `marital_status` were collected but never sent (verified null on subscriber 65314) |

Verification: `npx tsc -b` clean; `npx eslint` on the touched files reports only two pre-existing unused-var
warnings; UI runs 83929 / 83932 and API run 83931 as described above.

---

## 11. What was verified working end-to-end (patient 83929 unless noted)

* Step 1: every field round-trips — title, preferred name, pronouns, middle name, address 1/2, city/state/zip,
  3 phones, email, contact pref (`cell_phone`), marital, `gender`, guardian name/phone, SSN, driver license,
  Medi ID, student + school, referral type / referred by / referral-to date, notes, HIPAA note, all five
  opening-balance buckets (`total 190.75`), patient types `EF, OR, SS` (+ `patient_type: Ortho`), flags
  `is_active / assign_benefits / hipaa_agreement / send_statements / add_to_quickfill`, fee schedule 25,
  provider `PRV-100`, hygienist `PRV-141`, `home_office_id 1`, `chart_no` auto-generated (`83929`),
  `first_visit` / `last_visit`.
* Responsible party: non-self guarantor created **and linked** via the composite (83931 → RP id 3,
  `resp_party_type IN`, `send_statements true`); via the fallback it is now replayed (was lost on 83929).
* Insurance: Primary Dental (self subscriber, deductible/max remaining, Dentical share month/year/amount/
  unused) **and** Primary Medical (spouse subscriber with name/DOB/sex/address/member id/effective date/notes)
  both saved.
* Medical alerts: 88/88 answered via "No to all", 3 Yes preserved, comments row `ADDITIONAL_COMMENTS`.
* Questionnaires: 27 dental + 21 medical rows including all 12 previously-unsavable long questions; emergency
  contact row created; the "Women Only" block and free-text/date questions persist.
* Recalls: 3 rows with `interval_unit`, `scheduled_date`, `scheduled_time`, `recall_type`, `procedure_code`.
* Duplicate flow: Check Patient modal (DOB-only 25 % matches) and server 409 modal both render office / email
  / provider columns.
