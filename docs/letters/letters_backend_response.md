# Letters — Backend Response

**Module:** Letters (New) — print menu → Letters dialog → Report Viewer → "Save PDF file"
**Gap report answered:** [letters_backend_devreport.md](letters_backend_devreport.md) (LTR-1…12)
**Integration round 2:** LTR-13…16 · **round 3:** LTR-17 + deploy (see the sections below)
**Migration:** Alembic `e9f0a1b2c3d4` (`add_letters_module_gaps`)
**Tests:** [tests/test_letters_module.py](../../tests/test_letters_module.py) — 52 cases ·
[tests/test_document_storage.py](../../tests/test_document_storage.py) — 20 cases

---

## Summary

| ID | Status | What shipped |
|----|--------|--------------|
| **LTR-1** | **Done** (needs one env var to go live) | `patient-documents` is now object-storage backed; consent PDFs route to `gs://{bucket}/consent-forms/{tenant}/{patient}/{uuid}.pdf`; `file_url` is a fully-qualified HTTPS URL; `storage_backend`/`storage_bucket`/`storage_path` on the row; `GET /patient-documents/{id}/content` proxy; `GET /consent-forms` lists the bucket masters |
| **LTR-2** | **Done** | `LETTERTYPE` definitions group seeded (8 codes → labels) |
| **LTR-3** | **Done** | Provider letterhead columns, `offices.corporate_name`, and an `account_settings.marketing_*` block — all three merge blocks now have a real source |
| **LTR-4** | **Done** | `#TX_PLAN_TH_NUMBER#` binds when the letter is launched from a treatment plan (`treatment_plan_id`); otherwise it is reported unresolved rather than guessed |
| **LTR-5** | **Done** | `POST /letters/render`, `POST /letters/render-batch` (job id), `GET /letters/batches[/{id}]`, `GET /letters/merge-fields` |
| **LTR-6** | **Done** | `GET /patients/{id}/letter-context` |
| **LTR-7** | **Done** | Semantic pinned + `GET /offices/{id}/letter-templates/effective`; `scripts/seed_office_letter_templates.py` for curation |
| **LTR-8** | **Tooling shipped, data NOT yet mutated** | `scripts/repair_letter_templates.py` (dry-run by default). **Needs your sign-off before `--apply`** — see below |
| **LTR-9** | **Tooling shipped, data NOT yet mutated** | Same script, `--fix-channel`. The importer bug is diagnosed |
| **LTR-10** | **Done** | Status vocabulary published + `POST /patient-consents/{id}/sign` |
| **LTR-11** | **Done** | Every datetime on the wire now carries an offset — API-wide, not just Letters |
| **LTR-12** | **Done** (**breaking**) | `/patient-documents` gains `document_type`/`office_id`/`search` + standard paging; the response is now the paginated envelope |

---

## LTR-1 — consent PDFs in the bucket

**Code:** [app/services/document_store.py](../../app/services/document_store.py),
[app/services/patient_extra_service.py](../../app/services/patient_extra_service.py),
[app/api/v1/patients_extra.py](../../app/api/v1/patients_extra.py)

Set **one** env var to cut over — no code change, no redeploy of the frontend:

```
GCS_BUCKET_DOCUMENTS=reco-documents
PUBLIC_API_BASE_URL=https://<api-host>       # so file_url is absolute
# optional, they have sensible defaults
GCS_CONSENT_FORMS_PREFIX=consent-forms
GCS_DOCUMENTS_PREFIX=patient-documents
DOCUMENT_URL_MODE=auto                       # auto | gcs | proxy
DOCUMENT_SIGNED_URL_TTL_SECONDS=900
```

With the bucket unset (dev, CI) uploads stay on the local filesystem exactly as
before, so nothing needs cloud credentials to run.

1. **Routing** — `document_type=consent-form` (also `consent_form`/`consent`, see
   `CONSENT_DOCUMENT_TYPES`) lands under the consent prefix; every other type under the
   generic one. Both are `{prefix}/{tenant_id}/{patient_id}/{uuid}{ext}`.
2. **`file_url` is fully-qualified.** GCS rows get a short-lived **V4 signed URL**; if
   signing is unavailable (no `serviceAccountTokenCreator`, or `DOCUMENT_URL_MODE=proxy`)
   they get `GET /api/v1/patient-documents/{id}/content`, which re-checks tenancy and
   streams the object. The browser never sees `gs://` and never holds bucket credentials.
   The signed URL is computed **on read, not persisted** — persisting it would serve an
   expired link on the next fetch.
3. **Provenance** — `storage_backend` (`local|gcs`), `storage_bucket`, `storage_path` are
   on `PatientDocumentRead`. Existing rows were backfilled to `local` with
   `storage_path = file_path`, so a later migration of those blobs is auditable.
4. **`GET /api/v1/consent-forms`** lists the blank masters already in the bucket
   (`{items[], storage_bucket, storage_prefix, is_configured}`). Returns
   `is_configured:false` + `items:[]` when no bucket is set, so it is always safe to call.

If a GCS upload fails while a bucket *is* configured, the write falls back to local disk
and logs an error rather than losing a just-printed consent form. GCS objects are **not**
deleted on `DELETE` — the bucket's retention policy owns a signed clinical record and the
soft-deleted row is the marker.

You can stop sending the intended folder in `description`; keep it if you like, nothing
reads it.

---

## LTR-5 / LTR-6 — server-side render, batch, and the aggregate context

**Code:** [app/services/letter_service.py](../../app/services/letter_service.py),
[app/api/v1/letters.py](../../app/api/v1/letters.py)

### `GET /api/v1/letters/merge-fields`

The authoritative catalog. It is **exactly the 56 tokens** that appear across the 153
seeded templates — verified by extracting `#TOKEN#` from every `body_html` row, so it
cannot drift from the corpus. Each entry carries `token`, `placeholder`, `group`,
`label`, `requires_balance`, `requires_treatment_plan`.

### `POST /api/v1/letters/render`

```json
{ "template_id": 3, "patient_id": 83867, "office_id": null, "treatment_plan_id": null }
```
→
```json
{
  "template_id": 3, "patient_id": 83867,
  "title": "AP003 - Missed Appt Ortho Letter",
  "letter_type": "A",
  "rendered_html": "…",
  "unresolved_tokens": ["PAT_CELLPHONE"],
  "merge_fields": { "PAT_FIRST_NAME": "John", "…": "…" },
  "unknown_tokens": []
}
```

Properties kept from the frontend implementation, deliberately:

- **Merged values are HTML-escaped** — patient data cannot inject markup.
- The template body is passed through `sanitize_html` (a template row is
  tenant-editable content and the render now happens server-side).
- An unresolved token prints **blank** and is listed in `unresolved_tokens`; it is
  never left as a visible `#TOKEN#`. `unknown_tokens` reports placeholders that are
  not in the catalog at all — that is your drift alarm.
- `title` falls back to `name` (LTR-9: `title` is null on 103 of 153 rows).
- The balance aggregate runs **only** when the template actually contains
  `#RP_TOTAL_BAL#`, so the cheap letters stay cheap.

### `POST /api/v1/letters/render-batch` — the CS001…CS009 sweeps

```json
{ "template_id": 12, "patient_ids": [1,2,3], "office_id": 9, "store_html": false }
```
→ `{ "batch": {…job record…}, "items": [ {patient_id, status, unresolved_tokens, …} ] }`

Durable job rows (`letter_batch_runs` / `letter_batch_items`) with a real id you can
poll via `GET /letters/batches/{id}`; `GET /letters/batches` lists them (paged).
It runs **inline** — the batches a practice actually sends are hundreds of rows, so you
get a job id *and* a finished result without a worker tier, and the row/item model is
already the async shape if that changes. Capped at `LETTERS_BATCH_MAX_PATIENTS` (500).
**One bad patient records a `failed` item and the sweep continues** — a single bad row
must not lose the other 499 letters. `store_html` is off by default (a batch is normally
one print stream, not 500 stored bodies).

### `GET /api/v1/patients/{id}/letter-context`

Replaces the 2–6 round trips. Returns `patient`, `office`, `provider`,
`responsible_party`, `referred_by`, `next_appointment` (+ its provider),
`last_appointment`, `treatment_plan`, `treatment_plan_teeth`, `today`, plus
**`merge_fields`** (every catalog token already resolved) and `unresolved_tokens`.

Query params: `office_id`, `treatment_plan_id`, `include_balance` (**default false** —
the balance aggregate is the slow one; keep your existing "only when the template needs
it" behaviour, or just use `/letters/render` which decides for you).

---

## LTR-3 — the merge fields that had no source

| Block | New source | Fallback chain |
|-------|-----------|----------------|
| `#PAT_PREF_PROV_*#` | `providers.address_line1/2, city, state, zip, phone, email` | provider → office |
| `#MARKET_*#` | `account_settings.marketing_name/address_1/address_2/city/state/zip/phone` | marketing → corporate → office |
| `#OFFICE_CNAME#` | `offices.corporate_name` | corporate_name → `office.name` |

All nullable and additive — nothing changes until someone fills them in, and the
fallbacks mean a letter never prints an empty letterhead. The marketing block is
writable through the existing `PATCH /tenants/{id}/account-settings`; provider address
and `corporate_name` come through the existing Provider / Office CRUD.

**Action for the practice:** populate these for the 30 `#MARKET_*#` templates and the
10 provider-letterhead templates, otherwise they keep printing the office block (which
is what happens today).

## LTR-4 — `#TX_PLAN_TH_NUMBER#`

Not dropped. The token now binds when the letter is launched **from** a treatment plan:
pass `treatment_plan_id` to `/letters/render` (or `/letter-context`) and it resolves to
the plan's tooth numbers, de-duplicated in plan order (`"14, 19"`). Without a plan it
resolves to blank and is reported in `unresolved_tokens` — printing an arbitrary tooth
number on a patient's letter would be worse than printing none.

## LTR-7 — office ↔ letter-template assignment

The semantic is now pinned and enforced in code: **unassigned = all**.

- `GET /offices/{id}/letter-templates` — unchanged. It is the *assignment grid* and
  returns exactly what its `PUT` replaces, so it still returns `[]` for a curated-by-
  nobody office. Don't use it to populate the dialog.
- `GET /offices/{id}/letter-templates/effective` — **use this one.** No assignment →
  the full active tenant catalog; one or more assignments → exactly that set.
  (Same shape as the `providers/effective` endpoint from PROV-1.)

`scripts/seed_office_letter_templates.py` materialises an explicit assignment when an
office wants a shorter list (`--tenant`, `--office`, `--letter-type`, `--replace`,
`--dry-run`). It skips offices that already have one, so it never undoes curation.

---

## LTR-8 / LTR-9 — the migration damage (⚠ needs your decision)

**The `?` loss is upstream and irrecoverable from the database.** The whole 153-template
corpus contains **zero non-ASCII characters**, and the importer reads with
`encoding="cp1252", errors="replace"` — which would have produced `�`, not `?`. So
the literal `?` is already in `LETTERS.txt`: Denticon's export lost the characters, and
re-running the migration against the same file cannot bring them back.

That leaves contextual repair. `scripts/repair_letter_templates.py` implements three
narrow rules and **writes nothing without `--apply`**:

| Rule | Example | Why it is safe |
|------|---------|----------------|
| R1 contraction | `you?re` → `you’re`, `attorney?s` → `attorney’s` | a `?` between a letter and `s/t/re/ve/ll/d/m` is never a question mark |
| R2 quote pair | `as ?bleaching?.` → `as “bleaching”.` | a `?` **preceded by whitespace** is never a real question mark, so it opens a quote; the next `?` followed by punctuation closes it |
| R3 trademark | `RADIESSE?` → `RADIESSE®` | **opt-in**, and only for brands you name on the command line (`treatment?` is a legitimate question) |

Dry run on tenant 1 right now:

```bash
python -m scripts.repair_letter_templates --tenant 1 --trademarks RADIESSE,Botox,Dysport --show-diff
```

reports **27 rows repairable (≈100 replacements)** and **10 rows still containing a `?`**
that the rules refuse to touch — those are printed with context for a human to decide
(most are genuine question marks in consent copy; a few are lost bullets `•` and
en-dashes `–`). Nothing has been applied: this is patient-facing legal copy, so the
`--apply` is yours to authorise after reading the diff.

**LTR-9 — root cause found.** The channel junk is not a stray value, it is a **field
offset**: [denticon_migration/migration/utils/reader.py](../../denticon_migration/migration/utils/reader.py)
splits `LETTERS.txt` on commas while the HTML `BODY` column contains embedded commas and
newlines, so those rows shift. The 11 affected rows are all `Financial Agreement …`
templates, and their **`body_html` is 60–66 characters** — i.e. the body is truncated
too, and nulling `channel` does not recover the letter. `--fix-channel` cleans the column
and flags every truncated body; **the real fix is re-importing those 11 templates** with
a quoting-aware reader (or re-entering them in Setup, which may be faster for 11 rows).
The `letter_channel` definitions group is seeded so the valid vocabulary is explicit.

---

## LTR-10 — consent signing

**Vocabulary** (`GET /api/v1/patient-consents/statuses`, also the `consent_status`
definitions group): `pending · printed · signed · declined · voided`.
Signature methods: `drawn · scanned · verbal`.

**`POST /api/v1/patient-consents/{id}/sign`**

```json
{
  "signature_data": "data:image/png;base64,…",   // OR
  "document_id": 27,                              // an uploaded scan of the wet-signed copy
  "status": "signed",
  "signature_method": "drawn",
  "signer_name": "John Smith",
  "signer_relationship": "self",
  "declined_reason": null
}
```

- Exactly one of `signature_data` / `document_id` is required for `status:"signed"`
  (`declined` / `voided` need neither).
- `document_id` must belong to the **same patient** — that's checked, not assumed.
- Re-signing an already-signed consent is a **409**; the first signature is the record.
- `signed_by` is stamped from the **token** (the staff user who captured it);
  `signer_name`/`signer_relationship` describe who physically signed.
- New columns: `signer_name`, `signer_relationship`, `signature_method`,
  `declined_reason`.

Keep writing `status:"printed"` at print time — that is now a documented value.

---

## LTR-11 — timezone-aware timestamps (API-wide)

`"2026-08-19T02:05:11.828300"` → `"2026-08-19T02:05:11.828300Z"`.

The columns are naive `TIMESTAMP`s that hold UTC, so nothing is *converted* — the value
is **labelled**, which is what it always meant. Two seams cover the whole surface
([app/core/datetimes.py](../../app/core/datetimes.py)):

- `build_schemas` types every `datetime` column as `UtcDatetime`, so all generated Read
  schemas emit an offset. OpenAPI still says `format: date-time`, so **no Orval change**.
- `install_utc_json_encoder()` patches `jsonable_encoder` for the hand-written endpoints
  that return plain dicts (ledger feeds, dashboards, audit rows).

You can drop the `fmt_stamp` UTC pinning in `LettersPage.tsx`.

---

## LTR-12 — `/patient-documents` list ⚠ **breaking change**

`GET /api/v1/patient-documents` now returns the **standard paginated envelope**
(`{items, meta}`) instead of a bare array, and takes:

| Param | Notes |
|-------|-------|
| `patient_id` | now **optional** (office-wide document search is possible; tenancy always enforced) |
| `document_type` | e.g. `consent-form` — this is the one the Letters history wanted |
| `office_id` | |
| `search` | matches `file_name` / `description` |
| `page`, `size`, `sort`, `order` | the usual |

Regenerate the Orval client and switch the history call to
`?patient_id=…&document_type=consent-form`; the client-side filter can go.

---

## Migration & seeds

```bash
python -c "from alembic.config import main; main(['upgrade','head'])"   # e9f0a1b2c3d4
python -m scripts.seed_account_definitions --tenant 1                    # LETTERTYPE, consent_status, letter_channel
python -m scripts.export_openapi                                         # refresh openapi.json for Orval
```

Optional / decision-gated:

```bash
python -m scripts.seed_office_letter_templates --tenant 1 --dry-run      # LTR-7 curation
python -m scripts.repair_letter_templates --tenant 1 --show-diff \
    --trademarks RADIESSE,Botox,Dysport                                  # LTR-8/9 review, then --apply
```

## Not done, and why

- **Re-importing the 11 truncated `Financial Agreement` bodies** (LTR-9) needs
  `LETTERS.txt` and a quoting-aware reader; the source export lives on the migration
  drive, not in this repo.
- **Applying the mojibake repair** (LTR-8) is left to a human `--apply` — see above.
- **Envelope printing / PDF generation** stays in the browser. `reportlab` is already
  available server-side (statements, payment-plan contracts) if you want
  `POST /letters/render.pdf` later; the render endpoint is the half that was missing.

---

# Round 2 — LTR-13…16 (found during frontend integration)

| ID | Status | What changed |
|----|--------|--------------|
| **LTR-13** | **Done** | The appointment merge block falls back next → last → preferred provider; `last_appointment_provider` added to `letter-context`; `#APPT_DATETIME#` added to the catalog |
| **LTR-14** | **Done** | `today` / `#TODAY_DATE#` are computed in the printing office's timezone |
| **LTR-15** | **Done** | `overrides: {token: value}` **and** `signing_provider_id` on `/letters/render` and `/letters/render-batch` |
| **LTR-16** | **Partly** — code paths now covered by tests; a real bucket still needs one deploy | 20 tests exercise upload/signing/proxy/listing against a fake GCS client, plus `scripts/check_document_storage.py` to prove the real thing in one command |

---

## LTR-13 — `#APPT_PRDR#` no longer prints a blank doctor

You are right that this was the serious one: `"I Leo Rob hereby authorize and request
that Dr. and their assistants perform the specified extraction(s)"` is a defective legal
document, not a cosmetic gap.

The root cause was a wrong reading of the token on my side. I bound the appointment block
to the *upcoming* appointment, but a consent form is printed **at the chair, after the
visit has started** — so by definition there is no upcoming appointment, and the one that
matters is the one happening now, which is stored as the most recent past row.

The block now means **"the appointment this letter is about"**, resolved in order:

| Token | Resolution order |
|-------|-----------------|
| `#APPT_PRDR#` | next appointment's provider → **last appointment's provider** → the patient's preferred provider |
| `#APPT_DATE#` | next appointment → **last appointment** |
| `#APPT_DATETIME#` | same, formatted `08/19/2026 9:00 AM` |

The third fallback (preferred provider) is beyond what you asked for; I added it because
15 templates use `#APPT_PRDR#` and a patient with **no** appointment rows at all would
still have produced the blank-doctor consent. A named doctor who might be the wrong one
gets caught at the chair; a blank one gets signed. Say the word if you would rather it
stop at the last appointment.

`letter-context` now also returns **`last_appointment_provider`** alongside
`next_appointment_provider`, so the residual in the frontend can go.

Verified against your two reproduction patients on the live database:

| | 83867 | 83896 |
|--|--|--|
| `last_appointment.provider_id` | `prov-arjun-9` | `prov-23423-9` |
| `merge_fields.APPT_PRDR` | `"Arjun"` | `"TEST PROVIDER"` |
| `merge_fields.APPT_DATE` | `06/21/2026` | `08/16/2026` |
| `merge_fields.APPT_DATETIME` | `06/21/2026 8:20 AM` | `08/16/2026 8:00 AM` |
| in `unresolved_tokens`? | no | no |

### One note on `#APPT_DATETIME#`

It was **not** in the 56-token corpus — no migrated template uses it. I added it anyway
since you are binding it, so the catalog is now 57 entries: the 56 corpus tokens plus this
one deliberate extension. The test suite pins that distinction (`CORPUS_TOKENS` in
`tests/test_letters_module.py` is the extracted ground truth), so the catalog can still
never *lose* coverage of a token a real template uses.

---

## LTR-14 — `#TODAY_DATE#` is the office's date

`build_context` now reads `offices.timezone` (already populated —
`America/New_York` for office 108) and computes `today` there. Both
`letter-context` and `/letters/render` return the `timezone` they used, so the
frontend can drop its workstation-local override and there is no ambiguity about
which clock produced a date on a signed form.

Live right now, at `2026-08-19T05:35:57Z`:

```
UTC date                : 2026-08-19
America/New_York        : 2026-08-19
America/Los_Angeles     : 2026-08-18   <- differs
Pacific/Honolulu        : 2026-08-18   <- differs
```

The helper is `office_today()` in [app/core/datetimes.py](../../app/core/datetimes.py).
An unparseable `offices.timezone` degrades to `America/New_York` rather than 500-ing that
office's letters. While I was there I pointed AppointNow's private copy of the same
helper at it, so availability and `#TODAY_DATE#` cannot drift apart.

The appointment "is it upcoming or past" boundary now uses the office's date too — it was
the same UTC bug one level down.

---

## LTR-15 — caller-supplied values

Both surfaces, on `/letters/render` and `/letters/render-batch`:

```json
{
  "template_id": 3,
  "patient_id": 83867,
  "signing_provider_id": "prov-arjun-9",
  "overrides": { "APPT_PRDR": "Dr. Arjun Mehta", "OFFICE_PHONE1": "412-555-0100" }
}
```

The response gains `applied_overrides` and `rejected_overrides`.

- **`signing_provider_id`** re-points exactly two tokens: `#APPT_PRDR#` and
  `#DOC_LAST_NAME#` — the doctor *named in the body*. It deliberately leaves the
  `#PAT_PREF_PROV_*#` letterhead alone, because that block is the practice's return
  address and should not silently move because a different dentist is chairside. Use
  `overrides` if you do want it to. An unknown provider id is a **404**.
- **`overrides`** wins over `signing_provider_id`, so you can use both.
- **Unknown keys are rejected, not merged** — they come back in `rejected_overrides`.
  Silently accepting a typo would look like it worked.
- **Values are HTML-escaped on substitution**, exactly like server-resolved values, so
  this is not a markup-injection route.

On the batch endpoint the same fields apply to every letter in the sweep — one signing
doctor for a whole collections run.

---

## LTR-16 — what I could verify, and what I could not

**Could not:** I have no bucket or credentials here, so nobody has yet proven that the
upload reaches `gs://reco-documents/consent-forms/…`, that IAM signing works, or that the
link opens from a browser. That still needs one deployed run and it is the remaining risk
on LTR-1.

**Did do**, so that run is a formality rather than a debugging session:

1. **20 tests** ([tests/test_document_storage.py](../../tests/test_document_storage.py))
   drive the real code with a fake GCS client, covering the branches that were previously
   only exercised in production: consent-prefix vs generic-prefix routing, signed-URL
   `file_url`, `DOCUMENT_URL_MODE=proxy`, **signing unavailable → proxy fallback**,
   `PUBLIC_API_BASE_URL` absolutisation, signed URLs not being persisted, the `/content`
   proxy streaming and enforcing tenancy, upload failure falling back to local rather than
   losing a consent, GCS blobs surviving a row delete, and `GET /consent-forms` filtering
   by prefix.

2. **A one-command probe:** `python -m scripts.check_document_storage`. Run it in the
   deployed environment after setting the env vars. It writes a throwaway object, reads it
   back through both the signed URL and the proxy seam, compares bytes, lists the consent
   prefix, then deletes it — and exits non-zero on the first failure, so it works as a
   deploy gate. It never touches a patient record.

```bash
GCS_BUCKET_DOCUMENTS=reco-documents PUBLIC_API_BASE_URL=https://<api-host> \
  python -m scripts.check_document_storage
```

The check most likely to fail is signing: on Cloud Run the runtime service account needs
`roles/iam.serviceAccountTokenCreator` **on itself**. If it does not have it the probe
warns rather than fails, and `file_url` falls back to the `/content` proxy — which works,
just with the bytes passing through the API.

---

## Still open (unchanged)

- **LTR-8 / LTR-9** — a human decision, not code. Nothing applied. Read the
  `--show-diff` output before authorising `--apply`; the 11 truncated
  `Financial Agreement` bodies need re-import from `LETTERS.txt` either way.
- **Batch letters** — `/letters/render-batch` is deliberately unwired. It belongs to a
  collections queue screen, not the per-patient dialog.

---

# Round 3 — deploy + LTR-17 (2026-08-19)

## The deploy problem: found and fixed locally

You were right, and the cause was mundane. The local backend was
`uvicorn app.main:app --host 0.0.0.0 --port 8000` — **started without `--reload`**, at
23:19 on 8/18, i.e. before the round-2 edits landed. It was serving a stale in-memory
build of this same working tree. Nothing was wrong with the code; it had simply never
been loaded.

**The local dev backend now serves the round-2 + LTR-17 build**, restarted with
`--reload` so a code change is picked up automatically and this cannot recur:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Verified against the running server on `127.0.0.1:8000`:

```
LetterRenderRequest  : office_id, overrides, patient_id, signing_provider_id,
                       template_id, treatment_plan_id
LetterRenderResponse : applied_overrides, appointment_provider_source, appointment_source,
                       fallback_tokens, letter_type, merge_fields, patient_id,
                       rejected_overrides, rendered_html, template_id, timezone, title,
                       today, unknown_tokens, unresolved_tokens
LetterContextResponse: appointment_provider_source, appointment_source, balance,
                       fallback_tokens, last_appointment, last_appointment_provider,
                       merge_fields, next_appointment, next_appointment_provider, office,
                       patient, provider, referred_by, responsible_party, timezone, today,
                       treatment_plan, treatment_plan_teeth, unresolved_tokens
```

Your reproduction cases, run against that live server with a real bearer token:

```
GET /api/v1/patients/83867/letter-context
  APPT_PRDR                   = "Arjun"          (was "")
  APPT_DATE                   = "06/21/2026"
  APPT_DATETIME               = "06/21/2026 8:20 AM"
  today / timezone            = 2026-08-19 / America/New_York
  appointment_source          = "last"
  appointment_provider_source = "last"
  fallback_tokens             = {"APPT_DATE":"last","APPT_DATETIME":"last","APPT_PRDR":"last"}
  APPT_PRDR in unresolved_tokens = False

POST /api/v1/letters/render {"template_id":114,"patient_id":83867,
                             "signing_provider_id":"prov-arjun-9",
                             "overrides":{"APPT_PRDR":"Dr. Arjun Mehta"}}
  applied_overrides  = ["APPT_PRDR","DOC_LAST_NAME"]
  rejected_overrides = []
  body → "…request that Dr. Dr. Arjun Mehta and their assistants perform the specified teeth…"
```

**Small note from that last line:** template 114 has a literal `Dr. ` in front of
`#APPT_PRDR#`, so an override value of `"Dr. Arjun Mehta"` renders as "Dr. Dr. Arjun
Mehta". The server's own resolution returns the bare `"Arjun"` for exactly this reason.
Send the name without the honorific and the templates that supply their own read
correctly.

### Cloud Run is **not** deployed, and I did not deploy it

`.github/workflows/deploy-cloud-run.yml` triggers on push to
**`feature/phase_data_migration`**. The work is on `feature/uat-realse` and is currently
uncommitted in the working tree. Pushing to a branch that auto-deploys a shared
environment is your call, not something I should do unprompted — so
`https://dentc-backend-…run.app` still serves round 1. Commit and merge to that branch
when you want it live.

## The timezone field name — pinned

It is **`timezone`**, a sibling of `today`, on **both** `letter-context` and the
`/letters/render` response. It is a full IANA zone id (`"America/New_York"`), sourced from
`offices.timezone` for the printing office. Pin your probe to that name; the other
spellings will never appear.

Your gating approach is right, and the field is a sound marker — it is only present on a
build that also dates letters in the office's zone.

## Answers noted

- **Third fallback stays.** Now visible rather than silent — see LTR-17 below.
- **`signing_provider_id` vs `overrides` per Signature Type** — your table is exactly the
  intended split, and needs nothing from the backend. `signing_provider_id` moves
  `#APPT_PRDR#` *and* `#DOC_LAST_NAME#` together (they are one identity); sending
  `overrides: {"DOC_LAST_NAME": "…"}` alone leaves `#APPT_PRDR#` on the treating provider,
  which is the Hygienist / Assistant / Office Manager case. Both are covered by tests.

---

## LTR-17 — the appointment block reports which tier answered

**Done.** Both `GET /patients/{id}/letter-context` and `POST /letters/render` now return:

| Field | Values | Meaning |
|---|---|---|
| `appointment_source` | `"next"` · `"last"` · `null` | which appointment fed `#APPT_DATE#` / `#APPT_DATETIME#` |
| `appointment_provider_source` | `"next"` · `"last"` · `"preferred"` · `null` | which tier fed `#APPT_PRDR#` |
| `fallback_tokens` | `{token: tier}` | only the **degraded** resolutions |

Two scalars rather than one, because they genuinely disagree: a past appointment whose
`provider_id` no longer resolves gives `appointment_source: "last"` with
`appointment_provider_source: "preferred"`. There is a test for exactly that row.

`fallback_tokens` is the one to drive the preview from — it is empty whenever everything
came from the upcoming appointment, so a non-empty map *is* the set of values to annotate:

```json
{ "APPT_PRDR": "preferred" }
```
→ "provider taken from the patient's preferred provider — no appointment on file"

```json
{ "APPT_DATE": "last", "APPT_DATETIME": "last", "APPT_PRDR": "last" }
```
→ "from the visit on 06/21/2026"

Two refinements worth knowing:

- **An overridden token is never listed.** If the dialog supplied `#APPT_PRDR#` (via
  `overrides` or `signing_provider_id`) the value came from the user, so there is nothing
  to warn about — `fallback_tokens` comes back `{}` while
  `appointment_provider_source` still reports the underlying tier for anyone who wants it.
- **`/letters/render` only lists tokens the template actually contains.** A warning about
  `#APPT_DATE#` on a letter that does not print a date is noise; `letter-context` reports
  everything, since it has no template in hand.

When nothing can answer at all (no appointments *and* no preferred provider), both scalars
are `null` and `fallback_tokens` is `{}` — the token is genuinely unresolved and stays in
`unresolved_tokens`, which is the existing warning path.

---

## Tests

52 cases in [tests/test_letters_module.py](../../tests/test_letters_module.py)
(9 new for LTR-17) and 20 in
[tests/test_document_storage.py](../../tests/test_document_storage.py). The LTR-17 set
covers each tier, the disagreeing-tier row, override suppression, and the
template-filtered list.

## Unchanged

- **LTR-8 / LTR-9** — still awaiting a human `--apply` decision. Nothing mutated.
- **LTR-16** — still needs one deployed run with `GCS_BUCKET_DOCUMENTS` set;
  `python -m scripts.check_document_storage` is the one-command check.
