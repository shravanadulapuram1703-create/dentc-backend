# Imaging ↔ Documents separation — Backend Response

**Date:** 2026-11-16 · **Gap IDs:** IMG-DOC-1..6 · **Report:**
`dentc-frontend/docs/imaging/imaging_documents_separation_backend_devreport.md`
**Alembic:** `03bbb54c0b12` (parent `81e09d9576e9`). Verified against the UAT DB
(`Test_Dental_Group`) in a rolled-back transaction. **Not applied yet.** Run
`alembic upgrade head` when you deploy.

| Gap | Status |
|---|---|
| IMG-DOC-1 persist + return `context`, per-owner storage folder | **Done** |
| IMG-DOC-2 filter by owner (repeated / comma / exclude) | **Done** |
| IMG-DOC-3 backfill existing rows | **Done** (runs inside the migration) + dry-run script |
| IMG-DOC-4 validated `document_type` vocabulary | **Done, behind a cut-over switch** (off by default; see below) |
| IMG-DOC-5 `PATCH /patient-documents/{id}` to move Documents ↔ Imaging | **Done** |
| IMG-DOC-6 reject unknown list params | **Done** (422 on this endpoint, with a kill switch) |

## IMG-DOC-1 — `context` (owning module)

- New column `patient_documents.context`: `VARCHAR(30) NOT NULL DEFAULT 'documents'`,
  indexed on `(patient_id, context)`. It is returned on `PatientDocumentRead`.
- Allowed values (a closed set):
  `documents, imaging, note, patient_photo, letter, consent, progress_note, restorative, treatment_plan`.
  Any other value returns 422 `invalid_document_context`. The list is published on
  `GET /patient-documents/limits → allowed_contexts`.
- **If the upload omits `context`, the server infers it from `document_type`.** This keeps
  today's frontend filing correctly before it starts sending `context`:

  | `document_type` | inferred context |
  |---|---|
  | `PH` | `patient_photo` |
  | `patient-letter` | `letter` |
  | `consent-form`, `CF`, `consent` | `consent` |
  | `progress_note` | `progress_note` |
  | `restorative-drawing` | `restorative` |
  | `treatment-plan` | `treatment_plan` |
  | `X-Ray`, `Bitewing`, `Panoramic`, `Periapical`, `Intraoral Photo`, `Treatment Photo`, `Other Image` | `imaging` |
  | anything else (`Insurance Card`, `XR`, `X-Ray / Radiograph`, …) | `documents` |

  `XR` and `X-Ray / Radiograph` are deliberately **not** inferred as Imaging. Notes and the
  Documents tab send those values too. Staff move a misfiled radiograph with IMG-DOC-5.
- Each context gets its own storage prefix under `documents/`:
  `documents/general` (documents), `documents/imaging`, `documents/notes`,
  `documents/consent-forms`, `documents/patient-photos`, `documents/letters`,
  `documents/progress-notes`, `documents/restorative`, `documents/treatment-plans`.
  You can override the prefixes per environment with `GCS_CONTEXT_PREFIXES` (JSON).
  Existing objects stay where they are. Every row stores its own `storage_path`, so nothing
  breaks.

## IMG-DOC-2 — list filters

`GET /patient-documents` now supports:

- `context=imaging`. Repeat the param (`context=documents&context=note`) or pass a comma list
  (`context=documents,note`). Each value is validated, so a typo returns 422 instead of an
  unfiltered list.
- `exclude_context=imaging`. Same forms.
- `document_type` now takes a **comma list**, matches **case-insensitively**, and matches every
  known spelling of a code. For example, `IC` also finds rows stored as `Insurance Card`, and
  `XR` finds `X-Ray / Image` and `X-Ray / Radiograph`. It stays a single string param in
  OpenAPI, so your generated client signature does not change.

## IMG-DOC-3 — backfill

The migration stamps every existing row. It runs inside the migration on purpose: if
`?context=imaging` shipped while old radiographs still had no owner, they would vanish from
the gallery. The rules follow the report's order exactly (`document_vocabulary.backfill_case`):

1. `storage_path` under `documents/notes/` → `note`. Under `documents/consent-forms/` → `consent`
   (or `letter` for a letter type).
2. `image_details.tile_id = String(id)` → `imaging`.
3. `patients.photo_document_id` points at the row → `patient_photo`.
4. to 6. Same as the inference table above.

**Dry-run counts on UAT `Test_Dental_Group` (10 rows):**

| context | document_type | rows |
|---|---|---|
| consent | `consent-form` | 3 |
| documents | `Insurance Card` | 3 |
| note | `CF` | 4 |
| imaging | — | 0 |

No row falls through to `documents` that could be a radiograph. On any other environment,
get the same report with:

```bash
python -m scripts.backfill_document_context
```

That command prints the count per owner, any rows whose stored owner differs from the derived
one, and the `document_type` values that fell through to `documents`.

## IMG-DOC-4 — `document_type` vocabulary (cut-over switch)

- There are now two definitions groups. Both are seeded by `scripts/seed_account_definitions.py`,
  and the code falls back to the same built-in lists when a tenant has none:
  - `document_type` (Documents and Notes): `CF IC ID XR RX RF LB MH TP FA EOB CR PH OT`
  - `imaging_document_type` (new, Imaging): `XR BW PA PAN FMX CEPH CBCT IO TXP OI`
- `GET /patient-documents/limits` now also returns `document_types.{documents|note|imaging}.options[]`
  (`{code, label}`), `movable_contexts` and `document_type_enforced`. Read the pickers from here
  or from `/definitions?group_code=…`.
- Every read now carries `document_type_label`, so a code such as `IC` shows as
  "Insurance Card".
- **`DOCUMENT_TYPE_VOCABULARY_ENFORCED` is off by default.** While it is off, the value is
  stored as written. Folding `Bitewing` to `BW` today would hide every new upload from the
  current Imaging gallery, which still matches on the label. When you turn it on, the picker
  contexts (`documents`, `note`, `imaging`) fold a code, label or known alias to the code
  (`Identification` → `ID`, `bitewing` → `BW`). Any other value returns 422
  `invalid_document_type`, with `details.allowed[]`. System contexts (letter, consent,
  progress note, restorative, treatment plan, photo) keep their fixed type.
- The cut-over, done in one release:
  1. The frontend reads its pickers from `/limits` (or `/definitions`) and displays
     `document_type_label`.
  2. Preview the type migration: `python -m scripts.backfill_document_context --fold-types`
  3. Apply it: `python -m scripts.backfill_document_context --fold-types --apply`
  4. Set `DOCUMENT_TYPE_VOCABULARY_ENFORCED=true`.

## IMG-DOC-5 — `PATCH /patient-documents/{id}`

Request body: `{ context?, document_type?, description? }`. The schema is
`extra="forbid"`, so an unknown key returns 422.

- You can only move a document between **`documents` and `imaging`**. Any other owner returns
  422 `context_not_movable`. Notes, consents, progress notes and the chart photo are pointed at
  by another record, so moving their file would orphan that record.
- On a move, the file moves into the new context's folder (copy, then delete the source, for
  GCS; a rename for local storage). If the storage move fails, the row still changes owner and
  the response says `relocated: false`.
- The request stamps `updated_at`/`updated_by`. The before/after values, including the old and
  new `storage_path`, are written to `audit_logs`. A request that changes nothing writes nothing.

## IMG-DOC-6 — unknown query params

`GET /patient-documents` returns **422 `unknown_query_parameter`** for any param it doesn't
declare (`details.unknown`, `details.allowed`). The allowed set is read from the route itself,
so it always matches the OpenAPI spec. This applies to this endpoint only, not API-wide: older
clients send stray params to many generic lists. Kill switch:
`DOCUMENT_LIST_REJECT_UNKNOWN_PARAMS=false`.

## Frontend follow-up

- Regenerate the client (`npm run api:sync`). New: `context`/`exclude_context` list params,
  `context`/`document_type_label`/`relocated`/`updated_*` on the read, `update_patient_document`,
  and the vocabulary fields on `UploadLimits`.
- Imaging: list with `context: ['imaging']` and upload with `context: 'imaging'`. Then you can
  delete `isImagingDocument`.
- Documents tab: list with `context: ['documents']` and upload with `context: 'documents'`.
  Product still needs to decide whether note and letter attachments belong on that tab
  (`context: ['documents','note']`).
- Uploads that don't send `context` still work (it is inferred), so nothing breaks before the
  cut-over.
