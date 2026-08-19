# Letters — backend dev report

Module: **Letters (New)** — legacy Denticon print-menu → Letters dialog, Report Viewer,
"Save PDF file".
Frontend: `src/features/letters/**`, route `/patient/:patientId/letters`.
Verified live against the local backend (tenant 1) on 2026-08-18 with patient 83867.

---

## 1. What is already there (no work needed)

The backend covers this module better than most. All four resources exist and are seeded:

| Resource | Endpoint | State |
| --- | --- | --- |
| Letter catalog | `GET/POST/PATCH/DELETE /api/v1/letter-templates` (tag *Communications*) | **153 rows seeded**, real `body_html` |
| Per-office assignment | `GET/PUT /api/v1/offices/{office_id}/letter-templates` (tag *Office Assignment*) | endpoint works, **table empty** — see LTR-7 |
| Consent audit record | `GET/POST/PATCH/DELETE /api/v1/patient-consents` (tag *Patients*) | works; verified a real POST |
| Binary store | `GET/POST /api/v1/patient-documents` (tag *Patients*) | works; verified a real 92 KB PDF upload |

`letter_type` splits the catalog into the legacy "Letter Group" dropdown:

```
C 79  Patient Consent          I 23  Insurance & Treatment
F 17  Financial / Collection   E 13  Email Templates
S  8  Statements & Disclosures A  7  Appointment Letters
M  4  Marketing Letters        D  2  Referral Letters
```

Template bodies use `#TOKEN#` merge fields (56 distinct across the corpus) and a small
HTML subset (`br div strong u span ul ol li`), with `div.dvfrom` / `div.dvto` marking the
return- and recipient-address blocks that drive Envelope Printing.

**Verified end to end:** dialog → merge → preview → PDF → `POST /patient-documents`
(`document_type=consent-form`, id 27) → `POST /patient-consents` (id 1, `document_id=27`,
`status="printed"`, `rendered_html` retained).

---

## 2. Gaps

### LTR-1 — Consent PDFs are written to local disk, not `gs://reco-documents/consent-forms/` **(blocking for production)**

The practice keeps all consent forms in the cloud-storage bucket
**`reco-documents/consent-forms`**. `POST /api/v1/patient-documents` currently writes to
the app server's local filesystem and returns a server-relative path:

```json
{
  "id": 27,
  "document_type": "consent-form",
  "file_name": "a01-informed-consent-for-extraction-83867-2026-08-18.pdf",
  "file_url": "/uploads/patient_documents/83867/44b426dedc44432fa954015de19619ff.pdf"
}
```

Consequences: the PDFs do not survive a container restart on Cloud Run, they are not in
the bucket the practice actually reads, and nothing else in the estate can find them.

**Asks:**

1. Back `patient-documents` with GCS. Route `document_type=consent-form` to
   `gs://reco-documents/consent-forms/{tenant_id}/{patient_id}/{uuid}.pdf`; keep other
   document types on their existing prefix.
2. Return `file_url` as a **fully-qualified HTTPS URL** (signed URL, or a
   `GET /api/v1/patient-documents/{id}/content` proxy that streams the object with the
   caller's tenant/RBAC checks applied). The frontend must not hold bucket credentials
   and cannot address `gs://` from a browser.
3. Expose the bucket/prefix actually in use on the document row (e.g. `storage_bucket`,
   `storage_path`) so the UI can show provenance and so a migration of existing rows is
   auditable.
4. If blank consent-form masters already live in that bucket, add
   `GET /api/v1/consent-forms` (list the bucket's PDFs) — right now the letter catalog in
   `letter-templates` is the only source of consent content, and the two must not drift.

Until this lands the frontend sends the intended folder in `description`
(`"consent-forms/{template name}"`) so the mapping is recoverable.

### LTR-2 — `letter_type` codes have no `/definitions` group

`letter_type` is a bare single character (`A C D E F I M S`). There is no
`definition-groups` row that maps code → label, so the frontend hardcodes the eight group
names (`src/features/letters/lettersModel.ts`). **Ask:** seed a `LETTERTYPE` definition
group (`key1` = code, `description` = label) so Setup can rename/add groups.

### LTR-3 — Merge fields with no backend source

| Token(s) | Missing data | Current fallback |
| --- | --- | --- |
| `#PAT_PREF_PROV_Address/CITY/STATE/ZIP/PHONE#` | `ProviderRead` has no address or phone columns | the office's address/phone |
| `#MARKET_NAME/ADDRESS/CITY/STATE/ZIP/PHONE#` | no marketing/practice-address resource | the office block |
| `#OFFICE_CNAME#` | no corporate/DBA name on `OfficeRead` | `office.name` |

30 templates use the `#MARKET_*#` block and 10 use the provider letterhead block, so these
letters currently print the office address in place of the intended one.

### LTR-4 — `#TX_PLAN_TH_NUMBER#` has no context

One template interpolates a treatment-plan tooth number. The Letters dialog has no
treatment-plan or procedure context to bind it to; it renders blank and is listed in the
preview's "printed blank" warning. **Ask:** either drop the token from the template or
define how a letter is launched from a treatment plan.

### LTR-5 — No server-side render/merge/export endpoint

There is no `POST /api/v1/letter-templates/{id}/render`. Every letter is merged and
rendered to PDF in the browser (jsPDF, `src/features/letters/letterPdf.ts`). Two
consequences:

- The merge-field catalog is duplicated in the frontend and will drift from whatever the
  legacy engine did.
- **Batch letter runs are impossible.** Nine seeded templates are explicitly batch
  collection letters (`CS001…CS009 - Batch Coll N Letter`); running those over a
  collections queue needs a server-side job, not a per-patient click.

**Ask:** `POST /api/v1/letters/render` `{template_id, patient_id, options}` →
`{rendered_html, unresolved_tokens[]}`, plus a batch variant that takes a patient list and
returns a job id.

### LTR-6 — No aggregate letter-context endpoint

Building the merge context takes 2–6 round trips (`/patients/{id}`, `/offices/{id}`,
`/referrals`, `/appointments`, `/responsible-parties/{id}` or `/patients?responsible_party_id=`,
and `/patients/{id}/balance` for collection letters). The balance call alone is **~28 s
cold** (measured), so the frontend only issues it when the chosen template actually
contains `#RP_TOTAL_BAL#`. **Ask:** `GET /api/v1/patients/{id}/letter-context`.

### LTR-7 — Office ↔ letter-template assignment is unseeded

`GET /api/v1/offices/{id}/letter-templates` returns `[]` for **every** office checked
(1, 9). The dialog therefore falls back to the full tenant catalog and shows
"No letters are assigned to this office yet". **Ask:** seed the join from the legacy data,
or confirm that "unassigned = all" is the intended semantic.

### LTR-8 — Migrated `body_html` contains `?` mojibake

**21 of 153 templates** have curly quotes and apostrophes replaced by a literal `?`:

- `PC037`: `also known as ?bleaching?`
- `Post operative Letter`: `It?s been several months`, `We?re always here`

This prints on real patient-facing consent forms. **Ask:** re-run the migration with the
source encoding (cp1252 → utf-8), or repair in place. Affected: AP002, AP003, PC001,
PC012, PC027, CL022, CL024, IL003, OR003, OR004, OR005, OR007 and 9 more.

### LTR-9 — `channel` column polluted by the migration

```
L: 121   null: 17   D: 4
'policies': 9        'if needed please lea': 1        'or responsibilities ': 1
```

11 rows hold letter *body text* in `channel`, which means a field-offset error in the
importer — worth checking whether adjacent columns are shifted on those rows too.
Also: `title` is null on **103 of 153** rows, so only `name` is usable as a heading.

### LTR-10 — Consent signing is modelled but not implemented

`PatientConsentRead` carries `signature_data`, `signed_by`, `signed_at` and `status`, but
there is no endpoint to capture a signature, no defined `status` vocabulary, and no way to
attach a scanned wet-signed copy back to an existing consent row. The frontend writes
`status: "printed"` and leaves the signature fields null. **Ask:** publish the status enum
and add `POST /api/v1/patient-consents/{id}/sign` (base64 signature image or an uploaded
document id).

### LTR-11 — `created_at` is a naive timestamp that is actually UTC

`"created_at": "2026-08-19T02:05:11.828300"` — no `Z`, no offset. `new Date()` reads it as
local time, which dates a letter printed at 22:05 on the 18th as the 19th. The Letters
history pins it to UTC client-side (`fmt_stamp` in `LettersPage.tsx`). **Ask:** serialise
timezone-aware ISO-8601. This affects every module, not just Letters.

### LTR-12 — `/patient-documents` list has no filters or paging

`ListPatientDocumentsParams` is `{ patient_id }` only — no `document_type`, no `page`/
`size`, and the response is a bare array rather than the paginated envelope every other
list endpoint uses. The Letters history therefore fetches every document a patient has and
filters client-side. **Ask:** add `document_type` + standard paging, matching the rest of
the API.

---

## 3. Frontend notes for whoever picks this up

- `src/features/letters/mergeFields.ts` holds the **complete** 56-token catalog. Any token
  the backend adds must be registered there or it renders blank and is reported in the
  viewer's warning strip.
- Merged values are HTML-escaped and the preview is rebuilt from a whitelisted block
  structure (`letterHtml.blocks_to_html`), so a template row cannot inject markup into the
  app. Keep that property if the render moves server-side.
- jsPDF's built-in Helvetica is WinAnsi-only; `letterPdf.pdf_safe()` folds typographic
  punctuation to ASCII before drawing. Remove it only if a Unicode font gets embedded.
- Envelope Printing prepends a #10 landscape page (684 × 297 pt) built from the template's
  `dvfrom`/`dvto` blocks, falling back to the office/patient address.
