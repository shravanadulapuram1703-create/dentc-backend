# Transactions — Backend Response (gaps implemented)

> Response to [`transactions_backend_devreport.md`](./transactions_backend_devreport.md).
> Every verified gap now has a backend endpoint. Alembic revision **`c7d8e9f0a1b2`**
> (`add_transactions_module_gaps`, down_revision `b3c4d5e6f7a8`). Run
> `npm run api:sync` to regenerate the Orval client.

All ids serialise as stored; all money fields are `Decimal`. `patient_payments`,
`insurance_claims` and `patient_procedures` have no `tenant_id` — tenancy is enforced
through the owning patient, as elsewhere in billing.

## Dashboard (office-level) — DASH-1..5
| Gap | Endpoint |
|---|---|
| DASH-1 | `GET /api/v1/offices/{office_id}/financial-summary` → `{outstanding_balance, patient_balance, insurance_receivable, credit_balance, patient_count, as_of}` |
| DASH-2 | `GET /api/v1/offices/{office_id}/collections?period=today\|week\|month\|year\|custom` (+ `date_from/date_to`) |
| DASH-3 | `GET /api/v1/offices/{office_id}/insurance-receivables` → total + `by_carrier[]` |
| DASH-4 | `GET /api/v1/offices/{office_id}/adjustment-summary?period=…` → `{adjustment_total, write_off_total, refund_total, write_off_by_type}` |
| DASH-5 | `GET /api/v1/offices/{office_id}/transactions` (office-scoped unified feed) |

## Unified feed / search — SRCH-1/3
- `GET /api/v1/transactions?search=&type=&status=&office_id=&date_from=&date_to=&amount_min=&amount_max=&transaction_number=&page=&size=`
- `type` ∈ `all|charge|payment|adjustment|refund|claim`. Rows are denormalised
  (`patient_name`, `provider_name`, `code`, `description`, signed `amount`, `status`,
  `transaction_number`). Amounts compared by absolute value for the range filter.

## Ledger — LED-1 / AUD-2
- `GET /api/v1/patients/{id}/ledger` now accepts `transaction_type`, `status`, `sort_by`
  (`date|amount|code|provider|status`), `sort_order`. Running balance stays chronological;
  filters/sort are applied for display afterward.
- Each `LedgerEntry` now carries `provider_id/provider_name`, `created_by/created_by_name`,
  `created_at`, and (reserved) `modified_by/modified_at`.

## Insurance payment / claims — INS-1 / SVC-1 / AUD-3
- `POST /api/v1/ledger-insurance-details/payment` — body includes `check_number`,
  `bank_number`, `eob_number`, `eft_trace_number`, `payment_method`, `payment_date`, the
  prim/sec paid/adjust/estimate figures and `claim_id`. Rolls paid onto the claim +
  invalidates the cached balance.
- `POST /api/v1/insurance-claims/{claim_id}/submit` → `{batch_id, sent_date, send_method,
  status, submission_id}`; stamps `submitted_date`, creates a `claim_submissions` row,
  marks the claim's procedures billed.
- `GET /api/v1/insurance-claims/{claim_id}/status-history` — timeline composed from
  `audit_logs` (status/submit/recalculate POSTs) + the claim's own lifecycle dates.

## Audit — AUD-1
- `GET /api/v1/audit-logs?resource_type=insurance-claims&resource_id={id}` — the new
  `resource_id` filter returns one record's full change history.

## Refunds — REF-1..4
| Gap | Endpoint |
|---|---|
| REF-1 | `POST /api/v1/patients/{id}/refunds` `{refund_amount, refund_method, reason, reason_code, source_payment_id, …}` → `{refund, balance}`; `GET` lists them |
| REF-2 | `POST /api/v1/patient-payments/{id}/reverse` · `POST /api/v1/patient-adjustments/{id}/reverse` `{reason, refund_method?}` |
| REF-3 | `GET /api/v1/patients/{id}/refundable-balance` → `{credit_balance, unallocated_payments, refundable_amount}` |
| REF-4 | `GET /api/v1/metadata/refund-policy?office_id=` → thresholds + approver roles |

A refund is a first-class `patient_refunds` row (never a negative payment); it folds into
the balance (`balance += refund`). `balance_service` now nets `payments − refunds` and
exposes `total_refunded` + `credit_balance` on `PatientBalance`. Refunds above the policy
threshold require an approver role.

## Statements — STMT-1..3
- `POST /api/v1/patients/{id}/statements` → frozen `patient_statements` snapshot
  (opening/charges/payments/adjustments/closing + aging + office aging message).
- `GET …/statements`, `GET …/statements/{sid}`, `GET …/statements/{sid}/pdf` (reportlab).
- `POST …/statements/{sid}/deliver` `{method: email|print|download}` records the lifecycle
  (email records intent — no SMTP wired).
- `POST /api/v1/offices/{id}/statements/batch` `{min_balance, only_aged, …}` → one `batch_id`
  over every office patient with an outstanding (optionally aged) balance.

## Charge entry — CHG-1..9
- **CHG-1/7** `POST /api/v1/patients/{id}/estimate` `{procedure_code, fee?, provider_id?}`
  or `{lines:[…]}` → per-line `{insurance_estimate, patient_estimate, estimated_deductible,
  coverage_pct, fee_source}` + totals. Derived from the patient's primary coverage rules +
  fee schedule (fee: override → fee-schedule entry → code default). No coverage → all-patient.
- **CHG-2** `procedure_codes.anatomy_rules/surface_rules/material_rules` (JSON) on the read.
- **CHG-4** `explosion-codes` + `explosion-code-items` CRUD + `GET /explosion-codes/{code}/expand`.
- **CHG-5** `patient_payments.bank_number`. **CHG-6** `patient_procedures.hygienist_id`.
- **CHG-8** `GET /api/v1/patients/{id}/insurance-summary` (carrier names by rank).
- **CHG-9** `GET /api/v1/patients/{id}/todays-appointment` (id + status → drives the
  Scheduler `PATCH /appointments/{id}/status` check-out already in place).
- **CHG-3** ("All Medical" CPT codes) remains a data-seeding task — the `/procedure-codes`
  category filter already supports it once medical codes are loaded.

## Write-offs — ADJ-1
- `patient_adjustments.write_off_type` (`contractual|provider|insurance|courtesy`) classifies
  a write-off; DASH-4 splits by it. Per-procedure adjustment allocation remains via the
  single `procedure_id` on `PatientAdjustmentCreate`.

## Migration
`c7d8e9f0a1b2` adds: `patient_payments.bank_number`; `patient_procedures.hygienist_id`;
`patient_adjustments.write_off_type`; `ledger_insurance_details.{payment_date,payment_method,
check_number,bank_number,eob_number,eft_trace_number,created_by}`;
`procedure_codes.{anatomy,surface,material}_rules`; and the `patient_refunds`,
`patient_statements`, `explosion_codes`, `explosion_code_items` tables.
