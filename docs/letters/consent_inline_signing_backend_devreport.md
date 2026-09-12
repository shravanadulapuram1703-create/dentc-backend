# Consent Forms — Sign-in-Viewer: Backend Gap Report

> **Audience:** Backend team
> **Module:** Letters → consent forms signed inside the Report Viewer (patient reads the form and signs on the
> document; Topaz pad or on-screen through the shared `SignatureCapture`).
> **Frontend:** `src/features/letters/LetterPreviewModal.tsx` (viewer, generated + stored sources),
> `ConsentSignatureBlock.tsx` (live signature lines at the foot of the sheet), `letterPdf.ts` (signatures stamped
> into the stored PDF), `LettersPage.tsx` (history **View** / **Sign** open the viewer).
> **Date:** 2026-09-12

---

## 1. What the frontend does now

| Flow | Steps | Backend calls |
|------|-------|---------------|
| **Generated letter, signed in the viewer** | Print/Preview → patient reads → *Sign here* on the Patient/Guardian line (and optionally the Dentist/Hygienist line) → **Sign & Save to Chart** | 1. `POST /patient-documents` with the PDF **rebuilt with the signature image(s) stamped on the lines** (`document_type=consent-form`) · 2. `POST /patient-consents` (`status=printed`, `rendered_html`, `document_id`) · 3. `POST /patient-consents/{id}/sign` with `signature_data` + the full SIG field set (`sig_string`, `point_count`, `device_model`, … ) + `signer_name`, `signer_relationship`, `signature_method` (`topaz` / `drawn`) |
| **Stored consent (printed earlier), signed later** | Letter History → **Sign** (or **View**) → viewer shows `rendered_html` on the sheet + the stored PDF → sign on the line → **Record Signature** | `POST /patient-consents/{id}/sign` only |
| **Other outcomes** | viewer → *Other outcome…* (scanned copy / verbal / declined / void) | unchanged `ConsentSignDialog` |
| **Read-only** | signed consents open with the stored `signature_data` drawn on the line, signer, relationship, method and date | `GET /patient-consents` (already returned) |

Verified live 2026-09-12 on tenant 1, patient 83928: consent 14 signed from history (stored flow), consent 16 created
+ signed from a fresh preview (generated flow); the stored PDF (document 66) contains the stamped signature and date.

## 2. Gaps

| Gap ID | Title | Detail / current workaround | Severity |
|--------|-------|-----------------------------|----------|
| **CS-1** | Sign endpoint cannot attach the signed PDF rendition | `ConsentSignRequest` accepts **either** `signature_data` **or** `document_id`. In the stored flow (form printed earlier, signed later) the frontend records the signature but the consent's `document_id` keeps pointing at the **unsigned** PDF, and there is no way to hand over a signed rendition without losing `signature_data`. Accept both: `signature_data` (+ SIG fields) **and** an optional `signed_document_id` that replaces / supplements `document_id`; or render the signed PDF server-side from `rendered_html` + `signature_data` (LTR-5) and store it as the consent's document. Until then, only consents signed at preview time have a signed PDF on file. | **High** |
| **CS-2** | One signature per consent — no countersign storage | Consent forms print a second line (Dentist / Hygienist / Assistant / Office Manager, chosen in the dialog). The frontend captures it and stamps it into the PDF, but the record has a single `signature_data`. Add a `consent_signatures` child table (`consent_id, role, signer_user_id, signature_data + SIG fields, signed_at`) or at least `countersign_*` columns + `countersign_role`, and accept them on `/sign`. Today the countersign survives only inside the stored PDF (generated flow) and is lost entirely in the stored flow. | Medium |
| **CS-3** | `signed_at` ignored on consents | The frontend sends `signed_at` = capture time on the workstation; the stored `signed_at` is the server receive time (seen: `05:14:16Z` for a capture stamped a few seconds earlier). Either honour the client value (bounded to ±N minutes) or add `captured_at` so audit can show both. | Low |
| **CS-4** | `rendered_html` is the pre-signature HTML; no signed rendition on the record | The viewer re-opens a stored consent from `rendered_html` and overlays the stored `signature_data`, which works, but the backend has no immutable "as signed" rendition (HTML or PDF) other than what CS-1 would give. `content_hash` is now computed on sign (✅ SIG-7) — please document what it hashes (`rendered_html` only, or + `signature_data`) so the frontend can show "document unchanged since signing". | Medium |
| **CS-5** | Consent list returns every `signature_data` inline | `GET /patient-consents?patient_id=` ships each signed consent's full data-URL image (20–40 KB each) even though the history table only needs status/method/signer. Add `include_signature=false` (or the `image_omitted` pattern the signature reads already use) and keep the image on `GET /patient-consents/{id}`. The viewer would then fetch the single row on open. | Low |
| **CS-6** | `file_url` host is environment-bound | Documents saved from the local backend come back as `https://dentc-backend-…run.app/api/v1/patient-documents/{id}/content` (`storage_backend=local`), i.e. the Cloud Run host, not the API the frontend is talking to. The viewer's PDF tab / *Open PDF* for stored consents therefore points at the wrong environment in dev. Build `file_url` from the request's base URL (or return a relative path and let the client resolve it, as `document_href()` already does for relative values). | Medium |
| **CS-7** | `/sign` on a `printed` consent created by another user | Not reproducible here (single admin), but please confirm `/sign` does not require the signer to be the consent's `created_by` — a hygienist commonly signs what the front desk printed. | Low |
| **CS-8** | Signature vocabulary on consents vs `patient_signatures` | Consents store `signature_method` (`topaz` / `drawn` / `scanned` / `verbal`) **and** `device_source` (`topaz` / `web-pad`); patient/user signatures store only `device_source`. Consider one shared enum (`capture_method`) across the three stores so reports can group by capture device without mapping two vocabularies. | Low |

## 3. What is already delivered (no action)

- SigString + device columns on `ConsentSignRequest` (SIG-1..3) — the frontend sends them (`signatureBodyFields()`).
- `content_hash` on sign (SIG-7 for consents), `signature_status` on reads, `has_sig_string` flag.
- `signature_method: "topaz"` accepted (SIG-5).

## 4. Frontend contract once CS-1 lands

`LetterPreviewModal.onRecordStored` will upload the rebuilt signed PDF (`build_letter_pdf(... signatures)`) and pass
its id as `signed_document_id` alongside `signature_data`; no other change is required.
