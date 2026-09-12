# Progress Notes — Backend Development Report

**Audience:** Backend team
**Module:** Patient → Progress Notes (legacy Denticon "M09 Progress Notes" parity)
**Frontend:** `src/features/progress-notes/` (route `/patient/:patientId/progress-notes`)
**Spec audited:** live `GET /api/v1/openapi.json` (FastAPI `v1.0.0`, 267 paths) —
verified **identical** to the committed `openapi.json`. Audit date: 2026-06-23.

This report lists (1) what the backend **already** supports (so it is not rebuilt)
and (2) the **gaps** that block full end-to-end Progress Notes, each with the
current spec evidence, impact, a concrete proposed change (endpoints/fields with
example payloads), and acceptance criteria.

---

## 1. Already implemented — no work needed

The core resource is in place and the frontend is fully wired to it (snake_case,
direct binding, no mapping layer).

**`/api/v1/progress-notes`** (tag *clinical*):

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/progress-notes?patient_id=` | list (paginated, `size`≤200) |
| POST | `/api/v1/progress-notes` | create |
| GET | `/api/v1/progress-notes/{item_id}` | read |
| PATCH | `/api/v1/progress-notes/{item_id}` | update (also used for strike-off/restore) |
| DELETE | `/api/v1/progress-notes/{item_id}` | (unused — notes are struck off, not deleted) |
| POST | `/api/v1/progress-notes/{note_id}/sign` | sign |

**`ProgressNoteRead`** (current): `patient_id*`, `office_id`, `legacy_id`,
`note_date (date)`, `notes`, `notes_html`, `tooth`, `surface`, `region`,
`signed_by (int)`, `signed_at (datetime)`, `is_struck_off* (bool)`,
`is_deleted* (bool)`, `created_by (int)`, `id*`, `created_at* (datetime)`.
Create/Update mirror these (all nullable except `patient_id` on create).

Supporting resources used and working:
- **`/api/v1/note-macros`** — macro library (Category/Macro panel + Preview).
- **`/api/v1/questionnaire-headers`** + **`/api/v1/questionnaire-options`** —
  resolve `{{pick-list name}}` macro tokens into option lists.
- **`/api/v1/patient-documents`** — file upload (attachments), 10 MB,
  gif/jpg/jpeg/png/pdf.
- **`/api/v1/patient-signatures`** — signature storage.
- **`/api/v1/users`** — exists with `username`/`first_name`/`last_name` (see PN-5).

Mapping of these fields to the legacy UI: `notes_html` = colour-coded rich text;
`tooth` = comma-joined Universal numbers/letters from the V-grid picker;
strike-off = `PATCH {is_struck_off:true}`; restore = `PATCH {is_struck_off:false}`.

---

## 2. Gaps (backend work requested)

Priority: **P1** blocks a legacy feature with no usable workaround; **P2** has a
client-side workaround but should be fixed for correctness/consistency.

### PN-1 — No per-user (provider) signature store ("Load My Signature") — **P1**

**Legacy behaviour:** "Load My Signature" loads the *logged-in provider's*
signature image on file and applies it to the note; over-the-shoulder, a provider
enters their credentials, then Load My Signature.

**Current spec:** the only signature store is **`/api/v1/patient-signatures`**,
keyed by `patient_id`:
```
PatientSignatureCreate: patient_id*, signature_data, signature_len, device_source, is_user_sig
PatientSignatureRead:   + id, created_at, created_by, legacy_id
```
`is_user_sig` flags "provider vs patient" but the row is still **per patient**.
There is no `/users/{id}/signature`, no `user-signatures` resource, and no way to
fetch "my" signature independent of a patient. Today the frontend can only
re-load a signature previously saved *for that same patient*.

**Impact:** "Load My Signature" cannot work as designed (a provider's stored
signature is unavailable on a patient where they have never signed before).

**Requested change** — a per-user signature resource, e.g.:
```
GET  /api/v1/users/{user_id}/signature        -> UserSignatureRead | 404
PUT  /api/v1/users/{user_id}/signature        body: { signature_data, signature_len?, device_source? }
GET  /api/v1/users/me/signature               -> convenience for the logged-in user
UserSignatureRead: { user_id, signature_data (base64/data-url or file_url), signature_len, updated_at }
```
**Acceptance:** a logged-in user can save one signature once and `GET …/me/signature`
returns it on any patient; storing/reading does not require a `patient_id`.

---

### PN-2 — `/sign` ignores "Change User" (over-the-shoulder) credentials — **P1**

**Legacy behaviour:** a Provider signs over a logged-in user's shoulder by typing
their **User Name + Password**, then Load My Signature → Save. The note is signed
as the *Provider*, not the logged-in user.

**Current spec:** `POST /api/v1/progress-notes/{note_id}/sign` takes **no request
body** and (per implementation) stamps the **authenticated** user into
`signed_by`/`signed_at`. There is no way to sign as a different user.

```
POST /api/v1/progress-notes/{note_id}/sign   requestBody: (none)
```

**Impact:** over-the-shoulder signing is impossible; the note is always attributed
to whoever is logged in. (The "Change User" username/password fields are rendered
for parity but cannot be honoured.)

**Requested change** — accept an optional credential/identity on sign and verify
server-side:
```
POST /api/v1/progress-notes/{note_id}/sign
body (optional): { username: string, password: string }   // verify → sign as that user
   - empty body  → sign as the authenticated user (current behaviour, keep)
   - bad creds   → 401
   - success     → set signed_by = verified user id, signed_at = now
```
**Note / partial workaround:** `ProgressNoteUpdate` already accepts `signed_by` and
`signed_at`, so the FE *could* stamp a provider if it knew their `user_id`. It does
not, because there is **no credential-verification endpoint** that returns a user
id. If a dedicated sign body is not feasible, an alternative is:
`POST /api/v1/auth/verify {username,password} -> { user_id }` (then FE PATCHes
`signed_by`). Either approach is acceptable; the sign-body approach is preferred
(atomic + audited).
**Acceptance:** posting valid provider creds to `/sign` sets `signed_by` to that
provider; invalid creds return 401; no body still signs as the caller.

---

### PN-3 — Attachments cannot be linked to a progress note — **P1**

**Legacy behaviour:** files are attached **to a specific note**; the list shows a
📎 indicator per note that has attachments.

**Current spec:** `/api/v1/patient-documents` links a file to a **patient only** —
there is no progress-note reference on upload, read, or list filter:
```
Body_upload_patient_document: file*, patient_id*, office_id, document_type, description
PatientDocumentRead:          tenant_id, patient_id, office_id, document_type, file_name,
                              content_type, file_size, file_url, description, is_deleted, created_by, id, created_at
GET /api/v1/patient-documents?patient_id=   // no note filter
```
Today the FE uploads with `document_type='progress_note'` as a tag, but the file
**cannot be associated back to the note that created it**, so the list's 📎 column
is non-functional and an edited note cannot show/remove its own attachments.

**Impact:** attachments are effectively orphaned at the patient level; no per-note
display, no per-note delete.

**Requested change** — either (a) add an optional FK + filter to patient-documents:
```
Body_upload_patient_document: + progress_note_id?: int
PatientDocumentRead:          + progress_note_id?: int
GET /api/v1/patient-documents?progress_note_id=    // filter
```
or (b) a note sub-resource mirroring the **existing** insurance-claim pattern
(`/insurance-claims/{claim_id}/attachments`), which is the cleaner precedent:
```
GET    /api/v1/progress-notes/{note_id}/attachments
POST   /api/v1/progress-notes/{note_id}/attachments        (multipart: file)
DELETE /api/v1/progress-notes/{note_id}/attachments/{attachment_id}
```
**Acceptance:** a file uploaded against a note is returned when listing that note's
attachments and not others; deleting it affects only that note.

---

### PN-4 — No strike-off timestamp (same-day restore rule unenforceable) — **P2**

**Legacy behaviour:** a struck-off note can be **Restored only on the same day it
was struck off**.

**Current spec:** `is_struck_off` is a bare boolean — there is no `struck_off_at`
(or `struck_off_by`). The FE therefore allows Restore unconditionally.

**Requested change:**
```
ProgressNoteRead: + struck_off_at?: datetime, + struck_off_by?: int
```
Set `struck_off_at = now` whenever `is_struck_off` transitions false→true (and
ideally clear it on restore). **Acceptance:** `struck_off_at` is populated on
strike-off so the client can gate Restore to the same calendar day.

---

### PN-5 — `created_by` / `signed_by` are numeric ids with no name — **P2**

**Legacy behaviour:** the list shows *who* created/modified/signed each note by
name; the editor footer shows created/modified by whom.

**Current spec:** `created_by`/`signed_by` are integers only; the FE renders
"User #N". Note that **`UserRead` already exposes `created_by_name` /
`updated_by_name`** — the backend already has this name-expansion pattern; the
progress note simply does not apply it.

**Workaround in place:** the FE can resolve ids → names via `GET /api/v1/users`
(has `username`/`first_name`/`last_name`), at the cost of an extra fetch and no
batch-by-id filter.

**Requested change (preferred):** add expanded names to `ProgressNoteRead`,
consistent with `UserRead`:
```
ProgressNoteRead: + created_by_name?: string, + signed_by_name?: string
```
**Acceptance:** list/read return display names without a separate users fetch.

---

### PN-6 — Macro `category` is unconstrained free text / numeric codes — **P2**

**Current spec:** `NoteMacroRead.category` is `string | null`, unvalidated. Seeds
often store **numeric codes** rather than labels, so the editor's Category dropdown
(derived from distinct macro categories) shows codes, not human labels. (Same root
issue as **NM-2** in the Notes-Macros setup report.)

**Requested change:** seed/normalise macro categories to human-readable labels (or
expose a category lookup). **Acceptance:** distinct macro categories render as
labels in the Category dropdown.

---

### PN-7 — Locking is client-derived only (no server enforcement) — **P2**

**Legacy behaviour:** a note locks (no further text changes) when **signed** or
**after midnight** of its creation day; locked notes can still be signed.

**Current spec:** there is no `is_locked` flag and the server does **not** reject a
`PATCH` to a signed or day-old note. The FE computes lock state from
`signed_at`/`created_at` and disables editing, but this is advisory — a direct API
call can still mutate a "locked" note.

**Requested change:** enforce server-side — reject text changes (`notes`,
`notes_html`, `tooth`, …) on a note that is signed or whose `created_at` is before
the current day, returning `409`/`422`; continue to allow `/sign` and
`is_struck_off` transitions. Optionally surface a computed `is_locked: bool` on
`ProgressNoteRead`. **Acceptance:** editing a signed or prior-day note via the API
is rejected; signing and strike-off still succeed.

---

## 3. Summary table

| ID | Gap | Priority | Workaround today |
|----|-----|----------|------------------|
| PN-1 | Per-user signature store ("Load My Signature") | P1 | none (per-patient only) |
| PN-2 | `/sign` over-the-shoulder credentials | P1 | none (signs as caller) |
| PN-3 | Attachment ↔ note link | P1 | none (orphaned at patient) |
| PN-4 | `struck_off_at` for same-day restore | P2 | restore always allowed |
| PN-5 | `created_by_name`/`signed_by_name` | P2 | resolve via `/users` list |
| PN-6 | Macro category labels | P2 | show raw code |
| PN-7 | Server-side lock enforcement | P2 | client-side disable only |

Once PN-1/PN-2/PN-3 land, Progress Notes is fully end-to-end; PN-4..7 are
correctness/quality follow-ups.

---

## 4. Backend response — IMPLEMENTED (2026-06-23)

All gaps are addressed. Migration: `alembic/versions/a3b4c5d6e7f8_add_progress_notes_gaps.py`
(down_revision `f2c3d4e5a6b7`). Models in `app/db/models/clinical.py`,
`patient_extra.py`, `identity.py`; schemas in `app/schemas/progress_notes.py` (+
`user_admin.py`); logic in `app/services/progress_notes_service.py`; routes in
`app/api/v1/progress_notes.py` (+ user-signature routes in `users_extended.py`);
CRUD wiring in `app/api/v1/registry.py`.

| ID | Resolution |
|---|---|
| **PN-1** | Per-user signature store on the existing `users.signature_data` (+ new `signature_len`/`signature_device_source`/`signature_updated_at`). `GET\|PUT /users/me/signature` (self) and `GET\|PUT /users/{user_id}/signature` (admin). `GET` returns **404** when nothing is on file. |
| **PN-2** | `POST /progress-notes/{note_id}/sign` now accepts an optional `{username, password}`. No body → sign as caller (unchanged). Valid provider creds (same tenant) → `signed_by` = that provider; bad creds → **401**; only one of username/password → **422**. Response includes `signed_by_name`. |
| **PN-3** | New `progress_note_attachments` table + sub-resource `GET\|POST /progress-notes/{note_id}/attachments` and `DELETE …/{attachment_id}` (10 MB cap, soft-delete; mirrors claim attachments). `ProgressNoteRead.attachment_count` powers the 📎 indicator without N calls. |
| **PN-4** | `progress_notes.struck_off_at`/`struck_off_by` set on the false→true strike-off transition and cleared on restore (server-managed; client values ignored). Exposed on the read model. |
| **PN-5** | `ProgressNoteRead` now carries `created_by_name`/`signed_by_name`/`struck_off_by_name` (batch-resolved, no N+1). |
| **PN-6** | `GET /note-macros/categories` → distinct categories `{category, macro_count}` for the dropdown (one fetch). Note: legacy seeds store numeric codes; true label normalisation is a seed-data fix, tracked with NM-2. |
| **PN-7** | Server-side lock: `PATCH` to a **signed** or **prior-day** note that changes text (`notes`/`notes_html`/`tooth`/`surface`/`region`/`note_date`) returns **409**; `/sign` and `is_struck_off` transitions still succeed. Computed `is_locked` surfaced on the read model. |

Apply with `python -c "from alembic.config import main; main(['upgrade','head'])"`.
