# Transactions Module — Screen-by-Screen Audit & Remediation Plan

> Status: **Audit complete (2026-06-06).** This document is the workflow/UX reference and the
> source of truth for the Transactions modernization phase. Backend gaps are tracked separately in
> [`transactions_backend_devreport.md`](./transactions_backend_devreport.md).
>
> Method: 11 parallel auditors mapped every financial workflow against `openapi.json` + the generated
> Orval client (`src/api/generated/**`); every suspected backend gap was then adversarially
> re-verified against `openapi.json` before being recorded. **10 suspected gaps were refuted**
> (the capability already exists) — see [§7 Refuted gaps](#7-refuted-gaps-do-not-request-these).

---

## 1. Executive summary

The Transactions module is in **two very different states**:

| Surface | State | One-line verdict |
|---|---|---|
| Global [`Transactions.tsx`](../../src/components/pages/Transactions.tsx) | ❌ **100% mock** | Hardcoded 7-row array; KPI cards computed from fake data; Export/New Transaction/View are dead. |
| [`PatientLedger.tsx`](../../src/components/pages/PatientLedger.tsx) — Balances tab | ✅ **Wired** | Correctly wraps generated `getPatientBalance`; aging + recent activity real. |
| [`PatientLedger.tsx`](../../src/components/pages/PatientLedger.tsx) — Ledger grid | ⚠️ **Wired to a fabricated contract** | Reads `getPatientLedger` via raw axios; the hand-written `LedgerEntry`/`LedgerResponse` types do **not** match the real backend schema → grid renders blank against real data. |
| [`PaymentsAdjustments.tsx`](../../src/components/patient/PaymentsAdjustments.tsx) | ⚠️ **Partial** | Flat patient payment + adjustment post via the generated client; per-procedure allocation grid is dead, provider/apply_to/bank# silently dropped. |
| [`AddProcedure.tsx`](../../src/components/patient/AddProcedure.tsx) (charge entry) | ❌ **Posts to phantom paths** | Create/update/delete + procedure-codes hit `/patients/{id}/procedures` & `/metadata/*` which **do not exist** → 404 against the real backend. |
| Insurance payment (`ClaimDetail.tsx` button) | ❌ **Stub** | `alert("…not available yet")`; the backing endpoint (`createLedgerInsuranceDetail`) exists but is unwired. |
| Refunds | ❌ **Absent everywhere** | No UI, no endpoint — `grep refund` returns nothing in `src/` or `openapi.json`. |
| Statements (patient generation) | ❌ **Dead button + no endpoint** | "BALANCE STATEMENT" has no `onClick`; no patient statement-generation endpoint exists. Office statement *settings* (Setup) are fully wired. |

**The root-cause defect** is [`src/services/ledgerApi.ts`](../../src/services/ledgerApi.ts): a ~800-line raw-axios
service with ~30 hand-written interfaces and ~26 functions. **~17 of its paths are phantom** (not in
`openapi.json`), and its `LedgerEntry`/`LedgerResponse`/`ProcedureCode`/`Claim*` types have severely
drifted from the generated models. It violates the project convention ("per-tab services must wrap the
generated Orval client, no raw axios") and is the reason most workflows are broken or fragile. **Most of
this phase is wiring the existing UI to endpoints that already exist** — not net-new features.

---

## 2. The `ledgerApi.ts` phantom-endpoint map

Migration target for each function (the generated equivalent **already exists**):

| `ledgerApi.ts` function | Calls (raw axios) | Exists? | Replace with (generated) |
|---|---|---|---|
| `getPatientLedger` | `GET /patients/{id}/ledger` | ✅ path real, **wrong params/shape** | `billing.getPatientLedger` + `GetPatientLedgerParams` (`date_from/date_to/page/size`) |
| `getPatientBalances` | `GET /patients/{id}/balance` | ✅ (already wraps generated) | keep — move out of the raw-axios file |
| `addProcedure`/`getProcedure`/`updateProcedure`/`deleteProcedure` | `…/patients/{id}/procedures*` | ❌ phantom | `clinical.createPatientProcedure`/`getPatientProcedure`/`updatePatientProcedure`/`deletePatientProcedure` (`/patient-procedures`) |
| `createClaim`/`getClaim`/`updateClaim`/`sendClaim`/`getPatientClaims` | `…/patients/{id}/claims*` | ❌ phantom | `billing.createInsuranceClaim`/`getClaimDetail`/`updateInsuranceClaim`/`listInsuranceClaims` (`/insurance-claims`) |
| `addPayment`/`getPayment` | `…/patients/{id}/payments*` | ❌ phantom (dead code) | `billing.createPatientPayment`/`getPatientPayment` (`/patient-payments`) |
| `addAdjustment`/`getAdjustment` | `…/patients/{id}/adjustments*` | ❌ phantom (dead code) | `billing.createPatientAdjustment`/`getPatientAdjustment` (`/patient-adjustments`) |
| `getProcedureCodes` | `GET /metadata/procedure-codes` | ❌ phantom | `procedures.listProcedureCodes` (`/procedure-codes`) — note shape is `PaginatedResponseProcedureCodeRead`, flat `requires_*` booleans |
| `getPaymentCodes`/`getAdjustmentCodes`/`getClaimStatuses`/`getTransactionTypes` | `GET /metadata/*` | ❌ phantom | `metadata.listDefinitions({ group_code, is_active })` (`/definitions`) — see §7 |
| `getOfficeProviders` | `GET /offices/{id}/providers` | ✅ path real | `office-assignment.listOfficeProviders` (returns bare `AssignedProviderRead[]`, not `{providers}`) |

> ⚠️ **There are no `/api/v1/metadata/*` endpoints at all.** Code lists live under `/api/v1/definitions`
> filtered by `group_code` (the OpenDental-style definition table), already used elsewhere via
> `useDefinitions` / `useListDefinitions`.

---

## 3. Per-screen findings

### 3.1 Transactions Dashboard (`Transactions.tsx`) — ❌ rebuild
- **Critical:** entire component is a hardcoded `transactions[]` array (lines 15–79); all 3 KPI cards
  and the table render from it. No `useEffect`, no service import.
- **High:** routed at `/patient/:patientId/transaction` but ignores the outlet `patient` and shows
  cross-patient fabricated rows — misleading data isolation.
- **High:** Export / New Transaction / per-row View buttons have no `onClick`.
- No office-wide aggregation or transaction-feed endpoint exists (confirmed gaps DASH-1…5). Decision
  required: make this a **per-patient** view (backed by `getPatientLedger` + `getPatientBalance`) or a
  **true office dashboard** (needs new backend endpoints first).

### 3.2 Patient Ledger grid (`PatientLedger.tsx`) — ⚠️ rebind to real contract
- **Critical:** `ledgerApi.LedgerEntry` (~40 fields: `posted_date`, `patient_name`, `apply_to`,
  `posted_amount`, `transaction_type`, `procedure_id`, `claim_id`…) vs the **real** thin `LedgerEntry`
  (`entry_date`, `entry_type`, `source_id`, `description`, `charge`, `credit`, `running_balance`,
  `procedure_code`, `tooth`, `payment_type`, `status`). Against real data the grid is mostly blank.
- **Critical:** envelope mismatch — UI reads `response.ledger_entries` + `response.pagination`; real
  shape is `{patient_id, entries[], opening_balance, closing_balance, total, as_of}` → `.map` on
  `undefined` throws.
- **High:** sends unsupported params (`limit/offset/transaction_type/status/sort_by/sort_order`); backend
  accepts only `date_from/date_to/page/size`. Server paging/sorting are non-functional; client re-sorts a
  single page (misleading once data exceeds one page).
- The rich per-row columns (provider, est pat/ins, apply_to, claim_id…) are **available by composing
  `GET /patient-procedures`** (see §7, ledger-richness refuted) rather than from the slim ledger feed.
- **Balances tab is the reference implementation** — correctly wraps generated `getPatientBalance`.

### 3.3 Charge / Procedure entry (`AddProcedure.tsx`) — ❌ repoint + reshape
- **Critical:** create/update/delete POST to phantom `/patients/{id}/procedures`; procedure codes from
  phantom `/metadata/procedure-codes`. Both 404. Real: `/patient-procedures` (POST/GET/PATCH/DELETE) and
  `/procedure-codes`.
- **High:** body diverges from `PatientProcedureCreate` — missing client-supplied `id`, `office_id` as
  string (needs number), `patient_id` in URL not body, `est_patient`/`est_insurance` vs
  `patient_estimate`/`insurance_estimate`, `materials: string[]` vs `material_id: number`.
- **High:** no fee-schedule application (fee = code `default_fee`); per-procedure estimate not computed
  (gap CHG-1). Anatomy/surface/material rules are fabricated client-side (gap CHG-2).

### 3.4 Patient Payments (`PaymentsAdjustments.tsx`) — ⚠️ complete allocation
- Flat payment + adjustment **are** persisted via generated `createPatientPayment` /
  `createPatientAdjustment` (snake_case bodies). Good.
- **High:** the "Procedures To Post" allocation grid is dead — `procedures` state hardcoded `[]`,
  per-row `newAmount` never submitted. The backing endpoint **exists**:
  `POST /patient-payments/{payment_id}/allocate` (guards over-allocation) — never called.
- **High:** `provider_id` collected but never sent; `apply_to` and `bank_number` silently dropped
  (`PatientPaymentCreate` has no bank field).
- **High (parity):** payment method / adjustment reason send `code.description` (label) instead of
  `code.key1` (value) → backend stores display text. Mirrors a real bug.
- **Medium:** no overpayment guard client-side; no reverse/void UI (`updatePatientPayment(is_void)` exists).

### 3.5 Insurance Payments & Reconciliation — ❌ build entry form
- **High:** the only entry point — `ClaimDetail.tsx` "INSURANCE PAYMENT" button — is `alert(…not
  available yet)`. The backing `createLedgerInsuranceDetail` (`POST /ledger-insurance-details`, with
  `prim/sec/ter ins_paid` + `ins_adjust` + estimates + `claim_id`/`procedure_id`) **exists and is
  entirely unwired**, as are the `patient-ins`/`patient-sec-ins` payment-plan resources.
- Batch allocation of one carrier payment across a claim's procedures **exists** via `allocatePayment`
  + `recalculateClaim` (see §7). Genuine gap: check/EFT/**EOB** number capture (gap INS-1).
- `ClaimDetail` already renders read-only reconciliation columns from `getClaimDetail` coverage rows.

### 3.6 Adjustments & Write-Offs — ⚠️ wire codes + classify
- Adjustments post via generated `createPatientAdjustment`. Reasons from `useDefinitions('adjustment')`.
- **High:** sends label not `key1` (same value bug as payments). **Medium:** `apply_to` captured but
  unsent (no field on `PatientAdjustmentCreate`); no edit/void/list UI though endpoints exist.
- **Write-offs:** no dedicated concept, but contractual/insurance write-offs are representable via
  `ledger-insurance-details.prim_ins_adjust`/`sec_ins_adjust` + `recalculateClaim` (see §7). Genuinely
  missing: an enforced `write_off_type` classification and per-procedure **adjustment** allocation (gap ADJ-1).

### 3.7 Refunds — ❌ blocked on backend
- **Critical:** no refund capability anywhere (UI or API). Only adjacent primitives are passive
  `is_void` flags and unconstrained negative amounts. Requires new backend endpoints (gaps REF-1…4)
  **before** any UI work. Do **not** implement as ad-hoc negative payments.

### 3.8 Statements — ⚠️ settings done, generation absent
- Office statement **settings** (`officeStatementApi.ts` + `StatementTab.tsx`) are a clean reference —
  wrap the generated client, bind snake_case. (Setup, not Transactions.)
- **High:** patient "BALANCE STATEMENT" button has no `onClick`; no patient statement
  generation/delivery endpoint exists (gaps STMT-1…3). Disable/hide until backend lands.

### 3.9 Transaction search & filtering — ⚠️ backend-drive
- Global page filters mock data client-side. Ledger date filter is real (`date_from/date_to`); status &
  transaction_type filters and multi-field sort have **no backend support** on the ledger endpoint
  (gap LED-1 / SRCH-2). No unified cross-patient feed (gap SRCH-1); no amount/txn-number search (SRCH-3).
  Cross-patient per-type lists (`patient-payments`, `patient-procedures`, `patient-adjustments`,
  `insurance-claims`) all support `search/sort/order/page/size` and could compose a global view.

### 3.10 Financial audit & history — ⚠️ thin
- Only audit surfacing is the ledger "CREATED BY" column — and the real `LedgerEntry` schema carries
  **no `created_by`/`created_at`**, so that column is unbacked (gap AUD-2). `listAuditLogs` exists but is
  unused and **cannot filter by `resource_id`**, so per-record change history is unreachable (gap AUD-1).
  Claim status-change history is faked from a single `submitted_date` (gap AUD-3).

---

## 4. Cross-cutting defects (apply broadly)
1. **Raw axios instead of generated client** — `ledgerApi.ts` (§2).
2. **Type drift / fabricated contracts** — delete hand-written `LedgerEntry`/`Claim*`/`Procedure*`/
   `Payment*`/`Adjustment*` interfaces; import generated models so they cannot drift again.
3. **snake_case parity violations** — `patient.officeId` (regex-stripped) in `PatientLedger`/`AddProcedure`
   must be `office_id`; camelCase view-models (`LedgerTransaction`, `OutstandingProcedure`) shadow API fields.
4. **Pervasive `any`** — `useOutletContext<{patient: any}>`, `catch (err: any)`, `onSave(p: any)`. Type the
   outlet patient to the generated `PatientRead` so field drift is compile-checked.
5. **Code value vs label** — always send `key1`, never `description`, for definition-backed selects.

---

## 5. Prioritized remediation plan

**Phase A — Service-layer foundation (unblocks everything; no backend dependency)**
1. Replace `ledgerApi.getPatientLedger` with generated `getPatientLedger`; rebind `PatientLedger` grid to
   the real `LedgerResponse`/`LedgerEntry`; switch to `page/size`; delete hand-written ledger types.
2. Repoint charge entry (`AddProcedure`) to `/patient-procedures` + `/procedure-codes`; fix the request body.
3. Delete the dead/phantom `ledgerApi` functions (payments/adjustments/claims/metadata); keep only a thin
   generated-client-wrapping `getPatientBalances` adapter.
4. Wire all code-lists (payment method, adjustment reason, claim status, transaction type) to
   `listDefinitions({ group_code })`; fix the **label-vs-`key1`** bug.

**Phase B — Complete the wired-but-incomplete workflows (no backend dependency)**
5. Payments: send `provider_id`; wire the "Procedures To Post" grid to `allocatePayment`; add overpayment
   guard + reverse/void.
6. Adjustments: fix reason value; add edit/void/list; resolve `apply_to` (drop or map).
7. Insurance payment: build the entry form on `createLedgerInsuranceDetail` + `allocatePayment` +
   `recalculateClaim`; replace the `ClaimDetail` stub.
8. Remove dead UI (statement button, empty allocation tabs) or gate behind feature flags.

**Phase C — Backend-blocked (see devreport; build UI once endpoints land)**
9. Refunds (REF-1…4), patient statement generation/delivery (STMT-1…3), office financial-summary
   dashboard (DASH-1…5), unified transaction search (SRCH-1/3), per-record audit history (AUD-1…3),
   ledger server-side sort/filter + enriched feed (LED-1, charge-time estimate CHG-1).

**Suggested first PR:** Phase A items 1–3 (the `ledgerApi` migration) — highest leverage, fixes the
critical broken-ledger and 404-on-save defects, and is the prerequisite for everything else.

---

## 6. Validation checklist (to track through the phase)

| Workflow | Create | Read | Update | Void/Reverse | Allocate | Backend-driven |
|---|---|---|---|---|---|---|
| Charges | ⚠️ phantom path | ⚠️ | ⚠️ | n/a | n/a | after Phase A2 |
| Patient payments | ✅ flat | ❌ no history UI | ❌ | ❌ | ❌ (endpoint exists) | partial |
| Insurance payments | ❌ stub | ✅ read-only | ❌ | ❌ | endpoint exists | no |
| Adjustments | ✅ flat | ❌ | ❌ | ❌ | ❌ | partial |
| Write-offs | ⚠️ via ins-detail | ✅ | — | — | — | partial |
| Refunds | ❌ none | ❌ | ❌ | ❌ | — | **blocked** |
| Statements (patient) | ❌ none | — | — | — | — | **blocked** |
| Patient ledger | — | ⚠️ wrong contract | — | — | — | after Phase A1 |

---

## 7. Refuted gaps (do **not** request these)

The verification pass found these capabilities **already exist** — the only work is frontend wiring:

| Suspected "gap" | Reality |
|---|---|
| Metadata endpoints for payment/adjustment/claim-status/transaction-type codes | `GET /api/v1/definitions?group_code=…` (+ `/definition-groups`); fields are free-string, definition-backed. Generated `listDefinitions`. |
| Ledger feed lacks rich per-row fields (provider, est, apply_to, claim_id…) | Compose `GET /api/v1/patient-procedures` (`PatientProcedureRead` has all of these + `claim_id` gating create-claim). |
| Atomic allocation of one insurance payment across claim procedures | `POST /api/v1/patient-payments/{payment_id}/allocate` ("guards over-allocation") + `POST /insurance-claims/{claim_id}/recalculate`. |
| No write-off / contractual concept | `ledger-insurance-details.prim_ins_adjust`/`sec_ins_adjust` (per claim+procedure) + `recalculateClaim`. Only the enforced `write_off_type` enum is missing. |
| Adjustment reason / payment-method / claim-status / transaction-type code lists | All via `listDefinitions({ group_code, is_active })`. |
| Balance / running-balance change history | `GET /api/v1/patients/{patient_id}/ledger` returns per-entry `running_balance` + `opening/closing_balance` + `entry_date` with `date_from/date_to`. |

---

## 8. Documentation pointers
- Backend gaps (verified, in required format): [`transactions_backend_devreport.md`](./transactions_backend_devreport.md)
- Conventions: project [`CLAUDE.md`](../../CLAUDE.md) (snake_case parity, wrap generated client, `npm run api:sync`)
- Reference implementations to imitate: `officeStatementApi.ts` (service), `getPatientBalances` (adapter),
  `useDefinitions` (code lists).
