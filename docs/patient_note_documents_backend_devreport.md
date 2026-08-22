# Patient Notes — document upload / download: backend gap report

**Module:** Patient → Notes → New Note → *Documents (Upload)* / *Document (Scan)*
**Screen:** `src/components/patient/AddEditPatientNote.tsx`
**Raised:** 2026-08-20
**Status:** blocked on the backend for the note↔document link; storage backend
change also required before this can ship to production.

---

## 1. What we need

A user writing a patient note of type **Documents (Upload)** must be able to:

1. attach a file (image / PDF) from their machine,
2. save it with the note,
3. re-open the note later and **view / download** that file,

with the file itself living in **Google Cloud Storage, keyed by patient id** —
the same way patient images are stored and served today.

---

## 2. What already exists and works (verified live)

Good news: the binary store is already built and behaves correctly. Verified
against `127.0.0.1:8000` on 2026-08-20 with patient **83862**.

| Endpoint | Verified result |
|----------|-----------------|
| `POST /api/v1/patient-documents` (multipart: `file`, `patient_id`*, `office_id`, `document_type`, `description`) | **201**. Returned `id: 31`, `file_name: "consent-test.txt"`, `content_type: "text/plain"`, `file_size: 47`, `document_type: "CF"`, `storage_path: "patient_documents/83862/979464be….txt"` — already namespaced **per patient id**. |
| `GET /api/v1/patient-documents?patient_id=83862` | **200**, returns the document. |
| `GET /api/v1/patient-documents/{id}/content` | **200**, `text/plain`, 47 bytes — authenticated streaming download with tenant checks. |
| `DELETE /api/v1/patient-documents/{id}` | **204**, and it is a **hard** delete — the row leaves the list, `/content` 404s, and the file is removed from disk. (Noting explicitly because several other resources here soft-delete and keep returning the row.) |

`PatientDocumentRead` also already carries `storage_backend`, `storage_bucket`
and `storage_path`, i.e. the model is **already shaped for cloud storage**.

**So this report is not asking for a new upload service.** It asks for two
things: a way to attach an existing document to a note, and a flip of the
storage backend to GCS.

---

## 3. Gaps

### NOTE-DOC-1 — a patient note cannot reference a document (BLOCKER)

`PatientNoteCreate` / `PatientNoteUpdate` / `PatientNoteRead` expose only:

```
patient_id, office_id, note_date, note_type, notes, notes_html,
is_archived, is_deleted, legacy_id, created_by, updated_by, id, created_at, updated_at
```

There is **no `document_id`**, no `attachments` array, and no
`/api/v1/patient-notes/{note_id}/attachments` sub-resource. So a file can be
uploaded, but nothing records that it belongs to a given note — re-opening the
note cannot find it.

This is inconsistent with the rest of the API, which already solves exactly this
problem twice:

* `GET|POST /api/v1/progress-notes/{note_id}/attachments`
  `DELETE /api/v1/progress-notes/{note_id}/attachments/{attachment_id}`
  (`ProgressNoteAttachmentRead`: `progress_note_id`, `attachment_type`,
  `file_name`, `content_type`, `file_size`, `file_url`, `description`, …)
* `GET|POST /api/v1/insurance-claims/{claim_id}/attachments`

**Ask — either option works for us, (a) is less work:**

* **(a)** add a nullable `document_id: int | null` to `PatientNoteCreate` /
  `PatientNoteUpdate` / `PatientNoteRead`, FK to `patient_documents.id`. The
  client uploads first, then saves the note with the returned id.
* **(b)** add `/api/v1/patient-notes/{note_id}/attachments` mirroring the
  progress-notes routes exactly, so one patient note can carry several files.

Please also confirm what should happen to the document when a note is deleted
(cascade vs orphan).

### NOTE-DOC-2 — documents are stored on local disk, not GCS

Live response from the upload above:

```json
"storage_backend": "local",
"storage_bucket": null,
"storage_path": "patient_documents/83862/979464bea95e4cf09f43afb14c5f0f08.txt",
"file_url": "/uploads/patient_documents/83862/979464bea95e4cf09f43afb14c5f0f08.txt"
```

Files are written to the application server's filesystem. On Cloud Run (or any
scaled/redeployed container) that storage is ephemeral and per-instance:
uploads are lost on redeploy, and an instance cannot read another instance's
files. It is also outside whatever backup/retention policy covers the database.

**Ask:** switch the storage backend to **GCS** — `storage_backend: "gcs"`,
`storage_bucket` populated, keeping the existing
`patient_documents/{patient_id}/{uuid}.{ext}` object prefix (that layout is
already right). No client change is needed for this if `/content` keeps
streaming the bytes.

### NOTE-DOC-3 — `file_url` serves PHI with no authentication (SECURITY)

Verified with **no `Authorization` header at all**:

```
GET http://127.0.0.1:8000/uploads/patient_documents/83862/979464be….txt
→ 200 OK, text/plain, full file contents
```

Anyone who obtains or guesses that path reads a patient document — no login, no
tenant check. `/patient-documents/{id}/content` does apply tenant checks; the
raw `/uploads/**` path bypasses them entirely.

**Ask:** stop serving `/uploads/**` as a public static route. Either

* drop `file_url` from the response and have clients use `/content`, or
* return a **short-lived signed GCS URL** in `file_url` (this is the natural fit
  once NOTE-DOC-2 lands, and is what we would prefer for rendering images and
  PDFs inline without proxying bytes through the API).

Please treat this as security-priority regardless of the rest of this report —
it applies to every document already uploaded, not just notes.

### NOTE-DOC-4 — no vocabulary for `document_type`

`document_type` is free-text. The Notes screen offers a fixed list
(Consent Form (CF), etc.) that is **hardcoded in the frontend** and therefore
cannot be maintained by the practice or kept in step with any other module.

**Ask:** seed a `definitions` group (e.g. `group_code = "DOCTYPE"`) with the
legacy document sub-types, or confirm free-text is intended and we will keep the
list client-side.

### NOTE-DOC-5 — no server-side file validation

The screen enforces **max 10 MB** and **.gif/.jpg/.jpeg/.png/.pdf**, but that is
client-side only; `POST /patient-documents` accepted a `text/plain` upload
without complaint.

**Ask:** enforce a content-type allow-list and a size cap server-side, returning
a 4xx with a readable `detail`. Please confirm the limits so the UI can state
the same numbers.

---

## 4. Summary for the backend team

| ID | Gap | Priority | Ask |
|----|-----|----------|-----|
| **NOTE-DOC-1** | Patient notes cannot reference an uploaded document | **Blocker** | Add `document_id` to `PatientNote*`, **or** add `/patient-notes/{id}/attachments` like progress-notes already has |
| **NOTE-DOC-3** | `/uploads/**` serves patient documents unauthenticated | **Security** | Remove the public route; use `/content` or signed GCS URLs |
| **NOTE-DOC-2** | Documents stored on ephemeral local disk | **High** | Move to GCS, keep the `{patient_id}/{uuid}` prefix |
| **NOTE-DOC-5** | No server-side size / content-type validation | Medium | Enforce and document the limits |
| **NOTE-DOC-4** | `document_type` has no definitions vocabulary | Low | Seed a `DOCTYPE` definitions group, or confirm free text |

**Not gaps — confirmed working, no action needed:** upload, per-patient listing,
authenticated streaming download, hard delete, and the per-patient object
prefix.

---

## 5. Current frontend state

Until NOTE-DOC-1 lands, the Notes screen:

* shows the file picker behind a **Show File Details** toggle (it is collapsed
  by default, which is why the upload control "does not appear" — this is a UI
  defect we are fixing separately),
* validates size/extension client-side,
* saves only `note_type` and `notes`; the chosen file and document sub-type are
  **discarded**, which the amber banner on the screen states plainly.

Once `document_id` (or the attachments sub-resource) exists we will: upload via
`POST /patient-documents` with `patient_id` + `document_type`, save the note with
the returned id, and render a view/download link from
`GET /patient-documents/{id}/content` — no further backend work expected.
