# Payment Plans (Ortho + Regular) — backend gap response (PP-1…8 · OPP-1…11 · RPP-1…6)

> Response to [`payment_plans_backend_devreport.md`](payment_plans_backend_devreport.md).
> Migration **`e1f2a3b4c5d6`** (down_revision `c0d1e2f3a4b6`) — fully additive: every
> column is nullable or carries a server default, nothing is renamed or retyped.
> Tests: [`tests/test_payment_plans_module.py`](../../tests/test_payment_plans_module.py) (25 cases).

**Everything in the report is implemented.** Nothing is deferred. Two answers you
explicitly asked for are in §4.

---

## 1. Severity 1

### PP-1 · Deleted contracts reappear — **fixed (option a)**

Two separate things were going on, and the distinction matters for your client-side
workaround:

* The **`is_active` query filter was never broken.** I reproduced your exact sequence
  against a clean tenant: `DELETE /ortho-plans/1` → `GET /ortho-plans?patient_id=…&is_active=true`
  correctly returns `[]`. Whatever produced your capture, the generic filter engine does
  honour the parameter (`CRUDBase.list` applies every whitelisted equality filter).
* The **default listing** did return soft-deleted rows, which is the real bug — a page
  load that doesn't pass a filter is the common case, and it brought the contract back.

**What changed:** `CrudConfig` gained an opt-in `hide_soft_deleted` flag, enabled for
`ortho-plans`, `patient-payment-plans` and `patient-reg-plans`. On those three, a list
with no explicit `is_active` now excludes soft-deleted rows:

```
DELETE /api/v1/ortho-plans/1                        → 204
GET    /api/v1/ortho-plans?patient_id=83867         → { items: [] }   ← was [ {id:1, is_active:false} ]
GET    /api/v1/ortho-plans?patient_id=83867&is_active=true   → { items: [] }
GET    /api/v1/ortho-plans?patient_id=83867&is_active=false  → { items: [ {id:1} ] }   ← still available on purpose
```

**Answer to "which of the two is intended":** **(a) — soft delete stays.** A financial
contract must remain recoverable and auditable; a hard delete would orphan any posted
ledger rows that reference it. `is_active=false` is now the explicit "show me the
deleted ones" query (undelete / audit screens).

**You can drop the client-side filter** in `loadOrthoPlan`, `loadRegularPlan` and
`useOverviewData`. The flag is deliberately opt-in per resource rather than global —
`/providers`, `/definitions` and similar screens legitimately list inactive rows by
default, and a blanket change would silently empty them. `tests/test_payment_plans_module.py::test_pp1_does_not_leak_into_other_resources`
pins that.

### PP-5 · `GET /patients/{id}/balance` cold latency — **fixed**

The aggregate ran **six statements**, four of them full scans of the patient's history,
with no composite index to support any of them — and the two "most recent payment"
probes (`ORDER BY payment_date DESC LIMIT 1`, once for insurance and once for patient)
could not use an index at all.

* Charges, estimates, today's charges and all five aging buckets now come from **one**
  conditional-aggregation query instead of three scans.
* Payments are read **once** and reduced in Python (total + today + both last-payment
  probes) instead of four round trips.
* Added `ix_patient_procedures_patient_dos (patient_id, date_of_service)` and
  `ix_patient_payments_patient_date (patient_id, payment_date)`.

Net: **2 scans instead of 6**, both index-backed. The response contract is byte-identical.
Also — posting an instalment now **invalidates the 30 s Redis cache** for that patient,
so a freshly-billed charge shows immediately rather than up to 30 s late.

---

## 2. Ortho Payment Plan — `ortho_plans`

| # | Delivered |
|---|---|
| **OPP-1** | Added **`initial_procedure_code`** (FK → `procedure_codes.code`). I did **not** rename `procedure_code` → `periodic_procedure_code`: it is already live in your Overview panel and the rename would be a breaking change for zero information gain. **`procedure_code` *is* the periodic code** — that is now stated in the model docstring and the OpenAPI description. |
| **OPP-2** | **`pref_provider_id`** (FK → `providers.id`). `OrthoPlanRead` also returns **`pref_provider_name`**, batch-resolved — no per-row `GET /providers/{id}`. It is the default provider the periodic charge posts under (PP-2). |
| **OPP-3** | **`insert_class`**. Seeded as a lookup: `GET /definitions?group_code=insert_class` (`NONE`/`CL1`/`CL2`/`CL3`). |
| **OPP-4** | **`pat_setup_date`**, **`pat_notes`**, **`remarks`** — the patient sub-plan is now symmetric with the two insurance tiers. |
| **OPP-5** | **`financial_disclosure`** (key into `GET /definitions?group_code=financial_disclosure`; seeded `STD`/`NOFIN`/`ORTHO`). The contract endpoint resolves it to `disclosure_text` for you. |
| **OPP-6** | **Tokenised only**, exactly as you asked: `payment_code`, `payment_token_id`, `card_holder_name`, `card_last4`, `card_exp_month`, `card_exp_year`, `post_down_payment_with_card`. **There is no PAN and no CVV column and there will not be one** — card data belongs in a PCI-compliant vault; send us the vault token. A test asserts the schema never grows a `card_number`/`cvv`/`pan` property. You can drop the "not stored" notice for everything except the raw card number and CVV inputs, which should go straight to the vault SDK. |
| **OPP-7** | **`ins_mon_claim_print_fee`**, **`ins_suppress_periodic_printing`**, **`sec_ins_mon_claim_print_fee`**, **`sec_ins_suppress_periodic_printing`**. |
| **OPP-8** | Secondary tier is now **fully symmetric**: added `sec_ins_setup_date`, `sec_ins_down_pay`, `sec_ins_interval`, `sec_ins_num_payments`, `sec_ins_rem_payments`, `sec_ins_rem_amt`, `sec_ins_first_due_date` — plus **`sec_ins_months_remaining`** (you listed 7; the primary has 11, so I added the 8th for true parity). |
| **OPP-9** | New table **`patient_plan_installments`** — see §3. |
| **OPP-10** | Plan-level **`tx_duration_months`** and **`months_remaining`**. Derivation from `banding_date → treat_end_date` is a fine *default*, but it is not authoritative: staff shorten and extend treatment without moving the band dates. Persist what the screen shows. |
| **OPP-11** | `created_by` is a migrated free-text label and could not be retyped without losing it, so: added **`created_by_id`** (FK → `users.id`, stamped on every create), **`updated_by`** (FK → `users.id`, stamped on every PATCH) and **`created_office_id`** (FK → `offices.id`). `OrthoPlanRead` returns **`created_by_name`** (falling back to the legacy string for migrated rows), **`updated_by_name`**, **`created_office_name`** and **`created_office_code`**. Stop falling back to the patient's home office. |

---

## 3. Regular Payment Plan — `patient_payment_plans`

| # | Delivered |
|---|---|
| **RPP-1** | **`tx_plan_amt`** (worksheet line 2 — the intent is now persisted, not recovered by subtraction) and **`treatment_plan_id`** (FK → `treatment_plans.id`, indexed and filterable: `?treatment_plan_id=TP-1`). `tx_plan_number` stays free text and untouched so migrated legacy plan numbers survive — write both. |
| **RPP-2** | **`billing_code`**, matching `patient_ins_payment_plans.billing_code`. `ACBIL : Periodic Contract Billing` is seeded by **`python -m scripts.seed_payment_plan_codes`** (also seeds `ACBILO` for ortho contract billing). |
| **RPP-3** | **`financial_disclosure`** — same lookup as OPP-5. |
| **RPP-4** | Same tokenised block as OPP-6. |
| **RPP-5** | Per-instalment store — see §3 below. |
| **RPP-6** | **`total_of_payments`** persisted. When set it wins over the derived figure in the contract payload, so a reconciliation report and the printed contract cannot disagree. |

---

## 4. Cross-cutting

### PP-2 · Posting periodic billing — **shipped**

`is_billed` / `ledger_id` were dead columns. They aren't now.

```
POST /api/v1/patient-ins-payment-plans/{id}/post        → 201 PostedInstallment
POST /api/v1/patient-sec-ins-payment-plans/{id}/post    → 201
POST /api/v1/patient-plan-installments/{id}/post        → 201
POST /api/v1/payment-plans/post-due                     → 200 PostDueResult   ← the nightly batch
```

A post writes a **real `patient_procedures` charge** and stamps `is_billed` + `ledger_id`
with that charge's id. Everything is resolved from the contract, so the usual call has an
empty body; each value can be overridden per call (`post_date`, `procedure_code`, `fee`,
`provider_id`, `office_id`, `notes`).

Resolution order, and the 422 you get when it runs out:

| | resolved from |
|---|---|
| billing code | request → instalment `billing_code` → contract's periodic code |
| amount | request → `periodic_amt` (must be > 0) |
| provider | request → `ortho_plans.pref_provider_id` → `patients.preferred_provider_id` |
| office | request → contract `office_id` → `patients.home_office_id` |
| date | request → `periodic_date` → today (UTC) |

* **Never double-charges.** Posting an already-posted instalment is a `409` carrying the
  existing `ledger_id` in `details`, not a second charge.
* An **insurance** instalment posts as `insurance_estimate = amount`; a **patient**
  instalment as `patient_estimate = amount`.
* `POST /payment-plans/post-due` sweeps every unbilled instalment with
  `periodic_date <= through_date` (default today) across all three tables. Optional
  `patient_id` / `ortho_plan_id` / `payment_plan_id` / `sides` narrowing, and
  **`dry_run: true`** to see what *would* post. One bad row (missing provider, unknown
  code) lands in `skipped` with the reason — it never aborts the sweep.

### PP-3 · Contract / coupon reports — **shipped, server-rendered**

```
GET /api/v1/payment-plans/{ortho|regular}/{plan_id}/contract       → JSON  (ContractResponse)
GET /api/v1/payment-plans/{ortho|regular}/{plan_id}/contract.pdf   → application/pdf
GET /api/v1/payment-plans/{ortho|regular}/{plan_id}/coupons.pdf    → application/pdf
```

The PDFs are rendered with `reportlab` (added to `requirements.txt`; imported lazily, so
a deployment without it still serves the JSON and returns a clear 422 on the PDF routes).
The contract carries the Truth-in-Lending box, the full schedule with per-instalment
POSTED/due state, the resolved disclosure text, patient/responsible-party/office/provider,
and a signature block. Coupons are five per page with tear-off rules.

The **JSON `contract` endpoint is the more useful half**: every figure is computed
server-side from the stored terms, so if you keep jsPDF for a customised layout you can
at least stop deriving the numbers on the client and the paper output will still agree
with a reconciliation report.

### PP-4 · `patient_reg_plans` vs `patient_payment_plans` — **answer: `patient_payment_plans` is canonical**

`patient_reg_plans` is a **migration-only** landing table for legacy rows. It stays
exposed read-only-in-practice so nothing that reads it breaks, but **write new contracts
to `patient_payment_plans`** — you already are, and that is correct. It is the only one
of the two that gained the RPP columns above; `patient_reg_plans` did not and will not.
Once the Overview CONTRACT panel no longer needs the legacy rows, we can retire it.

### PP-6 · FK from an ortho plan to its billing rows — **shipped**

**`ortho_plan_id`** (FK → `ortho_plans.id`, indexed) added to `patient_ins_payment_plans`
and `patient_sec_ins_payment_plans`, and it is a list filter:
`GET /patient-ins-payment-plans?ortho_plan_id=42`. A patient with two ortho contracts over
time now has cleanly separable schedules. `legacy_plan_id` is untouched for migrated data.

### PP-7 · Audit trail — **shipped**

`updated_by` + `created_by_id` on both contract tables (see OPP-11), with resolved
`created_by_name` / `updated_by_name` on both read models. Contract mutations were already
captured by `AuditMiddleware` → `audit_logs` (every authenticated 2xx POST/PUT/PATCH/DELETE);
`GET /audit-logs?resource=ortho_plans&resource_id={id}` is the per-contract change history.

### PP-8 · `plan_type` vocabulary — **constrained**

`plan_type` is now `regular | ortho` on the write models. Casing is normalised rather than
rejected (`"Ortho"` → `"ortho"`); anything else is a `422`. **Reads stay a plain string** so
migrated legacy values still serialise — do not let the FE assume the enum on read. The
vocabulary is also a lookup: `GET /definitions?group_code=plan_type`.

---

## 5. New: the patient-side instalment store (OPP-9 / RPP-5) + server-side amortisation

One table serves both cases — the row shapes were identical, so a `plan_side`
discriminator beat two near-duplicate tables:

**`patient_plan_installments`** — `plan_side` (`patient`|`ins`|`sec_ins`), exactly one of
`ortho_plan_id` / `payment_plan_id`, then the same columns as `patient_ins_payment_plans`
(`periodic_order`, `periodic_date`, `periodic_amt`, `plan_amount`, `down_payment`,
`rem_total_amt`, `rem_payments`, `is_billed`, `billing_code`, `ledger_id`). Full CRUD at
`/api/v1/patient-plan-installments`.

Rather than make you write 24 rows one at a time, the schedule is a first-class resource:

```
GET  /api/v1/payment-plans/{kind}/{plan_id}/installments            → terms + rows
PUT  /api/v1/payment-plans/{kind}/{plan_id}/installments            → replace the unposted rows
POST /api/v1/payment-plans/{kind}/{plan_id}/installments/generate   → amortise from the contract
```

`…/generate` with an **empty body** reads the contract's own terms and amortises them:
`A = P·r / (1 − (1+r)⁻ⁿ)`, `r = APR / periods-per-year`, zero APR degrading to `P / n`.
`interval_type` accepts your spellings (`monthly`, `semi-monthly`, `bi weekly`, `quarterly`,
`annually`, …). Any field can be overridden in the body; `persist: false` returns a preview
without writing.

Two properties worth knowing:

* **The final instalment absorbs the rounding residue**, so the rows sum to
  `total_of_payments` exactly. A client-side projection that rounds each instalment
  independently drifts by up to a cent per payment — over 24 payments that is a real
  reconciliation discrepancy.
* **`PUT …/installments` never destroys a posted row.** Re-amortising a contract mid-term
  replaces only the unposted instalments; anything already in the ledger survives untouched.

---

## 6. To run

```bash
python -c "from alembic.config import main; main(['upgrade','head'])"
python -m scripts.seed_payment_plan_codes        # ACBIL / ACBILO (global, once per DB)
python -m scripts.seed_account_definitions       # plan_type, insert_class, financial_disclosure
pip install -r requirements.txt                  # picks up reportlab for the PDFs
```

`financial_disclosure` is seeded with three **placeholder** labels — replace the
`description` text with the practice's approved wording before anything prints for a
patient.
