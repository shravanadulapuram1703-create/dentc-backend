# Letters — Backend Response

**Module:** Letters (New) — print menu → Letters dialog → Report Viewer → "Save PDF file"
**Gap report answered:** [letters_backend_devreport.md](letters_backend_devreport.md) (LTR-1…12)
**Migration:** Alembic `e9f0a1b2c3d4` (`add_letters_module_gaps`)
**Tests:** [tests/test_letters_module.py](../../tests/test_letters_module.py) — 28 cases

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
