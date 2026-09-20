# Consent Forms — Sign-in-Viewer: Backend Response

> **Answers:** [consent_inline_signing_backend_devreport.md](consent_inline_signing_backend_devreport.md)
> **Alembic:** `7c862ec97e84` (applied on the dev database 2026-09-12)
> **Code:** [app/services/patient_extra_service.py](../../app/services/patient_extra_service.py) (`sign_consent`,
> countersigns), [app/services/signature_service.py](../../app/services/signature_service.py)
> (`resolve_signed_at`, `capture_method_for`, consent enrich),
> [app/api/v1/patients_extra.py](../../app/api/v1/patients_extra.py) (`consents_router`),
> [app/services/document_store.py](../../app/services/document_store.py) (CS-6),
> [tests/test_consent_inline_signing.py](../../tests/test_consent_inline_signing.py)
> **Date:** 2026-09-12

## 1. Status by gap

| Gap | Status | Where |
|-----|--------|-------|
| **CS-1** signed PDF rendition on `/sign` | ✅ Shipped | `signed_document_id` accepted **with** `signature_data`; kept beside `document_id` |
| **CS-2** countersign storage | ✅ Shipped | `consent_signatures` child table; `countersigns[]` on `/sign` + `POST …/countersign` for the stored flow |
| **CS-3** `signed_at` ignored | ✅ Shipped | client value honoured within 15 min; `captured_at` + `signed_at_source` always recorded |
| **CS-4** as-signed rendition + what `content_hash` hashes | ✅ Shipped | `signed_rendered_html` frozen on sign; hash documented and published |
| **CS-5** list ships every image | ✅ Shipped | `GET /patient-consents?include_signature=false` (`image_omitted` / `has_image`) |
| **CS-6** `file_url` host is environment-bound | ✅ Shipped | built from the **request origin**; `PUBLIC_API_BASE_URL` is only the out-of-request fallback |
| **CS-7** `/sign` requires the creator? | ✅ Confirmed no | any user of the practice; covered by a test |
| **CS-8** two vocabularies | ✅ Shipped | derived `capture_method` on all three stores, published |

Frontend contract is the one the report planned: upload the rebuilt signed PDF and
pass its id as `signed_document_id` alongside `signature_data`. Nothing else changes.

## 2. CS-1 — `signed_document_id` beside `document_id`

`ConsentSignRequest` now takes any combination of `signature_data` (+ the Topaz
block), `document_id` (the scanned wet copy) and **`signed_document_id`** (the PDF
rebuilt with the signature stamped on the lines). The two document ids are
different things and are stored in two columns: `document_id` stays the printed /
scanned copy, `signed_document_id` is the signed rendition. Both must belong to the
same tenant **and** the same patient as the consent (422
`document_patient_mismatch` naming the field). `signature_method` follows the
*capture*, not the presence of a document — a pad signature that also hands over
its signed PDF is still `topaz`; only a bare `document_id` defaults to `scanned`.

A `signed` outcome needs at least one of the three; `declined` / `voided` need none.

## 3. CS-2 — countersignatures

New table `consent_signatures` (one row per line): `role` (`dentist | hygienist |
assistant | office_manager | other`, published), `signer_user_id`,
`signer_provider_id`, `signer_name`, the full capture block (`signature_data`,
SigString encrypted at rest, counts, pad identity, `captured_user_agent`),
`signed_at`, void columns. Two ways in:

- **Generated flow** — `countersigns: [{role, signature_data, …}]` on `/sign`,
  written in the same transaction as the patient signature.
- **Stored flow** — `POST /patient-consents/{id}/countersign` after the patient
  signed (a hygienist countersigning at the chair what was printed earlier).

Reads: `GET /patient-consents/{id}/signatures?include_image=` lists the lines, and
`PatientConsentRead.countersigns[]` embeds them (metadata only; the image is on
the sub-resource with `include_image=true`). `POST …/signatures/{sid}/void` voids a
line with a reason. Every line goes through the same `normalise_capture` pass as
the patient signature and is written to `signature_audit_events`.

## 4. CS-3 — the capture time

`signed_at` on `/sign` is honoured when it is within **15 minutes** of the server
clock (`CONSENT_SIGNED_AT_TOLERANCE_MINUTES`); outside that window the server time
is stored. Either way the row records what happened: `captured_at` is the raw
client value (kept even when rejected, so audit can show both), and
`signed_at_source` is `client` or `server`. A missing or unparseable value is
`server`.

## 5. CS-4 — the as-signed rendition, and what `content_hash` covers

`content_hash` is SHA-256 over **`rendered_html` only**, whitespace-collapsed — it
does **not** include `signature_data`, the countersigns or any document id.
That is deliberate: the hash answers "is the document the patient read still the
document on the record", and a re-serialisation that only reflows the markup is
not an edit. The rule is published at `GET /metadata/signature-capture →
consent_content_hash`.

On `status=signed` the server also freezes **`signed_rendered_html`** — the HTML
exactly as it stood when signed, immutable afterwards. A later edit to
`rendered_html` flips `signature_status` to `stale` while `signed_rendered_html`
still shows what was signed. With CS-1 the signed PDF is the third rendition.

## 6. CS-5 — `?include_signature=false`

`GET /patient-consents?include_signature=false` returns every row with
`signature_data: null`, `image_omitted: true` and `has_image` (same pattern as the
signature reads). The rows are detached before the column is blanked so the strip
can never flush back as a NULL. `GET /patient-consents/{id}` always carries the
image. The default list behaviour is unchanged.

## 7. CS-6 — `file_url` follows the request

`document_store.public_url` builds `file_url` from the **origin the current
request arrived on** (`RequestContextMiddleware` parks scheme + host, honouring
`X-Forwarded-Proto` / `X-Forwarded-Host`), so a document saved through a local
backend links to that backend and one saved through Cloud Run links to Cloud Run.
`PUBLIC_API_BASE_URL` is now only the fallback **outside** a request (scripts, the
reminder job). When it is unset, URLs stay relative and the client resolves them.

## 8. CS-7 — confirmed

`/sign`, `/countersign` and the void routes check tenant + patient ownership only.
The signer is never required to be the consent's `created_by`; a test signs a
consent created by another user.

## 9. CS-8 — one `capture_method`

Every signature read (`PatientSignatureRead`, `PatientConsentRead`,
`UserSignatureRead`, provider signature, countersign lines) now carries a derived
**`capture_method`** ∈ `topaz | drawn | scanned | verbal | legacy | unknown`,
folded from `device_source` + (consents) `signature_method` + whether a SigString /
image is present. The stored columns are untouched — `device_source` stays the raw
device token and `signature_method` the consent outcome — so nothing existing
breaks and reports can group on one field. Vocabulary and the folding rule are
published at `GET /metadata/signature-capture`.

## 10. Response shapes (additive)

- `PatientConsentRead`: + `signed_document_id`, `captured_at`, `signed_at_source`,
  `signed_rendered_html`, `capture_method`, `image_omitted`, `has_image`,
  `countersigns[]`.
- New `ConsentSignatureRead` (countersign line), new routes
  `GET /patient-consents/{id}/signatures`, `POST /patient-consents/{id}/countersign`,
  `POST /patient-consents/{id}/signatures/{sid}/void`.
- `ConsentSignRequest`: + `signed_document_id`, `countersigns[]`.
- `GET /metadata/signature-capture`: + `capture_methods`, `capture_method_rule`,
  `consent_countersign_roles`, `consent_signed_at_tolerance_minutes`,
  `consent_content_hash`.

`openapi.json` is regenerated.
