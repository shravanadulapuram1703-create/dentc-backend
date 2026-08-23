# Patient Notes — document upload / download: backend response

**Report answered:** [`patient_note_documents_backend_devreport.md`](patient_note_documents_backend_devreport.md)
**Module:** Patient → Notes → New Note → *Documents (Upload)* / *Document (Scan)*
**Date:** 2026-08-20
**Migration:** `a1b2c3d4e5f7` (`patient_notes.document_id`)
**Status:** all five gaps closed. NOTE-DOC-2 needs one env var set at deploy time;
everything else is live in code.

---

## Summary

| ID | Gap | Status | What landed |
|----|-----|--------|-------------|
| **NOTE-DOC-1** | Notes cannot reference a document | **Done** | Option **(a)** — `document_id` on `PatientNote*`, plus an embedded `document` block on the read so you don't need a second call |
| **NOTE-DOC-3** | `/uploads/**` served PHI unauthenticated | **Done** | Public static mount removed; every document/attachment now reads through an authenticated `/content` route |
| **NOTE-DOC-2** | Documents on ephemeral local disk | **Done in code, needs config** | Already routed to GCS — set `GCS_BUCKET_DOCUMENTS` on the deploy |
| **NOTE-DOC-5** | No server-side validation | **Done** | 10 MB cap + content-type allow-list enforced, published at `GET /patient-documents/limits` |
| **NOTE-DOC-4** | No `document_type` vocabulary | **Done** | `definitions` group `document_type` seeded (14 codes, `CF` = Consent Form) |

Nothing in the report's "confirmed working" list changed shape except `file_url`
— see NOTE-DOC-3, which is a deliberate breaking change to a value that was
leaking PHI.

---

## NOTE-DOC-1 — the note ↔ document link

We took **option (a)**, as you preferred. `patient_notes` gains a nullable
`document_id` FK to `patient_documents.id`.

`PatientNoteCreate` / `PatientNoteUpdate` / `PatientNoteRead` now carry
`document_id: int | null`. The flow is exactly what you described:

```
POST /api/v1/patient-documents   (multipart: file, patient_id, document_type)  -> 201 {id}
POST /api/v1/patient-notes       {..., "document_id": <that id>}               -> 201
```

**One addition beyond the ask.** `PatientNoteRead` also returns an embedded
`document` object, populated server-side in a single batched query:

```jsonc
{
  "id": 501,
  "patient_id": 83862,
  "note_type": "DOC",
  "notes": "Signed consent",
  "document_id": 31,
  "document": {
    "id": 31,
    "file_name": "consent.pdf",
    "content_type": "application/pdf",
    "file_size": 84213,
    "document_type": "CF",
    "description": null,
    "file_url": "https://storage.googleapis.com/...?X-Goog-Signature=...",
    "storage_backend": "gcs",
    "created_at": "2026-08-20T14:02:11Z"
  },
  "created_by_name": "Dana Ruiz",
  "updated_by_name": null
}
```

Without it, a Notes list of 40 rows would fire 40 `GET /patient-documents/{id}`
calls just to learn each file's name and URL. `document` is `null` for the note
types that carry no file. `created_by_name`/`updated_by_name` come along in the
same pass since we were already resolving actors.

### Integrity rule

A note may only reference a document **in the same tenant and on the same
patient**. A note renders inside one patient's chart, so a mis-pointed id would
put another patient's file there — that is a PHI disclosure, not a cosmetic bug.
Enforced on create *and* on PATCH:

| Case | Response |
|------|----------|
| `document_id` belongs to another patient | `422` `document_patient_mismatch` |
| `document_id` unknown, deleted, or another tenant's | `404` |
| `document_id: null` | accepted — clears the link |

A `PATCH` carrying only `document_id` is checked against the note's **stored**
`patient_id`, so you never have to resend `patient_id` to make the check work.

### Cascade vs orphan — your open question

**Deleting a note does not delete the document.** `DELETE /patient-notes/{id}` is
a soft delete; the document is a patient-level record that also appears in
`GET /patient-documents?patient_id=`, and may be referenced by a consent
(`patient_consents.document_id`). Destroying the file when a note is soft-deleted
would mean an undeleted note points at nothing. Removing a file is an explicit
`DELETE /patient-documents/{id}`.

If you want a "remove note and its file" affordance in the UI, issue the two
calls — document first, then the note.

---

## NOTE-DOC-3 — `/uploads/**` no longer exists (breaking, security)

You were right, and it was worse than the report says: the blanket static mount
covered **everything** under the upload directory — patient documents, insurance
**claim attachments**, and **progress-note attachments** — all readable with no
token and no tenant check.

Three changes:

1. **The blanket mount is gone.** Only branding subdirectories are served
   publicly now (`logos`, `office_logos`, `provider_watermarks`), listed in
   `UPLOAD_PUBLIC_SUBDIRS`. Account and office logos keep working unchanged. The
   path from your report (`GET /uploads/patient_documents/83862/…`) now returns
   **404** with no credentials — and with them.

2. **`file_url` is never a `/uploads` path again.** For patient documents it is
   now either a short-lived signed GCS URL or
   `/api/v1/patient-documents/{id}/content`, resolved per read (a signed URL
   expires, so it is minted on read, never persisted). This is the behaviour that
   was already true for GCS-backed rows; local rows used to fall back to the
   public path and no longer do.

3. **Attachments got the read path they never had.** Two new endpoints, same
   shape as the document proxy:

   ```
   GET /api/v1/progress-notes/{note_id}/attachments/{attachment_id}/content
   GET /api/v1/insurance-claims/{claim_id}/attachments/{attachment_id}/content
   ```

   `ProgressNoteAttachmentRead.file_url` and `ClaimAttachmentRead.file_url` now
   point at these instead of `/uploads/...`.

**What this means for the frontend:** keep using `file_url` — it is still a URL
you can put in `<img src>` / `<a href>` / `window.open`. When it resolves to a
`/content` endpoint it needs the `Authorization` header, so render it through
your authenticated fetch (blob URL) rather than a bare `<img src>`; when
`GCS_BUCKET_DOCUMENTS` is set and signing works, it is a plain signed HTTPS URL
that renders inline with no header at all. That is the mode we want in
production, and it is what you asked for.

> Nothing was migrated or re-keyed — files already on disk keep their
> `storage_path`; only the way they are *served* changed.

---

## NOTE-DOC-2 — GCS

Every patient file lives under one `documents/` root, with a folder per class:

```
gs://reco-documents/
└── documents/
    ├── notes/{tenant_id}/{patient_id}/{uuid}{ext}           # context=note
    ├── consent-forms/{tenant_id}/{patient_id}/{uuid}.pdf    # consent document types
    └── general/{tenant_id}/{patient_id}/{uuid}{ext}         # everything else
```

Note the layout is `{tenant}/{patient}/…`, one level deeper than the local path
you observed — a bucket is shared across tenants, so tenant has to be in the key.

### `context` — one new field on the upload (FE change required)

`POST /patient-documents` accepts a `context` form field. **Send `context=note`
for every upload from the Notes screen** — that is what puts the file in
`documents/notes/`. Without it the upload still succeeds, it just lands in
`documents/general/` (or `documents/consent-forms/` for a consent sub-type).

We cannot infer it: the file is uploaded *before* the note row exists, so there
is nothing on the server that knows the upload came from Notes.

```
POST /api/v1/patient-documents
  file=@consent.pdf
  patient_id=83862
  document_type=CF
  context=note            <-- new
```

**`context` beats `document_type`.** A consent form uploaded from Notes goes to
`documents/notes/`, not `documents/consent-forms/` — the note is the record it
belongs to. (Uploading a consent from anywhere *else* still files it with the
practice's consent library.)

An unrecognised `context` is a **422 `invalid_document_context`** rather than a
silent fall-through to the default — a typo would otherwise bury a note's file in
the wrong folder with nothing to indicate it. The accepted values are published
alongside the size/type limits:

```
GET /api/v1/patient-documents/limits
-> {"max_bytes": ..., "allowed_contexts": ["note"], ...}
```

**To turn it on, set on the deploy:**

| Var | Value |
|-----|-------|
| `GCS_BUCKET_DOCUMENTS` | `reco-documents` |
| `PUBLIC_API_BASE_URL` | the API's browser-reachable origin (so proxy URLs are absolute) |
| `DOCUMENT_URL_MODE` | `auto` (default) — signed URL when signing works, else proxy |
| `DOCUMENT_SIGNED_URL_TTL_SECONDS` | `900` (default) |
| `GCS_NOTES_PREFIX` | `documents/notes` (default) |
| `GCS_CONSENT_FORMS_PREFIX` | `documents/consent-forms` (default) |
| `GCS_DOCUMENTS_PREFIX` | `documents/general` (default) |

The three prefixes are defaults — you only set them to override the layout.

**The service account needs access to the bucket — this is currently the only
thing blocking it.** `GCS_CREDENTIALS_PATH` points at
`dicom_migration/sa-dicom-ingest.json`, i.e.
`sa-dicom-ingest@reckon-dental.iam.gserviceaccount.com`, which has rights on the
DICOM buckets but **none on `reco-documents`**. Probed against the live bucket:
routing is correct, upload returns
`403 … does not have storage.objects.create access`.

```bash
gcloud storage buckets add-iam-policy-binding gs://reco-documents --member=serviceAccount:sa-dicom-ingest@reckon-dental.iam.gserviceaccount.com --role=roles/storage.objectAdmin
```

`objectAdmin` covers create / read / list / delete. For V4 signed URLs the
account also needs `roles/iam.serviceAccountTokenCreator` **on itself**; without
it everything still works — `file_url` falls back to the `/content` proxy.

Verify against the real bucket in one command:

```bash
python -m scripts.check_document_storage
```

If GCS is configured but an upload fails, we log the error and write the file
locally rather than losing it. That row reports `storage_backend: "local"` — it
is the signal that the bucket is unreachable. The local path mirrors the object
key it would have had, so a later sweep can lift it into the bucket unchanged.

> **One thing to know before the bucket goes live.** The prefixes changed in this
> pass — they used to be `consent-forms/` and `patient-documents/` at the bucket
> root. Nothing needs migrating because the bucket has never been switched on
> (`storage_backend` is `local` on every row today, and reads use each row's
> stored `storage_path` regardless). If blank consent masters have already been
> uploaded to `consent-forms/`, either move them under `documents/consent-forms/`
> or call `GET /consent-forms?prefix=consent-forms` to keep listing them where
> they are.

---

## NOTE-DOC-5 — server-side validation

Enforced on **every** binary upload route (patient documents, progress-note
attachments, claim attachments), from one shared rule set:

| Rule | Value |
|------|-------|
| Max size | **10 MB** (`DOCUMENT_MAX_BYTES`) |
| Content types | `application/pdf`, `image/jpeg`, `image/png`, `image/gif`, `image/tiff`, `image/bmp`, `image/webp` |
| Extensions | `.pdf .jpg .jpeg .png .gif .tif .tiff .bmp .webp` |

Both the extension **and** the declared content type must be acceptable, with one
deliberate exception: a declared type of `application/octet-stream` (or an empty
one) defers to the extension. Browsers and TWAIN scanners routinely send
octet-stream for a perfectly good PDF, and rejecting those would break *Document
(Scan)* for no security gain.

Failures are `422` with a readable message you can show verbatim:

```json
{"error": {"code": "file_too_large",
           "message": "File exceeds the 10.0 MB limit (14.2 MB uploaded)",
           "details": {"max_bytes": 10485760, "size": 14889574}}}
```

Codes: `file_too_large`, `file_empty`, `unsupported_file_type` (extension),
`unsupported_content_type` (declared type).

**Don't hardcode the numbers.** They are published:

```
GET /api/v1/patient-documents/limits
-> {"max_bytes": 10485760, "max_megabytes": 10.0,
    "allowed_content_types": [...], "allowed_extensions": [...]}
```

We widened your list slightly (tiff/bmp/webp) because scanned legacy records
arrive as TIFF. Narrow the picker to `.gif/.jpg/.jpeg/.png/.pdf` if you prefer —
the server will accept the superset either way.

---

## NOTE-DOC-4 — `document_type` vocabulary

Seeded as the `document_type` `definitions` group, so the dropdown comes from the
same endpoint every other dropdown uses:

```
GET /api/v1/definitions?group_code=document_type
```

`key1` is the stored value, `description` the label:

| key1 | Label | | key1 | Label |
|------|-------|-|------|-------|
| `CF` | Consent Form | | `MH` | Medical History |
| `IC` | Insurance Card | | `TP` | Treatment Plan |
| `ID` | Photo ID | | `FA` | Financial Agreement |
| `XR` | X-Ray / Image | | `EOB` | Explanation of Benefits |
| `RX` | Prescription | | `CR` | Correspondence |
| `RF` | Referral Letter | | `PH` | Patient Photo |
| `LB` | Lab Report | | `OT` | Other |

Run `python -m scripts.seed_account_definitions` (idempotent) to seed. Practices
extend the list through the ordinary `/definitions` CRUD — no release needed.

`document_type` stays a free-text column on the row (migrated data holds values
that predate this list), so nothing is rejected; the group is the *pick list*.

**One thing to change on your side:** `CF` is now also recognised as a consent
type, so a consent uploaded from Notes lands under the `consent-forms/` bucket
prefix with the rest of the practice's consents rather than in the generic
document prefix. Keep sending `CF` — that is what makes it work.

---

## Endpoint delta

| Method | Path | Note |
|--------|------|------|
| `POST` | `/api/v1/patient-documents` | **new `context` form field** — send `context=note` from Notes |
| `GET` | `/api/v1/patient-documents/limits` | **new** — NOTE-DOC-5, also publishes `allowed_contexts` |
| `GET` | `/api/v1/progress-notes/{id}/attachments/{aid}/content` | **new** — NOTE-DOC-3 |
| `GET` | `/api/v1/insurance-claims/{id}/attachments/{aid}/content` | **new** — NOTE-DOC-3 |
| `*` | `/api/v1/patient-notes*` | `document_id` in/out; `document` block on read |
| `GET` | `/api/v1/patient-notes?document_id=` | **new filter** |
| — | `/uploads/**` (except branding subdirs) | **removed** — NOTE-DOC-3 |

`openapi.json` is regenerated; re-run Orval.

---

## Not addressed (out of scope, by design)

* **Multiple files per note.** We shipped option (a), which is one document per
  note. If a note genuinely needs several files, tell us and we will add
  `/patient-notes/{id}/attachments` mirroring progress-notes — the storage layer
  already supports it, it is a table and four routes.
* **Virus scanning.** Uploads are validated for size and type, not scanned. Worth
  a separate conversation before this carries patient-submitted files.
* **The collapsed *Show File Details* toggle** is yours, as your report notes.
