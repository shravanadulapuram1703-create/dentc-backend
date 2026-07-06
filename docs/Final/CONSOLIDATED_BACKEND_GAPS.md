# DentC — Consolidated Backend Gaps Report

> **Audience:** Backend team
> **Source:** Aggregated from 29 per-module frontend dev-reports under `docs/**/*_backend_devreport.md`.
> **Purpose:** Single hand-off list of every backend gap the frontend hit while modernizing each module — missing endpoints, missing fields, wrong/inconsistent behavior, and un-enumerated code domains, each with the frontend workaround currently in place.
> **Date:** 2026-07-05

---

## 1. How to read this

- **Gap ID** — the identifier used in the module's own dev-report (`docs/<module>/*_backend_devreport.md`). Use it to trace back to full detail.
- **Workaround** — what the frontend does *today* to ship without the backend. Every workaround is a source of drift, N+1 latency, or unpersisted data.
- **Severity** — as stated by each module report: **Blocker/Critical** (feature is broken or data is silently lost), **High** (major workaround / not scalable), **Medium** (audit/UX/consistency), **Low** (nice-to-have / parity polish).

### Totals
- **~90 setup/admin gaps**, **~60 clinical gaps**, **~85 patient/transaction/platform gaps** documented.
- Cross-cutting themes recur far more often than one-off gaps — **fix the themes in §2 first** and a large fraction of the individual rows below collapse.

---

## 2. Cross-cutting themes (fix these first — highest leverage)

These patterns appear across most modules. Addressing them centrally resolves dozens of individual rows.

| # | Theme | Appears in | What to do |
|---|-------|-----------|------------|
| T1 | **No aggregation / roll-up endpoints** — everything is per-record CRUD; all KPIs, AR, aging, collections, dashboards computed client-side over truncated lists | Dashboard, Reports, Transactions, Account Ledger | Add office/tenant-scoped summary endpoints (financial-summary, collections, AR, aging, dashboard/summary) |
| T2 | **`*_by` fields are numeric ids with no name** — every "Modified By / Created By" renders as "User #385" | Progress Notes, Perio, Charting Setup, Notes Macros, Insurance, Users, Transactions | Embed `*_by_name` on read models (pattern already exists on some), or a bulk users-lookup |
| T3 | **Missing `updated_at` / `updated_by` audit columns** | Notes Macros, Charting (materials), Custom Toolbar, Users, Perio, Ledger, Progress Notes | Standardize a `TimestampMixin` (created/updated at+by) across auditable resources |
| T4 | **No `office_id` filter on list endpoints** (or param accepted but ignored server-side) — forces client-side filtering of whole tenant | Scheduler, Office Assignment, Reports, Users, Insurance | Honor `office_id` server-side on all list endpoints |
| T5 | **Un-enumerated status/code strings** — `status`, `carrier_type`, `coverage_type`, `category`, `referral_type`, `elig_status` are free-text with no enum/lookup; UI shows raw codes | Scheduler, Dashboard, Reports, Insurance, Referrals, Notes Macros, Medical | Expose `/definitions` groups (or enums) and document the code domain for each |
| T6 | **N+1 fan-out from thin read models** — appointment/lab/ledger feeds return ids only, so the UI fires one `GET /patients/{id}` (etc.) per row | Scheduler, Scheduler Appointments, Lab Tracking, Account Ledger | Denormalize `*_name` and key fields onto the list/feed read models |
| T7 | **No bulk / transactional writes** — save-32-teeth, copy-toolbar, replace-items = N individual calls, non-atomic, partial-failure risk | Perio, Custom Toolbar, Office Assignment, Pick List (partly resolved) | Provide bulk upsert / atomic replace endpoints |
| T8 | **No server-rendered export (PDF/Excel) & no attachments-to-record linkage** — all PDFs built client-side (jsPDF); uploaded docs orphan at patient level | Reports, Treatment Plans, Progress Notes, Prescriptions, Lab Tracking, Transactions | Server-side export endpoints; add record-scoped attachment FK |
| T9 | **Soft-delete vs hard-delete inconsistency** — some DELETEs flip `is_active`, siblings hard-delete; deleted rows still returned in lists | Perio, Restorative, Treatment Plans, Fee Schedules | Pick one convention per family; add `include_deleted=false` filtering |

---

## 3. Platform / Infrastructure (blocking)

| Module | Gap ID | Title | Description / Workaround | Endpoint / Resource | Severity |
|--------|--------|-------|--------------------------|---------------------|----------|
| Dashboard | 6 | **List-endpoint latency** | Live-verified 27–55s per list query against 61k patients; `?size=1` count ≈54s; login ≈10s. Makes the whole app feel broken. | All list endpoints | **Critical** |
| Authentication | 2.1 | Forgot password — request reset | Missing; login "Forgot password" is a dead end. | `POST /auth/forgot-password` | High |
| Authentication | 2.2 | Reset password — validate token | Missing; cannot verify reset link before showing form. | `POST /auth/reset-password/validate` | High |
| Authentication | 2.3 | Reset password — submit | Missing; cannot set new password from token. | `POST /auth/reset-password` | High |
| Authentication | 2.4 | Legacy activation — verify user | Missing; legacy-user activation wizard step stubbed. | `POST /auth/legacy-user/verify` | High |
| Authentication | 2.5 | Legacy activation — create password | Missing; cannot complete legacy activation. | `POST /auth/legacy-user/create-password` | High |
| Patient Context | PDP-1 | Read user's last patient | No endpoint; persisted in localStorage only. | `GET /users/me/last-patient` | High |
| Patient Context | PDP-2 | Persist user's last patient | No write endpoint. | `PUT /users/me/last-patient` | High |
| Patient Context | PDP-3 | Storage column | No `last_patient_id` on users table. | users table | High |
| Patient Context | PDP-4 | Tenant isolation on last-patient | Must enforce user-only + tenant isolation. | endpoint logic | High |
| Patient Context | PDP-5 | Recent-patients list | No history endpoint (legacy nav has "Recent Patients"). | `GET /users/me/recent-patients` | Low |
| Help | HELP-1 | Production Jira proxy | Direct mode exposes token + needs CORS; prod needs a backend proxy for create-issue / ticket-status. | `POST/GET {VITE_JIRA_PROXY_URL}` | High |

---

## 4. Scheduler & Appointments

| Gap ID | Title | Description / Workaround | Endpoint / Resource | Severity |
|--------|-------|--------------------------|---------------------|----------|
| SCHED-1 | Operatory → provider linkage | `OperatoryRead` missing `provider_id`; operatory auto-fill to provider broken; UI hardcodes blank. | `GET /operatories` | High |
| SCHED-2 | Office-scoped reference data | Operatories/providers/config/procedure-types not office-filtered; all tenants see all offices. | `GET /operatories?office_id=`, `/providers?office_id=` | High |
| SCHED-3 | New-patient-during-scheduling | FE passes string `patient_id` ("NEW"/chart_no); auto-create contract unclear. | `POST /appointments` | High |
| SCHED-4 | Status definitions + colors | Status list & colors hardcoded in UI; backend enum not exposed. | `GET /definitions?group_code=appt_status` | High |
| SCHED-6 | Patient context enrichment | "Go to patient" writes hardcoded patient data instead of fetching; downstream gets fabricated facts. | `GET /patients/{id}/context` | High |
| SCHED-7 | Denormalized names on AppointmentRead | No `patient_name`/`provider_name`/`operatory_name`; N+1 `GET /patients/{id}` per appointment. | `GET /appointments/scheduler` | High |
| SCHED-5 | Status-transition timestamps | `confirmed/checked_in/checked_out` timestamps not persisted; owner (client vs server) unclear. | `PATCH /appointments/{id}/status` | Medium |
| SCHED-8 | Responsible party + patient type | `responsible_party_id`, `patient_type` missing on PatientRead; FE hardcodes. | `GET /patients` | Medium |
| SCHED-9 | Week/Month range fetching | Views hardcode single-day fetch; month-range support unconfirmed. | `GET /appointments?date_from=&date_to=` | Low |
| SCHED-10 | procedure_label validation | Free-text, no FK enforcement; client vs server validation unclear. | `POST /appointments` | Low |
| SCHED-APPT-2 | Cancellation metadata not persisted | `PATCH .../status` accepts only `{status}`; note/reason/call-list flag collected but dropped. | `PATCH /appointments/{id}/status` | High |
| SCHED-APPT-1 | Created/modified-by attribution | AppointmentRead missing `created_by`/`updated_by`; Details pop-out shows dates only. | `GET /appointments/{id}` | Medium |
| SCHED-APPT-3 | Same-day family/account feed | Cannot filter by responsible-party; family same-day appts not retrievable. | `GET /appointments?responsible_party_id=&date=` | Medium |
| SCHED-APPT-4 | Per-block enrichment | Feed missing `has_alert`, `patient_age/gender`, `service_summary`, `insurance_eligibility`; N+1 fan-outs. | `GET /appointments/scheduler` | Medium |
| SCHED-APPT-6 | Per-line estimated-patient portion | AppointmentProcedureRead missing `est_patient`; FE derives naively, ignores COB. | `GET /appointment-procedures` | Medium |
| SCHED-APPT-7 | Account balance on feed | Balance needed for $ badge; only per-patient → N+1. | `GET /appointments/scheduler` | Medium |
| SCHED-APPT-5 | `posted_on` timestamp | Only `is_posted` boolean; no timestamp; denormalized feed omits `is_posted`. | `GET /appointments/{id}` | Low |

---

## 5. Patients, Transactions, Ledger & Reports

### 5a. Patients
| Gap ID | Title | Description / Workaround | Endpoint | Severity |
|--------|-------|--------------------------|----------|----------|
| PATIENTS-1 | Patient documents | No upload/list/download/delete for patient docs. | `GET/POST /patient-documents` | High |
| PATIENTS-6 | Patient-scoped ledger writes (phantom paths) | FE assumes non-existent `/patients/{id}/payments`, `/adjustments`; no adjustments resource. | `POST /patients/{id}/payments`, `/adjustments` | High |
| PATIENTS-7 | Composed claim-detail | Claim endpoints are flat records; no `procedures[]`/coverage/payment composition. | `GET /insurance-claims/{id}` | High |
| PATIENTS-8 | Claim clearinghouse ops + attachments | No validate/submit/status-refresh; no claim attachments. | `POST /insurance-claims/{id}/validate|submit|attachments` | High |
| PATIENTS-2 | Emergency contacts (separate entity) | Only inline guardian fields; no multi-contact resource. | `.../patient-emergency-contacts` | Medium |
| PATIENTS-3 | Advanced patient search | Only free-text + chart_no; no SSN/DOB/insurance/provider/office/type filters. | `GET /patients` (extend) | Medium |
| PATIENTS-4 | Duplicate-check | No real endpoint; FE heuristics via `listPatients`. | `POST /patients/check-duplicate` | Medium |
| PATIENTS-9 | Progress notes feature set | Missing `signed_by`/`signature_date`/tooth-surface/macros/attachments/linked procedures. | `GET/POST /progress-notes` (extend) | Medium |
| PATIENTS-5 | Balance shape | Missing `insurance_balance`, today's charges, last-payment amounts. | `GET /patients/{id}/balance` | Low |
| PATIENTS-10 | Note audit author + attachments | PatientNoteRead missing `created_by_name`/`updated_by(_name)`; no attachments. | `GET /patient-notes` | Low |

### 5b. Transactions (Entry, Ledger, Claims, Refunds, Statements)
| Gap ID | Title | Description / Workaround | Endpoint | Severity |
|--------|-------|--------------------------|----------|----------|
| DASH-1 | Office financial summary | No aggregate for outstanding/patient/insurance balances; only per-patient. | `GET /offices/{id}/financial-summary` | High |
| DASH-2 | Collections summary (today/month) | No aggregated collections endpoint. | `GET /offices/{id}/collections` | High |
| DASH-3 | Insurance receivables (A/R) | Only per-patient `insurance_balance`; no office A/R or aging-by-carrier. | `GET /offices/{id}/insurance-receivables` | High |
| DASH-4 | Refund/adjustment/write-off totals | No summary; refund concept missing entirely. | `GET /offices/{id}/adjustment-summary` | High |
| DASH-5 | Office-wide transaction feed | Ledger is per-patient only; no cross-patient feed. | `GET /offices/{id}/transactions` | High |
| LED-1 | Ledger sort + type/status filter | Ledger accepts only date/page/size; no `sort_by`/`transaction_type`/`status`. | `/patients/{id}/ledger` (extend) | High |
| INS-1(tx) | Check/EFT/EOB capture on ins payment | No `check_number`/`bank_number`/`eob_number`/`trace_number`; reconciliation impossible. | `LedgerInsuranceDetailCreate` | High |
| REF-1 | Process refund | No refund concept; only workaround is unvalidated negative payment. | `POST /patients/{id}/refunds` | High |
| REF-2 | Reverse/void payment or adjustment | Only passive `is_void` boolean; no reverse route / offsetting entry. | `POST /patient-payments/{id}/reverse`, `/patient-adjustments/{id}/reverse` | High |
| STMT-1 | Individual statement generation | No single-patient statement endpoint. | `POST /patients/{id}/statements` | High |
| SRCH-1 | Unified cross-patient transaction search | No merged feed; client merges 4 calls, can't paginate correctly. | `GET /transactions?search=&type=&status=` | High |
| CHG-1 | Charge-time estimate calculation | Estimates client-supplied; no server calc from coverage+fee schedule. | `POST /patient-procedures/estimate` | Medium |
| CHG-2 | Structured anatomy/surface/material rules | ProcedureCodeRead has only flat booleans; no rule objects. | extend `ProcedureCodeRead` | Medium |
| ADJ-1 | Per-procedure adjustment allocation | No allocations array; allocate is payment-scoped only. | `POST /patient-adjustments/{id}/allocate` | Medium |
| REF-3 | Refundable-credit lookup | PatientBalance missing unapplied-credit field. | `GET /patients/{id}/refundable-balance` | Medium |
| STMT-2 | Batch statement run | No monthly batch for outstanding balances. | `POST /offices/{id}/statements/batch` | Medium |
| STMT-3 | Statement delivery (print/email/PDF) | No PDF/email delivery. | `GET /patients/{id}/statements/{id}/pdf`, `POST .../email` | Medium |
| SRCH-3 | Search by txn number/amount/balance | No amount-range/txn-number filters. | collection endpoints (extend) | Medium |
| AUD-1 | Per-record change history | `audit-logs` has no `resource_id` filter. | `GET /audit-logs` (extend) | Medium |
| AUD-2 | Audit fields on ledger entries | LedgerEntry missing creator/modifier + timestamps. | `LedgerEntry` | Medium |
| AUD-3 | Claim status-change history | No status-history; hardcoded `claim_closed_by`. | `GET /insurance-claims/{id}/status-history` | Medium |
| SVC-1 | Send/submit claim action | Phantom `/claims/{id}/send`; no single send action. | `POST /insurance-claims/{id}/submit` | Medium |
| REF-4 | Refund authorization policy | No threshold/approval flow. | `GET /metadata/refund-policy` | Low |

### 5c. Account Ledger
| Gap ID | Title | Description / Workaround | Endpoint | Severity |
|--------|-------|--------------------------|----------|----------|
| AL-1 | Server-side running balance / single feed | LedgerEntry thin; grid assembled from 3 lists; running balance client-side. | `GET /patients/{id}/account-ledger` | High |
| AL-2 | Combined/server-paged feed | No single procedures+payments+adjustments feed; each list caps at 200 → truncation >200. | pagination on AL-1 | High |
| AL-3 | Ortho payment plan resource | No ortho-flagged plan; insurance-plan models lack financial-summary fields. | add `plan_type` discriminator | Medium |
| AL-4 | Ledger type filter ("Show All") | Filters only by date; no `transaction_type`. | ledger (extend) | Medium |
| AL-5 | Ledger server-side sort | No `sort_by`/`order`. | ledger (extend) | Medium |
| AL-6 | Columns with no backing data | No per-txn attachment/duration; "N" semantics unconfirmed. | confirm/add fields | Low |
| AL-7 | Office lookup beyond first 200 | `GET /offices?size=200` fetched once; offices beyond won't resolve. | office resolver / `office_short_id` on ledger | Low |
| AL-8 | Responsible party / insurance in context | Patient context missing resp-party + active-insurance summary for title bar. | `/patients/{id}/summary` | Low |

### 5d. Reports & Dashboard
| Gap ID | Title | Description / Workaround | Endpoint | Severity |
|--------|-------|--------------------------|----------|----------|
| DASH(rep)-1 | No aggregation endpoints | Only CRUD lists; KPIs/trends computed client-side. | `GET /dashboard/summary` | High |
| DASH(rep)-2 | Missing aggregation set | No dashboard/summary, trends, provider-productivity, practice AR, production summary, recall range, office payments. | multiple | High |
| DASH(rep)-3 | Missing metrics denominators | No provider working-hours/capacity, no leads/inquiries, no chair capacity. | `ProviderRead` (+hours), leads resource | High |
| DASH(rep)-4 | Missing resources | No `/tasks`, ins-verification filter, document-status, refund-requests, notifications, unified search, SMS/email send, check-in enums. | multiple | High |
| REPORTS-GAP-1 | No roll-up endpoints | KPIs/trends client-side with truncation warnings. | `GET /reports/summary` | High |
| REPORTS-GAP-2 | No practice-wide AR | Per-patient balance only; "Awaiting backend". | `GET /reports/accounts-receivable` | High |
| REPORTS-GAP-3 | No aging (30/60/90/120+) | No age buckets; Aging report blocked. | `GET /reports/aging` | High |
| REPORTS-GAP-4 | No export / email / scheduled reports | PDF/Excel disabled; only client CSV. | `POST /reports/{report}/export`, `/reports/schedules` | Medium |
| DASH(rep)-5 / REPORTS-GAP-5 | Status enum drift | Appointment/TreatmentPlan/Claim/elig statuses are free-text. | `/definitions` | Medium |
| REPORTS-GAP-6 | `office_id` list filter | Missing on `listPatientProcedures/Payments/InsuranceClaims`. | add `office_id` | Medium |

---

## 6. Clinical modules

### 6a. Restorative Charting
| Gap ID | Title | Description / Workaround | Resource | Severity |
|--------|-------|--------------------------|----------|----------|
| REST-1 | Enrich `chart_conditions` | Missing `group_id`, `grade`, `updated_by/at`; FE encodes in `region`. | `chart_conditions` | High |
| REST-2 | `chart_status_templates` catalog (NEW) | No bridge/denture preset resource; FE hardcodes. | NEW | High |
| REST-3 | `chart_settings` per-patient (NEW) | View settings (numbering, visibility) in localStorage. | NEW | High |
| REST-4 | `chart_tooth_notes` (NEW) | No per-tooth note resource; FE stores as `condition_code='NOTE'` row. | NEW | High |
| REST-5 | Seed colors/materials | Materials null color/pattern; crown materials missing. | seeding | Medium |
| REST-7 | First-class per-item metadata | `tooth_status/root_scope/rct_fill/watch_*` encoded in `region`. | `chart_conditions` | Medium |
| REST-8 | ADA alternate-benefit ("A") codes | Missing `amb_code`/`is_downgrade`/`alternate_of`; can't auto-offer A-code. | `procedure_codes` | Medium |
| REST-9 | Root-level conditions | Missing `segment`/`root_segment`; FE encodes in `region`. | `chart_conditions` | Medium |
| REST-10 | Freehand drawing persistence | Strokes packed into `progress_notes.notes_html` + PNG upload. | `progress_notes`/`patient_documents` | Low |

### 6b. Perio Charting
| Gap ID | Title | Description / Workaround | Resource | Severity |
|--------|-------|--------------------------|----------|----------|
| PERIO-BE-1 | UNIQUE(exam_id, tooth_no) | No constraint; duplicates allowed; FE guards in-memory. | `perio_exam_details` | Blocker |
| PERIO-BE-2 | Mobility accepts decimals | Columns INTEGER; reject 0.5/1.5 half-grades; FE drops non-integers. | `perio_exam_details` | Blocker |
| PERIO-BE-3 | DELETE semantics inconsistent | Exam soft-deletes, detail hard-deletes; no filter to exclude voided; DOS shows deleted. | `perio_exams` | High |
| PERIO-BE-4 | CAL not stored | No `cal1..6`; derived client-side as PD+FGM; can't store independently. | `perio_exam_details` | High |
| PERIO-BE-5 | Detail audit columns | No created/updated at+by. | `perio_exam_details` | Medium |
| PERIO-BE-6 | Exam attribution thin | `created_by` id only; no updated_by/at. | `perio_exams` | Medium |
| PERIO-BE-7 | Server-side range validation | `PATCH {pd1:999}` succeeds; out-of-range storable. | `perio_exam_details` PATCH | Medium |
| PERIO-BE-8 | Bulk upsert | 32-tooth save = ~32 calls, non-atomic. | `perio_exam_details` | Medium |
| PERIO-BE-9 | Date-range filters | Only `patient_id` filter; compare/history fetch-all client-side. | `perio_exams` GET | Low |
| PERIO-BE-10 | Server comparison/summary/print | Compare + PDF client-side. | — | Low |
| PERIO-BE-11 | Per-user chart settings | Requires `user_id` filter, no default seed; FE uses localStorage. | `perio_chart_settings` | Low |
| PERIO-BE-12 | `auto_advance` schema undefined | Free-form object; FE can't honor probing order. | `perio_chart_templates` | Low |
| PERIO-BE-13 | Clarify `PerioChartActivity` | Denormalized legacy log, undocumented, unused by new UI. | `perio_chart_activity` | Low |

### 6c. Progress Notes
| Gap ID | Title | Description / Workaround | Resource | Severity |
|--------|-------|--------------------------|----------|----------|
| PN-1 | Per-user signature store | `patient-signatures` keyed by patient only; "Load My Signature" can't work. | `patient-signatures`/`users` | Blocker |
| PN-2 | `/sign` ignores "Change User" | Sign endpoint takes no body; always signs as auth user; no over-the-shoulder. | `/progress-notes/{id}/sign` | Blocker |
| PN-3 | Attachments not linkable to note | Docs link to patient only; orphaned; no per-note display/delete. | `patient-documents` | Blocker |
| PN-4 | No strike-off timestamp | `is_struck_off` bare boolean; same-day restore rule unenforceable. | `progress_notes` | Medium |
| PN-5 | `created_by`/`signed_by` no name | Ids render "User #N"; FE resolves via `/users`. | `progress_notes` | Medium |
| PN-6 | Macro `category` free text | Unvalidated; seeds store numeric codes; dropdown shows codes. | `note-macros` | Medium |
| PN-7 | Locking client-derived only | No server enforcement; API can still mutate signed/locked notes. | `progress_notes` PATCH | Medium |

### 6d. Treatment Plans
| Gap ID | Title | Description / Workaround | Resource | Severity |
|--------|-------|--------------------------|----------|----------|
| PLAN-13 | Item becomes undeletable | Soft-deleted insurance-detail + FK RESTRICT → parent delete returns 409 forever. | `treatment-plan-insurance-details` | Blocker |
| PLAN-1 | No `phase_id` on item | Phase encoded in `billing_order` stopgap; blocks phase-aware re-estimate. | `treatment_plan_item` | High |
| PLAN-2 | No editable `diagnosed_date` | "Diag Date" shown/collected but only `created_at` exists; also no start/end date. | `treatment_plan_item` | High |
| PLAN-3 | No insurance-estimate compute | Store exists, no compute endpoint; `insurance_estimate` stuck at 0. | `treatment-plan-insurance-details` | High |
| PLAN-12 | Items no `patient_id` filter | Param accepted but ignored → cross-patient rows; FE does N+1 per plan. | `treatment-plan-items` GET | High |
| PLAN-5 | No performing `provider_id` | Reuses `diagnosed_by`; conflates diagnoser vs performer. | `treatment_plan_item` | Medium |
| PLAN-6 | No server export | Print built client-side (jsPDF). | — | Medium |
| PLAN-8 | `patient-documents` list empty | Uploads 201 but list returns 0 (uploaded docs have `office_id:null`; list office-scoped). | `patient-documents` GET | Medium |
| PLAN-9 | No pre-auth workflow | Fields exist, no submission/tracking flow/UI. | `treatment-plan-insurance-details` | Low |
| PLAN-4 | Item missing office/PS/S/C/dates | Legacy grid fields omitted. | `treatment_plan_item` | Low |
| PLAN-14 | Item DELETE is hard | Inconsistent w/ `patient-procedures` soft-delete; irreversible, no audit. | `treatment_plan_item` | Low |
| PLAN-15 | No procedure→appointment linkage | No flow to create appointment from planned procedures. | — | Low |
| PLAN-10 | No plan discount | No discount field/endpoint. | `treatment_plan_item` | Low |
| PLAN-11 | No treatment-counselor resource | Missing case-presentation resource. | — | Low |
| PLAN-7 | No per-patient consent capture | Templates/consents exist; no per-patient capture/e-sign/storage. | `patient-consents` (NEW) | Low |

### 6e. Prescriptions (per-patient) & 6f. Lab Tracking & 6g. Imaging & 6h. Patient Insurance
| Gap ID | Title | Description / Workaround | Resource | Severity |
|--------|-------|--------------------------|----------|----------|
| **Prescriptions** RX-P1 | No separate "Internal Note" | Single `notes` prints; Internal Note input gated/disabled. | `prescriptions` | Medium |
| RX-P2 | No DoseSpot patient id | PatientRead has none; FE shows `dosespot_rx_id`/0. | `patients` | Low |
| RX-P3 | ePrescribe not integrated | No DoseSpot launch/handoff; button only notifies. | — | Low |
| RX-P4 | No print/export endpoint | Client-side jsPDF only. | — | Low |
| RX-P5 | Med/Source status columns | No backend equivalent; columns omitted. | `prescriptions` | Low |
| **Lab** LAB-1 | No lab-vendor field | Missing `lab_vendor(_id)` + `lab_short_notice`; FE renders but "not saved". | `appointments` | High |
| LAB-2 | No lab filters on list | No `has_lab`/lab-date filters; FE filters client-side after fetch-all. | `appointments` list | Medium |
| LAB-3 | Denormalized names missing | Only ids; scheduler feed has names but drops lab fields. | `appointments` | Low |
| LAB-4 | No lab report/export | Lab & Lab-Cost reports client-side. | — | Low |
| LAB-5 | Office-wide lab tracking | Patient-scoped only; cross-patient dashboard blocked on LAB-2. | — | Low |
| **Imaging** IMG-1 | Binary↔metadata unrelated | `patient-documents` & `image-details` unlinked; doc id stuffed into `tile_id` string; no FK. | `image-details`/`patient-documents` | High |
| IMG-2 | `image-details` not patient-scoped | Filters only by `image_group_id`; must resolve group first. | `image-details` list | High |
| IMG-3 | No imaging-native binary endpoint | Images ride generic `patient-documents`; two writes/tables/manual correlation. | propose `/patients/{id}/images` | High |
| IMG-4 | No thumbnails | Full-res originals loaded into thumbnails; not scalable. | `patient-documents`/`image-details` | Medium |
| IMG-5 | No signed/expiring URLs for PHI | Stable `file_url`; long-lived/guessable → PHI risk. | `patient-documents` | Medium |
| IMG-6 | No image view/audit trail | Views not captured; HIPAA "who viewed which image" missing. | — | Medium |
| IMG-7 | No device-scan persistence | Device bytes funneled through generic docs; no modality/exposure/DICOM. | propose device endpoint | Medium |
| **Pt Insurance** INS-PT-1 | No marital status | `insurance_subscribers` missing; FE renders, not persisted. | `insurance_subscribers` | Low |
| INS-PT-2 | No subscriber phone | Missing column; not persisted. | `insurance_subscribers` | Low |
| INS-PT-3 | No secondary subscriber relationship | No column; not persisted. | `insurance_subscribers` | Low |
| INS-PT-4 | Subscriber address line 2 | Single `sub_address`; FE joins/splits on newline. | `insurance_subscribers` | Low |
| INS-PT-5 | No real-time eligibility | `elig_verified_on` set client-side; no re-check endpoint. | — | Low |
| INS-PT-6 | "Plan Date" column | Only subscriber-level date stored; Plan Date read-only/blank. | `insurance_subscribers` | Low |

---

## 7. Setup / Admin modules

### 7a. Security — Users & Groups
| Gap ID | Title | Description / Workaround | Resource | Severity |
|--------|-------|--------------------------|----------|----------|
| Users #1 | Compound user create/update | Basic-fields only; multi-tab form (offices/groups/IP/prefs/time-clock) can't persist atomically. | `POST /users/complete`, `PUT /users/{id}/complete` | High |
| Users #2 | Setup-metadata endpoint | No source for roles/access-levels/overtime/prefs schema; hardcoded. | `GET /users/setup-metadata` | High |
| Users #3 | Time-clock config | No config field/endpoint (`/time-clock-entries` is punches, not config). | `/users/{id}/time-clock-config` | High |
| Users #4 | Login-restriction / access-level fields | Allowed days/hours + patient access level absent. | user contract (extend) | High |
| Users #7 | Self-service change-password | `PATCH /users/{id}` doesn't verify old password. | `POST /users/me/change-password` | High |
| Users #5 | Roles/permissions catalog | `role` free-form; no catalog endpoint. | `GET /roles`, `/permissions` | Medium |
| Users #6 | List filter by office/role | No `office_id`/`role` params; grid joins client-side. | `list_users` (extend) | Medium |
| Users #8 | Update-audit fields | No `updated_at`/`updated_by` on UserRead. | `UserRead` | Medium |
| Users (fields) | Missing user fields | `short_id`, `report_access_provider_id`, `custom_1/2`, `signature_*`, `image_url` absent. | user model (+ image endpoint) | Med/High |
| Groups Gap 1 | Rights/permissions catalog | No endpoint for ~517 rights picker; hardcoded in FE. | `GET /permissions` | High |
| Groups Gap 2 | Group→rights read/write | No field/endpoint to read or assign rights. | `GET/PUT /user-groups/{id}/rights` | High |
| Groups Gap 4 | RBAC enforcement | Even once stored, rights not enforced. | enforcement layer | High |
| Groups Gap 3 | Copy user group server-side | FE emulates create+copy. | `POST /user-groups/{id}/copy` | Medium |

### 7b. Office Assignment (Setup Phase 3)
| Gap ID | Title | Description / Workaround | Resource | Severity |
|--------|-------|--------------------------|----------|----------|
| OA-24 | Office↔procedure-code assignment | No office-scoped GET/PUT or link table. | `/offices/{id}/procedure-codes` | High |
| OA-25 | Explosion codes resource | Entire resource missing. | `/explosion-codes` + office link | High |
| OA-26 | Production types resource | Entire resource + assignment missing. | `/production-types` + office link | High |
| OA-32 | Ortho Misc Setup resource | Undefined at backend. | define + office link | High |
| OA-27 | Users bulk/copy + `created_by` | No bulk set/copy; UserRead lacks `created_by`; no office/active filter. | `PUT /offices/{id}/users`, copy-from, filters | Medium |
| OA-28 | Provider single-office model | Single `office_id` FK not M:N; ProviderRead lacks name split + `created_by`. | `provider_offices` link / add fields | Medium |
| OA-29 | Note-macro office assignment | Tenant-wide, no office filter/link. | `/offices/{id}/note-macros` | Medium |
| OA-30 | RX office assignment | Tenant-wide, no office filter/link. | `/offices/{id}/prescription-library` | Medium |
| OA-31 | Letter-template office assignment | Tenant-wide, no office filter/link. | `/offices/{id}/letter-templates` | Medium |
| OA-33 | `?office_id=` not honored server-side | `/user-offices`, `/providers` ignore filter; FE safety-net. | those endpoints | Medium |

### 7c. Insurance & Fee Schedules
| Gap ID | Title | Description / Workaround | Resource | Severity |
|--------|-------|--------------------------|----------|----------|
| INS-1 | No `carrier_type` filter | Dental/Medical split pages whole list (~7 requests). | `ListInsuranceCarriersParams` | High |
| INS-3 | Carrier capability flags not modeled | No eligibility/claim-status/DXC-attachment/insurance-type. | `InsuranceCarrierRead` | High |
| INS-8 | Unstable pagination drops/dupes | Sort by non-unique `name`: 1340 total → 1338 unique (2 skipped, 1 dup). | ordering (`ORDER BY name, id`) — all paginated endpoints | High |
| INS-2 | `carrier_type` untyped string | `"True"`/`"False"` string, not bool/enum. | promote to `is_dental`/enum | Medium |
| INS-4 | Fax/email not modeled | No dedicated `fax`/`email`. | carrier contract | Medium |
| INS-5 | Employer model minimal | Lacks `salesrep`, contact, modified audit. | `EmployerRead` | Medium |
| INS-6 | Employer audit metadata | Only `created_at`; no modified_on/by. | employers | Medium |
| INS-9 | Plans search can't match carrier/employer name | Must use separate picker filters. | `GET /insurance-plans` | Medium |
| INS-10 | Opaque coverage_type/category codes | Single-char/bare codes, no enum/lookup. | expose enum/reference | Medium |
| INS-11 | No `elig_status` filter | Live status uniformly "unknown"; Pending Verifications KPI unmeasurable. | subscribers list | Medium |
| FEE-1 | Fee-schedule DELETE soft-deletes | Flips `is_active`; entries/assignments hard-delete (inconsistent). | confirm convention | Medium |
| FEE-2 | No `amb_code` | Legacy AMB Code column; missing on procedure codes/fee entries. | add field | Medium |
| FEE-3 | Assignment lacks office-group | Legacy Office Group column; only `office_id`. | add `office_group_id` | Medium |
| FEE-4 | No schedule-level effective date/versioning | `effective_date` on entries only. | expose on schedule / cloning endpoint | Medium |

### 7d. Codes, Charting Setup, Pick List, Macros, Medical, Toolbar, Referrals, Provider
| Gap ID | Title | Description / Workaround | Resource | Severity |
|--------|-------|--------------------------|----------|----------|
| AUX-1 | Modifier codes resource | Missing; legacy 2-col grid. | seed `MODIFIER` group / resource | High |
| AUX-2 | Type-of-Service codes | Missing; legacy 2-col grid. | seed `TYPEOFSERVICE` / resource | High |
| AUX-3 | Place-of-Service codes | Missing; needs Tax ID field `definitions` can't hold. | dedicated `place-of-service-codes` | High |
| AUX-4 | ICD codes resource | Missing; needs paginated+searchable ICD-9/10/SNOMED set. | dedicated `icd-codes` | High |
| PROC-6 | Fee-schedules list latency | `?size=200` multi-second; tab needs only `id,name`. | denormalize / lightweight projection | Low |
| CHART-1a | Perio template `*_by` not expanded | Shows `Modified By: 385`. | embed `*_by_name` | Medium |
| CHART-1b | Perio template no default seed | New tenants empty. | seed default | Medium |
| CHART-2c | Restorative colors no default seed | Empty grid on new tenants. | seed 10 defaults | Medium |
| CHART-3d | Materials no default seed | Empty grid. | seed defaults | Medium |
| CHART-3a | Materials missing `updated_at` | "Modified On" unfillable. | `TimestampMixin` | Low |
| CHART-3b | Materials missing `*_by` | "Modified By" unfillable. | add `modified_by` | Low |
| CHART-2a | Colors no `modified_by` | Shows creator not editor. | add `modified_by` | Low |
| PICK-3 | No custom/system discriminator | Can't split built-in vs user pick lists. | add flag/enum | Medium |
| PICK-4 | Item value single `answer_code` | No label/value_type split. | (parity-optional) | Low |
| PICK-5 | No uniqueness validation | Dup description/answer_code not enforced. | confirm | Low |
| _PICK-1/2_ | _Cascade delete + bulk replace_ | **RESOLVED** — backend added `.../cascade` and `PUT .../options`. | — | ✅ |
| NM-2 | Macro `category` numeric codes | Stored as `"179"` not labels; no group to resolve. | `NOTE_MACRO_CATEGORY` group / backfill | High |
| NM-1 | No `category` filter | FE loads all + filters client-side. | add param (+`/categories`) | Medium |
| NM-3 | `created_by` id only | No joined name. | expose `created_by_name` | Medium |
| NM-4 | No `updated_at`/`updated_by` | Can't show "last modified". | add fields | Medium |
| NM-5 | No name uniqueness | Duplicates allowed. | confirm | Low |
| MED-1 | No feature-scoped catalog home | `definition-groups` no `group_type`/filter; FE filters by convention. | bless group_type + filter | High |
| MED-3 | Questions no input-type column | Type code stored in `key1` convention. | add `input_type` | High |
| MED-4 | No question↔answer linkage | `medical-history-details` keyed by free-text code, no FK. | add `question_id` FK | High |
| MED-2 | No seed data | ~50+ legacy alerts/questions not migrated. | seed | Medium |
| MED-5 | No draft/publish + ordering | Immediate CRUD; no `sort_order`. | add flag + order | Medium |
| TB-1 | No toolbar resource | Repurposes `definition-groups` `group_type=TOOLBAR`. | resource / bless + filter | High |
| TB-4 | No group order/role-binding/default | Can't order toolbars or bind to role. | add fields | High |
| TB-2 | No function registry | 26 functions+icons hardcoded FE. | catalog endpoint | Medium |
| TB-5 | No seed + no transactional copy/save | No default toolbars; copy/save = N calls (partial-failure). | seed + bulk write | Medium |
| TB-3 | No `updated_at`/`updated_by` on groups | Can't show modified stamps. | add columns | Low |
| RX-1 (setup) | No "Modified By" | `updated_at` only, no `updated_by`/`created_by`. | add `updated_by` | Medium |
| RX-2 | Sig 240-cap FE-only | API doesn't advertise/enforce max length. | confirm column limit | Low |
| RX-4 | No `drug_name` uniqueness | Duplicate seeds ("Amoxicillin 500mg"). | confirm | Low |
| REF (Referrals) | Missing referral fields | No `e_referral_id`, `practice_name`, `contact_name`, `cost`; no demographics feed. | extend `ReferralRead` / demographics | Medium |
| REF | `referral_type` code domain | `"0"`=Referred By / `"1"`=Referred To, undocumented. | enum / definitions | Low |
| Provider Gap A | Provider `id` client-supplied | `ProviderCreate.id` required string; no server convention. | server-assign or publish convention | Low |

---

## 8. Suggested prioritization for backend

1. **Unblock broken features (Blocker/Critical):** Dashboard latency (Critical), Auth reset/activation (5), Perio UNIQUE + decimal mobility (PERIO-BE-1/2), Progress-Notes signature/sign/attachments (PN-1/2/3), Treatment-plan-item undeletable (PLAN-13).
2. **Kill the N+1 & truncation tax (theme T6/T1):** denormalize names on scheduler/lab/ledger feeds; add the office-level financial/collections/AR aggregates; server-paged combined ledger feed.
3. **Persistence of collected-but-dropped data:** cancellation metadata (SCHED-APPT-2), lab vendor (LAB-1), diagnosed_date (PLAN-2), insurance check/EFT/EOB (INS-1 tx), patient-context last-patient (PDP-1..4).
4. **Enumerations & audit standardization (T2/T3/T5):** `*_by_name`, `updated_at/by`, and `/definitions` groups for all status/code fields — one pass clears ~30 Medium rows.
5. **New resources:** ICD/Modifier/TOS/POS codes (AUX-1..4), refunds/statements (REF/STMT), office-assignment link tables (OA), tasks/notifications (Dashboard-4).

_Full per-gap detail (repro steps, exact payloads) lives in each module's `docs/<module>/*_backend_devreport.md`._
