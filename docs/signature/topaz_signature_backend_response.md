# Topaz Signature Capture — Backend Response

> **Answers:** [topaz_signature_backend_devreport.md](topaz_signature_backend_devreport.md)
> **Alembic:** `b6c7d8e9f0a1` (applied on the dev database 2026-09-10)
> **Code:** [app/services/signature_service.py](../../app/services/signature_service.py) (the one home),
> [app/api/v1/signatures.py](../../app/api/v1/signatures.py) (routes),
> [app/schemas/signature.py](../../app/schemas/signature.py) (DTOs),
> [scripts/migrate_legacy_sigstrings.py](../../scripts/migrate_legacy_sigstrings.py),
> [tests/test_signature_capture.py](../../tests/test_signature_capture.py)
> **Date:** 2026-09-10

## 1. Status by gap

| Gap | Status | Where |
|-----|--------|-------|
| **SIG-1** SigString column | ✅ Shipped + legacy rows migrated | `sig_string`/`sig_format`/`sig_compression`/`sig_encryption` on all three stores |
| **SIG-2** point/stroke counts | ✅ Shipped, enforced | 422 `signature_empty` when `point_count < 2` or `stroke_count < 1` |
| **SIG-3** device identity | ✅ Shipped | `device_vendor`/`device_model`/`device_serial` on all three stores |
| **SIG-4** encrypt at rest, never on reads | ✅ Shipped | Fernet at rest; `…/sig-string` routes are admin-only and audited |
| **SIG-5** `signature_method` vocabulary | ✅ Shipped | `topaz` accepted and published; `device_source` vocabulary published |
| **SIG-6** user PATCH vs PUT | ✅ Decided | **`PUT /users/{id}/signature` is canonical** (details §4) |
| **SIG-7** document binding | ✅ Shipped | `progress_note_id`/`consent_id` on signatures, `content_hash` on consents + notes, `signature_status` everywhere |
| **SIG-8** audit trail | ✅ Shipped | `signature_audit_events` + `GET /signature-audit-events` |
| **SIG-9** list size | ✅ Shipped | `GET /patient-signatures?include_image=false` |
| **SIG-10** MH sign endpoint carries the block | ✅ Shipped | `MedicalHistorySignRequest` takes every SIG-1/2/3/8 field |

The **only frontend change** is the one the report already planned: add the
fields to `signatureBodyFields()` and the three `sign` calls. Nothing in the
request shapes is required — the on-screen pad still sends `signature_data` +
`device_source` and nothing else.

## 2. The request block (identical on every path)

Accepted by `POST /patient-signatures`, `PATCH /patient-signatures/{id}`,
`POST /patients/{id}/medical-history/sign`, `POST /patient-consents/{id}/sign`,
`PUT /users/me/signature`, `PUT /users/{id}/signature`, and the generic
`/patient-consents` create/update:

```json
{
  "signature_data": "data:image/jpeg;base64,…",
  "signature_len": 31240,
  "device_source": "topaz",
  "signed_at": "2026-09-10T14:03:11.412Z",
  "sig_string": "02008C00D5…",
  "sig_format": "topaz_sigstring_v1",
  "sig_compression": 0,
  "sig_encryption": 0,
  "point_count": 412,
  "stroke_count": 6,
  "device_vendor": "topaz",
  "device_model": "T-L(BK)462",
  "device_serial": "TLBK462-0091",
  "captured_user_agent": "Mozilla/5.0 … (workstation hint)"
}
```

Every write path runs the same `signature_service.normalise_capture` pass, so
the rules cannot drift between screens:

- **Defaults when a `sig_string` is sent**: `sig_format → topaz_sigstring_v1`,
  `sig_compression`/`sig_encryption → 0`, `device_source → topaz`,
  `device_vendor → topaz`. So the pad path can send just `sig_string` + the image.
- **`signature_len`** is recomputed from `signature_data` when omitted or `0`.
- **`captured_user_agent`** defaults to the request `User-Agent`; `signed_at`
  defaults to server now.
- **422 `signature_empty`** (SIG-2) when the pad reports `point_count < 2` or
  `stroke_count < 1`. Only judged when the count is sent — the on-screen pad
  reports neither, and a Topaz pad reports hundreds of points per stroke, so
  this only ever catches an empty pad or a single dot.
- **422 `invalid_signature_field`** for an unknown `sig_format` or a
  compression/encryption value outside `0..2`; **422 `invalid_sig_string`** for
  a SigString containing whitespace; **422 `sig_string_too_large`** above 1 MB;
  **422 `signature_too_large`** above 512 KB of image.
- `device_source`/`device_vendor` are lower-cased and trimmed but an
  **unrecognised source is stored as written** (the PROV-3 call — a 422 on save
  is a worse failure than an unfamiliar string). `device_model`/`device_serial`
  are trimmed to the column width rather than refused: they are pad-reported.

The rules, vocabularies and limits are published at
**`GET /metadata/signature-capture`** so the Signature Pad diagnostics page
reads them from one place.

## 3. SIG-4 — the SigString is encrypted at rest and never on a read model

`sig_string` is Fernet-encrypted (`app.core.crypto`, `ENCRYPTION_KEY` in
production) on every write path — the generic CRUD routes go through
`PatientSignatureCRUD` / `PatientConsentCRUD`, so a clear-text value cannot land
in the column from any client. The read models
(`PatientSignatureRead`, `PatientConsentRead`, `MedicalHistorySignature`,
`UserSignatureRead`) carry **`has_sig_string`** plus every other capture field,
but never the SigString itself.

The only ways out, all **admin-only and written to the audit trail as
`sig_string_exported`** (reading the biometric record is itself an auditable act):

| Route | Returns |
|-------|---------|
| `GET /patient-signatures/{id}/sig-string` | `SignatureVectorRead` — clear `sig_string`, format/compression/encryption, counts, device, `encrypted_at_rest`, `sig_string_readable` |
| `GET /patient-consents/{id}/sig-string` | same |
| `GET /users/me/signature?include_sig_string=true` / `GET /users/{id}/signature?include_sig_string=true` | `UserSignatureRead` with `sig_string` filled |

`sig_string_readable=false` means the row holds a token the current key cannot
open (a key rotation without re-encryption) — the API says so rather than
returning ciphertext as if it were stroke data. The report asked for
`?include=sig_string` on the generic get; the generic read model cannot change
shape per request, so it is a sub-resource instead.

## 4. SIG-6 — `PUT /users/{id}/signature` is canonical

- **`PUT /users/me/signature`** and **`PUT /users/{id}/signature`** (admin) are
  the canonical writes. They accept the full block, go through
  `normalise_capture`, **replace the whole block** (a field the client did not
  send does not survive from the previous pad) and log `captured` (first
  signature) or `replaced` on the audit trail.
- **`PATCH /users/{id}`** and `PUT /users/{id}/complete` still accept
  `signature_data` for compatibility, but they carry no capture metadata, so
  the server keeps the row coherent: `signature_len` and
  `signature_updated_at`/`signature_signed_at` are recomputed and the Topaz
  block + `device_source` are **cleared** — they described the previous image.
  **Please switch the Users screen to the PUT.**
- `GET /users/{id}/signature` now returns the block (`has_sig_string`,
  `sig_format`, counts, `device_*`, `captured_user_agent`, `signed_at`).

## 5. SIG-7 — document binding and `signature_status`

MH-6 already froze what a medical-history signature attests to. The same
semantics now cover the other two document kinds:

- **Progress notes.** `POST /patient-signatures` (and PATCH) accept
  **`progress_note_id`**. The note must be on the **same patient** (422
  `signature_document_mismatch` — a signature rendered inside one chart that
  attests to another patient's note is a records error), and the server computes
  `content_hash` = SHA-256 over the note's clinical content (`notes`,
  `notes_html`, tooth/surface/region, `note_date`, `drawing_strokes`), overriding
  any echo. `signature_type` defaults to `progress_note`.
  `POST /progress-notes/{id}/sign` stamps `progress_notes.content_hash` too, and
  `ProgressNoteRead` reports **`signature_status`** (`unsigned | signed | stale |
  unverifiable`).
- **Consents.** `POST /patient-consents/{id}/sign` with `status=signed` stamps
  `patient_consents.content_hash` over `rendered_html` (whitespace-collapsed, so
  a reflow is not an edit). `PatientConsentRead` reports `signature_status`
  (`unsigned | signed | stale | unverifiable | declined | voided`). A signature
  row may also name a **`consent_id`** and is hashed the same way.
- **`PatientSignatureRead.signature_status`**: `voided` / `superseded` for an
  inactive row; for a bound row `signed | stale | unverifiable`; **`null` for an
  unbound row** (a medical-history signature is judged by the medical-history
  document, and an unbound row with a client-echoed hash has nothing to compare
  to — the API does not guess).
- A signature with **no recorded hash is `unverifiable`, never `signed`**.

## 6. SIG-8 — `signature_audit_events`

One append-only row per lifecycle event, written **inside the same transaction**
as the change (an event can never outlive a rolled-back capture), on every
path including the generic CRUD routes:

| `event` | Written by |
|---------|-----------|
| `captured` | any sign/create; consent `status=signed`; first user signature |
| `superseded` | the previous medical-history signature on re-sign (MH-7) |
| `voided` | `POST /patient-signatures/{id}/void`, `DELETE /patient-signatures/{id}`, consent `status=voided` |
| `declined` | consent `status=declined` (with `reason`) |
| `replaced` | `PUT /users/…/signature` over an existing signature |
| `sig_string_exported` | every SigString read (§3) |

Columns: `entity_type` (`patient_signature | patient_consent | user`),
`entity_id`, `patient_id`, `actor_id`, `occurred_at`, **`ip`** (first hop of
`X-Forwarded-For`, else the peer), **`user_agent`** (request header),
`device_source`/`device_vendor`/`device_model`/`device_serial` (from the
capture), `signature_type`, `content_hash`, `reason`.
`GET /signature-audit-events?entity_type=&entity_id=&patient_id=&event=&actor_id=`
is the read (paged, any authenticated user). `captured_user_agent` on the row
itself is the client's workstation hint (defaults to the header).

`audit_logs` still gets its one-row-per-request entry; it could never answer
"who signed on which pad from which workstation" for a signature created inside
a composite write, which is what this table is for.

## 7. SIG-9 — `?include_image=false`

`GET /patient-signatures?include_image=false` returns every row with
`signature_data: null`, `image_omitted: true` and **`has_image`** telling you
whether one exists — a 50-row list stops shipping 50 JPEGs. The rows are
detached from the session before the column is blanked, so the strip can never
be flushed back as a NULL (covered by a test). The default is unchanged (images
inline), so no existing caller moves.

## 8. SIG-1 legacy note — applied on the dev database

The report's finding was right and slightly under-counted. Measured before the
move: 3,862 rows — **3,760 raw SigStrings** (`device_source="0"`), 98 migrated
data-URL images (`device_source="2"`, a second legacy code the report had not
seen), 2 `web-pad` data URLs, and **2 rows holding the literal string
`undefined`** (ids 3055/3115 — a legacy client bug, left alone and reported).

`scripts/migrate_legacy_sigstrings.py` (dry-run by default, `--apply`,
`--tenant-id`, `--users`) moves a SigString-shaped `signature_data` into
`sig_string` (encrypted), sets `sig_format=topaz_sigstring_v1` +
`device_vendor=topaz`, and NULLs `signature_data`/`signature_len`.
`device_source` stays `"0"` — it is the only provenance marker.

**Applied 2026-09-10: 3,760 moved, 0 raw SigStrings left in `signature_data`,
every `sig_string` encrypted; `users.signature_data` had only 2 real images.**
Those rows now read `has_image=false, has_sig_string=true`, so the FE's
"Topaz signature on file (legacy data — image not available)" branch can key off
`has_sig_string && !has_image` instead of sniffing the string. Until the move
runs on a given database, `legacy_sig_string_in_image=true` flags such a row.

**No JPEG is rendered server-side.** Turning a SigString back into an image needs
Topaz SigPlus (a Windows COM component) which the API server does not have. A
migrated row is exactly as renderable as before — just stored in the right
column, encrypted, and reported honestly. If a rendering is ever needed, the
audited `/sig-string` route hands the vector to a workstation that has SigPlus.

## 9. Tenancy fix that rode along

`patient_signatures` has no `tenant_id`, and the generic engine only scopes
models that carry one — so before this change **any tenant could read, PATCH or
void any signature by id**. `PatientSignatureCRUD` now scopes every read and
write through the owning patient (the `InsuranceCoverageRuleCRUD` precedent);
a foreign id is a 404, and a signature cannot be moved to another patient
(422 `signature_patient_immutable`).

## 10. Response shapes (additive unless noted)

- `PatientSignatureRead`: + every capture field except `sig_string`, +
  `has_image`, `image_omitted`, `has_sig_string`, `legacy_sig_string_in_image`,
  `signature_status`, `created_by_name`, `signed_by_name`, `voided_by_name`,
  `progress_note_id`, `consent_id`.
- `PatientConsentRead` (also the `/sign` response — it is the same component
  now): + capture fields, `content_hash`, `has_sig_string`, `signature_status`.
- `ProgressNoteRead`: + `content_hash`, `signature_status`.
- `MedicalHistorySignature`: + capture fields, `has_sig_string`.
- `UserSignatureRead`: + capture fields, `signed_at`, `has_sig_string`,
  `sig_string` (only with `include_sig_string=true`).
- New: `SignatureVectorRead`, `SignatureAuditEventRead`, `SignatureCaptureRules`.
- `GET /patient-consents/statuses` now lists `topaz` under `signature_methods`.
- New list filters: `/patient-signatures?device_source=&progress_note_id=&consent_id=&include_image=`,
  `/patient-consents?signature_method=`.

`openapi.json` is regenerated.
