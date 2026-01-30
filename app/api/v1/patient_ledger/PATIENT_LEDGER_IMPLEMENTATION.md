## Patient Ledger Module (Backend) — Implementation Notes

### What’s implemented

- **Ledger**
  - `GET /api/v1/patients/{patientId}/ledger`
- **Balances**
  - `GET /api/v1/patients/{patientId}/balances`
- **Procedures**
  - `POST /api/v1/patients/{patientId}/procedures`
  - `GET /api/v1/patients/{patientId}/procedures/{procedureId}`
  - `PUT /api/v1/patients/{patientId}/procedures/{procedureId}`
  - `DELETE /api/v1/patients/{patientId}/procedures/{procedureId}`
- **Claims**
  - `POST /api/v1/patients/{patientId}/claims`
  - `GET /api/v1/patients/{patientId}/claims`
  - `GET /api/v1/patients/{patientId}/claims/{claimId}`
  - `PUT /api/v1/patients/{patientId}/claims/{claimId}`
  - `POST /api/v1/patients/{patientId}/claims/{claimId}/send`
- **Payments**
  - `POST /api/v1/patients/{patientId}/payments`
  - `GET /api/v1/patients/{patientId}/payments/{paymentId}`
- **Adjustments**
  - `POST /api/v1/patients/{patientId}/adjustments`
  - `GET /api/v1/patients/{patientId}/adjustments/{adjustmentId}`
- **Metadata (contract-required)**
  - `GET /api/v1/metadata/procedure-codes`
  - `GET /api/v1/metadata/payment-codes`
  - `GET /api/v1/metadata/adjustment-codes`
  - `GET /api/v1/metadata/claim-statuses`
  - `GET /api/v1/metadata/transaction-types`
- **Providers by office (contract-required)**
  - `GET /api/v1/offices/{officeId}/providers`

### SQL migration

- **File**: `app/api/v1/patient_ledger/sql/migrate_patient_ledger.sql`
- Creates new tenant_1 tables to match the contract without breaking legacy `tenant_1.ledger` / `tenant_1.procedures`.

### ERD-style relationships (high-level)

- `tenant_1.patient_ledger_entries`
  - references `tenant_1.patients`
  - references `public.offices`
  - optional links to: procedure/claim/payment/adjustment IDs (string IDs)
- `tenant_1.patient_procedures`
  - `patient_id` → `tenant_1.patients.id`
  - `procedure_code` → `tenant_1.procedure_codes.code`
  - `ledger_entry_id` → `tenant_1.patient_ledger_entries.id`
  - optional `claim_id` → `tenant_1.patient_claims.id` (stored as string)
- `tenant_1.patient_claims`
  - `patient_id` → `tenant_1.patients.id`
- `tenant_1.patient_claim_procedures`
  - `claim_id` → `tenant_1.patient_claims.id`
  - `procedure_id` → `tenant_1.patient_procedures.id`
- `tenant_1.patient_payments`
  - `patient_id` → `tenant_1.patients.id`
  - `ledger_entry_id` → `tenant_1.patient_ledger_entries.id`
- `tenant_1.patient_payment_applications`
  - `payment_id` → `tenant_1.patient_payments.id`
  - `procedure_id` → `tenant_1.patient_procedures.id`
- `tenant_1.patient_adjustments`
  - `patient_id` → `tenant_1.patients.id`
  - `ledger_entry_id` → `tenant_1.patient_ledger_entries.id`
- `tenant_1.patient_adjustment_applications`
  - `adjustment_id` → `tenant_1.patient_adjustments.id`
  - `procedure_id` → `tenant_1.patient_procedures.id`

### Assumptions / contract gaps (minimal safe)

- **Balances split (patient vs insurance)**: contract requires `patient_balance`, `insurance_balance`, and allocation behavior, but doesn’t define how payments/adjustments apply to charge lines. Current implementation:
  - `patient_balance = account_balance`
  - `insurance_balance = 0` (until insurance allocation rules are specified)
- **Claim details subscriber/coverage fields**: contract expects rich subscriber coverage data; current DB models don’t provide all of it. Current implementation populates required shapes with empty strings where data is unavailable.
- **Procedure update with fee changes**: contract allows updating procedures; but updating fee would require ledger rebalance/retroactive recompute rules. Current implementation blocks fee changes after posting (`422`).
- **Idempotent batch submission**: contract mentions idempotency; current implementation ensures a claim can only be sent once (403 if already sent). If you need true idempotency (retries return same response), we can add a unique event key and return existing “sent” result instead of 403.

### Sample requests

#### Add procedure

`POST /api/v1/patients/123/procedures`

```json
{
  "procedure_code": "D0150",
  "date_of_service": "2026-01-20",
  "provider_id": "PROV001",
  "office_id": "108",
  "tooth": null,
  "surface": null,
  "quadrant": null,
  "materials": null,
  "duration_minutes": 30,
  "fee": 120.00,
  "est_patient": 40.00,
  "est_insurance": 80.00,
  "billing_order": "P",
  "notes": "New patient exam",
  "apply_to": "P"
}
```

#### Create claim

`POST /api/v1/patients/123/claims`

```json
{
  "procedure_ids": ["PRC-..."],
  "claim_type": "dental",
  "billing_order": "primary",
  "notes": "Send electronically"
}
```

#### Send claim

`POST /api/v1/patients/123/claims/CLM-.../send`

```json
{
  "batch_id": null,
  "send_method": "electronic"
}
```

