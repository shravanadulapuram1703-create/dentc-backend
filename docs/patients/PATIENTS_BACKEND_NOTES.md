# Patients Module — Backend Implementation Notes (for the UI team)

> **Status:** the genuine backend gaps from `patients_backend_devreport.md` are implemented, persisted
> to the DB (`recondental_migrated`, Alembic `b8c9d0e1f2a3`), and in `openapi.json` (228 paths).
> **Regenerate Orval** (`npm run api:sync`).
> **Date:** 2026-06-05 · backend `/api/v1`.

---

## What shipped

| Gap | Endpoint(s) | Notes |
|---|---|---|
| **Patient Documents** | `GET/POST /patient-documents`, `GET/DELETE /patient-documents/{id}` | Multipart upload (`file` + `patient_id`, `office_id?`, `document_type?`, `description?`). Returns `file_url`; `file_path` is never exposed. ≤10 MB. |
| **Emergency Contacts** | CRUD `/patient-emergency-contacts` (`?patient_id=`) | Multiple contacts per patient (`name`, `relationship`, `phone`, `email`). |
| **Adjustments** | CRUD `/patient-adjustments` (`?patient_id=`, soft-delete via `is_void`) | The real adjustments resource. Codes come from `GET /definitions?group_code=adjustment`; payment methods from `?group_code=payment_method` (both seeded). |
| **Advanced search** | `GET /patients?…` | New typed filters: `dob`, `ssn`, `medicaid_id`, `email`, `phone`, `gender`, `patient_type`, `responsible_party_id`, `preferred_provider_id`, `chart_no`, plus ranges `created_at_from/to` (registration date) and `dob_from/to`. |
| **Balance enrichment** | `GET /patients/{id}/balance` | Added `insurance_balance`, `today_charges`, and `recent_activity.last_ins_amount` / `last_pat_amount` (amounts alongside the existing dates). |
| **Claim detail** | `GET /insurance-claims/{id}/detail` | Composed: `{ claim, procedures[], payments[], coverage[] }` (procedures = `patient_procedures` with that `claim_id`; payments = `payment_allocations`; coverage = `ledger_insurance_details`). |
| **Claim lifecycle** | `POST /insurance-claims/{id}/status` `{status}` | Server-sets `submitted_date`/`paid_date`/`close_date` and closes (`is_active=false`) on `closed`. |
| **Claim attachments** | `GET/POST/DELETE /insurance-claims/{id}/attachments` | Multipart upload, same storage model as documents. |
| **Progress Notes** | CRUD `/progress-notes` + `POST /progress-notes/{id}/sign` | New fields: `surface`, `region`, `signed_by`, `signed_at`, `is_struck_off`. Sign stamps the current user + time. Macros via existing `/note-macros`. |
| **Patient Note audit** | `patient-notes` now has `updated_by` | Plus `is_deleted`/`is_archived` filters — pass `?is_deleted=false` to hide soft-deleted notes. |
| **Duplicate check** | `POST /patients/check-duplicate` | `{first_name?,last_name?,dob?,ssn?,chart_no?}` → `{candidates:[{id,chart_no,first_name,last_name,dob,is_active,match_score}]}` (0–100 heuristic). Replaces the client-side heuristic. |
| **Metadata** | `GET /definitions?group_code=…` | Seeded `gender`, `title`, `marital_status`, `referral_type`, `pronoun`, `contact_pref`, `resp_party_rel`, `patient_type` (state already seeded). |

---

## ⚠️ Frontend-side / documentation (no backend change)

1. **Legacy `/patients/metadata*` does not exist** — use `GET /definitions?group_code=<gender|title|marital_status|referral_type|pronoun|contact_pref|resp_party_rel|state|patient_type>`. `key1`=value, `description`=label. Build one `useDefinitions(group_code)` hook.
2. **`home_office_name` / next-appointment / insurance summary** are not embedded on `PatientRead` — use `GET /patients/{id}/context` (aggregates balance + insurance summary + visit) or compose via `listOffices` / `listAppointments` / `listPatientInsurance`.
3. **`created_by`/`updated_by` are numeric ids** (no display name on the record) — resolve names via `listUsers`. (A denormalized `*_name` would require a join we didn't add.)
4. **Phantom patient-scoped ledger routes** (`/patients/{id}/payments|adjustments|claims|balances`) remain non-existent by design — use the flat resources: `patient-payments`, `patient-adjustments` (new), `insurance-claims`, and `getPatientBalance` (singular).

## ⛔ Still blocked (need product/infra decisions)

5. **Claim clearinghouse ops** — `validate` / `submit` (e-claim) / `refresh-status` are **not built**: they require an EDI/clearinghouse integration (Phase-4 EDI). `POST /insurance-claims/{id}/status` covers manual status transitions and close in the meantime.
6. **Print / PDF export** (patient summary, routing slip, walkout report) — **not built**: no PDF/report-generation backend yet. Needs a report-service decision before `GET /patients/{id}/summary.pdf` etc.
7. **Search by insurance carrier/plan (`ins_plan_id`) and `office_group_id`** — these are join-based (patient→insurance, office→group), not flat columns, so they're **not** on the `/patients` filter set. Use `listPatientInsurance?ins_plan_id=` to narrow, or request a dedicated `/patients/search` join endpoint if needed at scale.
8. **Document/attachment storage is local-filesystem** (served at `/uploads/...`); swap to object storage (S3/GCS) for production — the `{file_url}` contract is unchanged.

---

## Validation done
- Schema persisted (Alembic `b8c9d0e1f2a3`): `patient_documents`, `patient_emergency_contacts`,
  `patient_adjustments`, `claim_attachments` + `patients.medicaid_id`, `patient_notes.updated_by`,
  `progress_notes.{surface,region,signed_by,signed_at,is_struck_off}`.
- Tests + live checks green: document upload/list/delete, emergency-contact & adjustment CRUD, claim
  detail compose + status, progress-note sign, duplicate-check scoring, advanced `ssn` filter,
  `patient-notes` `is_deleted` filter, enriched balance fields. All routes tenant-guarded.
- `openapi.json` regenerated (228 paths, unique operationIds).
