# Topaz Signature Capture — Backend Gap Report

> **Audience:** Backend team
> **Module:** Electronic signature capture (Topaz SigPlusExtLite V3 + on-screen fallback)
> **Frontend:** `src/features/signature/**` — one shared `SignatureCapture` component now used by
> Medical History (patient + dentist), Progress Notes (provider), Letters → Consent signing, and
> Security → Users (user signature). Diagnostics page: **Setup → Devices → Signature Pad (Topaz)**
> (`/setup/devices/signature-pad`).
> **Date:** 2026-09-10

---

## 1. What the frontend does today

The browser talks to the Topaz pad **locally** (browser extension → Topaz Native Messaging Host →
USB pad). The backend never talks to Topaz. After a capture the frontend holds a `SignatureResult`:

| Field | Source | Persisted today? |
|-------|--------|------------------|
| `signature_data` | JPEG data URL (Topaz) or PNG data URL (on-screen) | ✅ `patient_signatures.signature_data`, `patient_consents.signature_data`, `users.signature_data` |
| `signature_len` | `signature_data.length` | ✅ |
| `device_source` | `"topaz"` or `"web-pad"` | ✅ (`patient_signatures.device_source`, `users` signature `device_source`) |
| `signed_at` | workstation timestamp of the capture | ✅ `patient_signatures.signed_at` |
| `sig_string` | Topaz **SigString** — the vector stroke data (the actual biometric record) | ❌ **dropped** (SIG-1) |
| `point_count`, `stroke_count` | Topaz | ❌ dropped (SIG-2) |
| `device_model`, `device_serial` | Topaz pad model (e.g. `T-L(BK)462`) + serial | ❌ dropped (SIG-3) |
| `signature_method` on consents | `"topaz"` / `"drawn"` / `"scanned"` / `"verbal"` | ✅ sent (`"topaz"` is a new value — SIG-5) |

Existing endpoints used, unchanged:

- `POST /api/v1/patient-signatures` (`PatientSignatureCreate`) — Medical History patient/dentist, Progress Notes provider signature
- `POST /api/v1/patient-consents/{id}/sign` (`ConsentSignRequest`) — Letters consents
- `PATCH /api/v1/users/{id}` `signature_data` — Security → Users (the dedicated `PUT /users/me/signature` /
  `PUT /users/{id}/signature` endpoints exist and carry `device_source`; the Users screen still saves through
  the user PATCH — see SIG-6)

## 2. Gaps

| Gap ID | Title | Detail / current workaround | Severity |
|--------|-------|-----------------------------|----------|
| **SIG-1** | No column for the Topaz **SigString** | The SigString is the tamper-evident vector record (strokes, points, timing). The frontend captures it on every Topaz signature and has nowhere to send it, so only the rendered image is stored. Add `sig_string TEXT NULL` (+ `sig_format VARCHAR(20)` = `topaz_sigstring_v1`, `sig_compression SMALLINT`, `sig_encryption SMALLINT`) to `patient_signatures`, `patient_consents` and the user-signature store; accept them on `PatientSignatureCreate`, `ConsentSignRequest`, `UserSignatureUpdate`, `MedicalHistorySignRequest`. **Legacy note (verified 2026-09-10 on tenant 1):** `GET /patient-signatures` has 3,862 rows; every legacy row (`device_source = "0"`, 3,860 of them — only the 2 `web-pad` rows are data URLs) holds a raw Topaz SigString (`02008C00D5…`) in `signature_data`, i.e. the legacy import put SigStrings where images go. Migrate those into `sig_string` and set `signature_data` NULL (or render a JPEG server-side from the SigString with SigPlus) — the frontend cannot render a SigString as `<img>` and now shows "Topaz signature on file (legacy data — image not available)" for them. | **High** |
| **SIG-2** | No `point_count` / `stroke_count` | Cheap integrity/quality metadata Topaz reports; lets the backend reject empty or one-dot signatures and lets audit reports show them. Add two nullable integers to the same three tables. | Low |
| **SIG-3** | No device identity | Add `device_model VARCHAR(40)`, `device_serial VARCHAR(40)`, `device_vendor VARCHAR(20)` (`"topaz"`). `device_source` (max 20 on the user endpoint) is only the *method*. Model/serial identify **which pad in which room** captured it — needed for audit and for E-SIGN/UETA attribution. | Medium |
| **SIG-4** | Client-side SigString encryption is not viable | Topaz supports `SetSigStringFormat(encryption_mode, key, …)` but any key shipped in browser JS is public. The frontend sends **clear-text, lossless** SigStrings over HTTPS. Backend should encrypt at rest (column-level or KMS) and never return `sig_string` in list/read payloads by default (add `?include=sig_string` for the audit screen only). | Medium |
| **SIG-5** | `signature_method` vocabulary | `ConsentSignRequest.signature_method` documents `drawn / scanned / verbal`. The frontend now sends **`topaz`** for pad captures. Confirm it is accepted (free-text today) and add it to any enum / reporting code. Same value set should apply to `patient_signatures.device_source` (`topaz`, `web-pad`, legacy `"0"`). | Low |
| **SIG-6** | `PUT /users/me/signature` vs user PATCH | Two write paths for the same field. The Users screen writes `signature_data` through the user PATCH (no `device_source`). Either make the PATCH accept `device_source` + SIG-1/3 columns, or have the frontend switch to `PUT /users/{id}/signature` — tell us which is canonical and we will align. | Low |
| **SIG-7** | Document binding for non-medical-history signatures | `POST /patients/{id}/medical-history/sign` freezes a version + `content_hash` (MH-6 ✅). Progress-note signatures and consents have no `content_hash`; `patient_signatures.content_hash` exists but nothing fills it for them. Expose a `content_hash` the frontend can echo (or compute server-side from the rendered consent HTML / note body) so a later edit flips a `signature_status` to `stale` like MH does. | Medium |
| **SIG-8** | Signature audit trail | No events for capture started / completed / voided per signature. `POST /patient-signatures/{id}/void` exists with a reason; add `signature_audit` (`signature_id, event, actor_id, at, ip, user_agent, device_model, device_serial`) written by the sign/void endpoints so the "who signed on which pad from which workstation" question is answerable. Frontend can send `user_agent`/workstation hints in the create body if a field is added. | Medium |
| **SIG-9** | Size of `signature_data` | Topaz JPEGs at 900×300 are ~20–40 KB base64; PNGs from on-screen are ~20 KB. Fine in Postgres `TEXT`, but list endpoints (`GET /patient-signatures?size=50`) return every image inline. Add `?fields=` / an `include_image=false` flag or a `signature_image_url` (signed, short-lived) so lists don't ship megabytes. | Low |
| **SIG-10** | Medical-history sign endpoint not used yet | The frontend still stores MH signatures through `POST /patient-signatures` (append-only, no version binding). Switching to `POST /patients/{id}/medical-history/sign` needs SIG-1/3 fields on `MedicalHistorySignRequest` as well, otherwise the Topaz metadata is lost on that path too. Add them there in the same change. | Medium |

## 3. Proposed schema (all three signature stores)

```text
sig_string        TEXT          NULL   -- Topaz SigString, clear text, lossless (SIG-1)
sig_format        VARCHAR(24)   NULL   -- 'topaz_sigstring_v1'
sig_compression   SMALLINT      NULL   -- 0 none | 1 lossless | 2 lossy
sig_encryption    SMALLINT      NULL   -- 0 clear | 1 DES | 2 high (client always sends 0)
point_count       INTEGER       NULL   -- SIG-2
stroke_count      INTEGER       NULL
device_vendor     VARCHAR(20)   NULL   -- 'topaz'
device_model      VARCHAR(40)   NULL   -- 'T-L(BK)462', 'T-LBK755SE', …   (SIG-3)
device_serial     VARCHAR(40)   NULL
captured_user_agent VARCHAR(255) NULL  -- SIG-8
```

Request bodies to extend: `PatientSignatureCreate`, `PatientSignatureUpdate`, `MedicalHistorySignRequest`,
`ConsentSignRequest`, `UserSignatureUpdate`. Read models: add the same fields **except** `sig_string`,
which should be opt-in (SIG-4).

## 4. Frontend contract once delivered

The frontend already builds every value above in `SignatureResult`
(`src/features/signature/signatureModel.ts`). When the columns land, the only frontend change is adding
them to `signatureBodyFields()` and the three `sign` calls — no UI work.

---

## 5. ADA Dental Claim Form signatures (added 2026-09-12)

**Screen:** Patient → Ledger → claim → **DIRECT PRINT** → *Signatures (Topaz pad or on screen)*
(`src/features/claims/ada/ClaimSignatureDialog.tsx`, `adaClaimSignatures.ts`).

The ADA Dental Claim Form (2024) carries three signature lines. Each can now be captured with the same
shared `SignatureCapture` pad the Progress Notes / Medical History / Consent screens use, and the image
is printed on the form's signature line (with the capture date) instead of "Signature on File":

| ADA item | Who signs | `POST /patient-signatures` body | Printed |
|---|---|---|---|
| 36 Patient / Guardian consent | patient or guardian | `signature_type = "claim_patient_consent"`, `is_user_sig = false`, `signed_at`, `signature_data`, `device_source` | image + date on the Item 36 line |
| 37 Assignment of benefits | policyholder / subscriber | `signature_type = "claim_assign_benefits"`, `is_user_sig = false` | image + date on the Item 37 line |
| 53 Treating dentist certification | treating dentist | `signature_type = "claim_treating_dentist"`, `is_user_sig = true`, `signed_by_user_id` = signed-in user | image + printed name + date on the Item 53 line; falls back to `GET /users/{provider.user_id}/signature` |

Resolution order at print time: row pinned to the claim → latest active row of that `signature_type` on
the patient ("Signature on File") → (Item 53 only) the provider's user-account signature.

### Gaps

| Gap ID | Title | Detail / current workaround | Severity |
|--------|-------|-----------------------------|----------|
| **SIG-11** | `patient_signatures` has no claim binding | The row has `progress_note_id` and `consent_id` but no `claim_id`, so a signature cannot be tied to the claim it was captured for. The frontend keeps the three ids on the claim's fill-out record (browser `localStorage`, CLM-FO-1) — another workstation only sees the *latest* row of that type on the patient. **Ask:** add `claim_id UUID NULL` (FK `insurance_claims.id`) + `?claim_id=` filter on `GET /patient-signatures`, and accept it on `PatientSignatureCreate`. | **High** |
| **SIG-12** | `signature_type` vocabulary | Free text today. The frontend now writes `claim_patient_consent`, `claim_assign_benefits`, `claim_treating_dentist` (alongside whatever MH / PN / consents write). Please add them to any enum / reporting and confirm they are accepted unchanged (verified: 201 on tenant 1). | Low |
| **SIG-13** | No signer identity for a guardian | Item 36 may be signed by a parent / guardian. `PatientSignatureCreate` has no `signer_name` / `signer_relationship`; the printed form shows the image only. Add `signer_name VARCHAR(120)`, `signer_relationship VARCHAR(40)` (self / parent / guardian / POA) so the audit trail names who signed for a minor. | Medium |
| **SIG-14** | Treating-dentist signature lives on the *user*, not the provider | `GET /users/{user_id}/signature` needs `providers.user_id`; providers with no linked user (most migrated rows) have no signature on file and must sign per claim. Add a provider-level signature (`PUT/GET /providers/{id}/signature`, same columns as the user store) or expose `signature_data` on `ProviderRead`. | Medium |
| **SIG-15** | Item 53 "signed" state vs `is_user_sig` | The dentist certification is stored as a `patient_signatures` row with `is_user_sig = true` and `signed_by_user_id` = the signed-in user, which may be the front-desk user doing over-the-shoulder capture. Add `signer_user_id` (the dentist) distinct from `created_by`, or reuse `signed_by_user_id` and have the frontend pass the provider's `user_id` — tell us which. | Low |
| SIG-16 | Server-rendered claim form must embed the images | When ADA-BE-1 (server PDF) lands it must render these three rows (and the user/provider signature) on the signature lines; the frontend renderer (`adaClaimFormPdf.ts`, `Canvas.image`) shows the placement: Item 36 line 14 pt high × 208 pt wide, Item 37 line 17 × 208, Item 53 line 16 × 78 before the printed name. | Medium |
| SIG-9 (reminder) | `include_image=true` on the list | The claim pre-flight lists up to 100 active signatures **with images** to find the latest of each type; a `?signature_type=in:(…)` filter or `latest_per_type=true` would avoid shipping every MH / PN signature image. | Low |

Legacy note: SIG-1 still applies — a legacy row whose `signature_data` is a raw SigString cannot be
printed; the pre-flight shows "not captured" for it and the paper line stays blank.
