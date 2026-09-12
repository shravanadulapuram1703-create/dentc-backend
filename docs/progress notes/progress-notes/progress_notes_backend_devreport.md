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

### Status update — 2026-09-07 (openapi resync)

The current `openapi.json` ships **PN-2** (`/sign` accepts `{username, password}`),
**PN-3** (`/progress-notes/{id}/attachments` + `attachment_count`), **PN-4**
(`struck_off_at`/`struck_off_by`), **PN-5** (`*_by_name`) and **PN-7**
(`is_locked` + server-side 409 on locked text edits). PN-1 and PN-6 are still open.
The frontend now trusts the server's `is_locked` flag instead of re-deriving it.
PN-8..PN-11 below were found while fixing the "cannot edit a saved note" report.

---

### PN-8 — Date of Service is frozen by the prior-day lock (cannot correct DOS) — **P1**

**Business need:** doctors usually write the note **days after** the visit and
often leave the DOS at "today". The corrected DOS must be settable **after** the
note has been saved — including after the note's text has locked at midnight.

**Current behaviour (before this change):** `ProgressNoteCRUD.update` listed
`note_date` in `_TEXT_FIELDS`, so once a note is `is_locked` (signed **or** created
on a prior day) a `PATCH {note_date}` fails with
`409 {"error":{"code":"conflict","message":"This note is locked (signed or from a prior day) and cannot be edited","details":{"locked_fields":["note_date"]}}}`.
A note written yesterday for last week's visit can therefore never get the right DOS.

**Change applied locally** (`app/services/progress_notes_service.py`, needs a
backend restart + deploy): `note_date` removed from the lock's text-field list; a
separate check rejects a DOS change only when the note is **signed**
(`"This note is signed; its Date of Service can no longer be changed"`).
Struck-off notes keep the DOS editable server-side (the FE disables it until
restored). **Acceptance:** `PATCH /progress-notes/{id} {"note_date": "…"}` → 200
on an unsigned prior-day note; still 409 on a signed note; text fields still 409
on any locked note.

**Open question for backend:** should a DOS correction be audited
(`note_date_changed_by/at`, or an event row)? Legacy Denticon shows the change in
the note's audit trail.

---

### PN-9 — Lock day boundary is UTC, not the office's local day — **P2**

`_note_is_locked` compares `created_at.date()` with
`datetime.now(timezone.utc).date()`. `created_at` is stored as a naive UTC
timestamp, so for a US-Eastern office a note written at 3 PM locks at **8 PM
local** (00:00 UTC), and a note written after 8 PM is reported as created
"tomorrow". The FE used to compute the lock in local time and disagreed with the
server inside that window: the editor opened as editable, and Save failed with
the 409 above (surfacing as "Failed to save the progress note").

**Requested change:** evaluate "today" in the office's (or tenant's) timezone —
`offices.timezone` if present, else a tenant setting — and use the same zone
when stamping `created_at`/`signed_at`. **Acceptance:** a note created at 3 PM
office-local stays editable until office-local midnight.

---

### PN-10 — Timestamps are serialised without a timezone designator — **P2**

`ProgressNoteRead.created_at`/`signed_at`/`struck_off_at` come back as
`2026-09-07T21:31:35.890793` (UTC, no `Z`). `new Date()` in the browser parses
that as **local** time, so the list showed "9:31 PM" for a note written at
5:31 PM Eastern, and the client-side lock fallback drifted by the UTC offset.
The FE now pins naive values to UTC before parsing (`parseServerDateTime`), but
every other module that renders these timestamps has the same bug.

**Requested change:** emit RFC 3339 with an explicit offset (`…Z` or
`+00:00`) for all `datetime` fields — a `ORMModel` JSON encoder / tz-aware
columns fixes it globally. **Acceptance:** `created_at` ends in `Z`.

---

### PN-11 — No `updated_at` / `updated_by` on progress notes — **P3**

`ProgressNote` uses `CreatedAtMixin` only, so the legacy **Created / Modified**
column can only show the creation stamp, and a DOS correction (PN-8) leaves no
trace of who changed it or when. **Requested change:** add `updated_at` /
`updated_by` (+ `updated_by_name`) to the model and `ProgressNoteRead`.

---

### PN-12 — Legacy-imported note bodies are stored double-escaped (`~^^~lt;p~^^~gt;…`) — **P1**

**Evidence (audited 2026-09-10 against `GET /api/v1/progress-notes?size=200`,
pages 1–10 = 2,000 of 35,306 rows, 768 patients):**

| Symptom | Rows in sample | Example |
|---|---|---|
| `notes_html` has every `&` replaced by the token `~^^~` on top of the markup already being entity-escaped once | **1,932 / 1,980 legacy rows (98 %)** | `~^^~lt;p~^^~gt;Lips: Normal~^^~lt;/p~^^~gt;` ⇒ `&lt;p&gt;Lips: Normal&lt;/p&gt;` ⇒ `<p>Lips: Normal</p>` |
| `notes` (plain column) has a literal `?` where a non-breaking space (`&nbsp;`) was | 791 (40 %) | `Patient presented for?Periodic Exam. MHR` |
| `notes` lost its line breaks entirely (paragraphs run together) while `notes_html` still has one `<p>` per line | 384 (19 %) | `…MHR-- Soft Tissue Exam --Ext.Head/Neck: NormalLymph Chain: Normal…` |
| Trailing empty paragraph `<p>&nbsp;</p>` appended to the body | 845 | — |
| `notes` itself carries the `~^^~` encoding, and each paragraph is wrapped twice (`<p><p>…</p></p>`) | 1 (id 21434) | — |
| `notes_html` is stroke JSON, not HTML (Restorative freehand drawings persisted as progress notes; `{"type":"rx-draw",…}`) | 4 | — |

Only tokens `~^^~lt;`, `~^^~gt;` and `~^^~amp;` occur (33,591 / 33,591 / 2,020
times); the only entities after decoding are `&lt;`, `&gt;`, `&amp;`, `&nbsp;`,
and the only tags are `<p>`, `<br>` (plus `<span style="color…">` in app-written
rows). The pattern is consistent with the migration script escaping the HTML a
second time and then substituting `&` → `~^^~` to survive a delimiter-based
export. The 44 legacy rows without `notes_html` are clean plain text.

**Impact:** the Progress Notes grid and editor showed raw
`~^^~lt;p~^^~gt;…~^^~lt;/p~^^~gt;` for practically every migrated note, so clinical
history was unreadable. The plain `notes` column is not a usable fallback for
search or reports either (`?` mojibake, collapsed lines).

**Frontend workaround (shipped):** `src/features/progress-notes/noteContent.ts`
decodes `~^^~` → `&`, un-escapes one level, sanitises to an allow-list
(`p/br/span/b/i/u/…`, colour styles only), drops the stray empty/trailing
paragraphs and hides `rx-draw` rows from the list. The editor hydrates from the
decoded HTML, so any note re-saved through the app is written back clean.
Search/timeline text is derived from the decoded HTML rather than `notes`.

**Requested change (one-off data repair + import fix):**
1. Migration over `progress_notes` where `notes_html LIKE '%~^^~%'`:
   `notes_html = html_unescape(replace(notes_html, '~^^~', '&'))` (single
   un-escape pass, so `&amp;nbsp;` becomes `&nbsp;`), strip the trailing
   `<p>&nbsp;</p>`, and collapse `<p><p>` / `</p></p>` (row 21434). Apply the same
   to the one row whose `notes` column carries the token.
2. Regenerate `notes` from the repaired HTML (block tags → newline, entities
   decoded, `&nbsp;` → space) for the 791 `?`-mojibake and 384 collapsed rows —
   this is what `search=` and any server-side report should match against.
3. Fix the legacy importer so future migrations do not re-introduce the token.
4. (Optional) Move the 4 `rx-draw` rows to a dedicated `drawing_strokes` /
   `drawing_doc_id` payload — both columns already exist on `ProgressNoteRead`
   but are null on these rows.

**Acceptance:** `GET /api/v1/progress-notes` returns no `notes_html` or `notes`
containing `~^^~`; `notes` for the sampled ids 20001/20002/20003 contains
newlines and no `?` before "Periodic"/"severe"; a `search=Periodic%20Exam` query
matches row 20002.

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
| PN-8 | DOS (`note_date`) correctable after the prior-day lock | P1 | **patched locally** in backend service; needs restart/deploy |
| PN-9 | Lock day boundary uses UTC, not office-local day | P2 | notes lock at 8 PM Eastern; FE trusts `is_locked` |
| PN-10 | Naive (no-`Z`) timestamps parsed as local time | P2 | FE `parseServerDateTime` pins to UTC |
| PN-11 | No `updated_at`/`updated_by` on notes | P3 | Created column only |
| PN-12 | Legacy `notes_html` double-escaped with `~^^~` (= `&`); `notes` has `?` mojibake / lost newlines | P1 | FE `noteContent.ts` decodes + sanitises for display; server `search=` still broken for those rows |

PN-2..PN-5 and PN-7 have landed (2026-09-07 resync). PN-1 and PN-8 block legacy
behaviour; PN-6, PN-9..PN-11 are correctness/quality follow-ups.
