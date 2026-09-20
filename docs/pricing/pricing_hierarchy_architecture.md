# Pricing hierarchy: Fee Schedules × Procedure Codes × Insurance Plans

> Architecture and flow reference (2026-09-12). Evidence base: backend + frontend code,
> the Denticon export under `F:/Recon Dental Data/...`, and the dev DB.
>
> **Status: R1 code complete (steps 1–6) behind ``PRICING_ENGINE_V2`` (default off).**
> Schema + 4/7 backfill sections applied to the dev DB; resolver, split engine,
> ``apply_split`` on both write paths, Setup guardrails, the endpoints + bulk ops,
> and the parity script all landed and green (1275 tests). The engine is still dark.
> Next is **R2**: apply the held office/carrier backfill sections, re-run the parity
> script (targeting ≥ 97 % on the reachable subset), then flip the flag in R3.
> See "R1 progress" below for exactly what is live, what is deliberately held, and the
> two findings that changed the plan.

## Context

Three Setup screens each hold "a number" about a procedure code: Fee Schedules (a fee per code per
list), Procedure Codes (a `default_fee`, plus a read-only per-code fee grid and an *Insurance* tab),
and Insurance Plans (coverage % per category). The Fee Schedule screen also has an "Insurance Fee"
column and a "Type" of `carrier`/`plan`, so it is not obvious which screen owns which number, who
wins, or how a posted charge ends up with a patient portion and an insurance portion.

The investigation (backend, frontend, the Denticon export at `F:/Recon Dental Data/…`, and the dev DB)
found that the confusion is real and not only cosmetic:

- **The browser is the pricing engine.** `GET /patients/{id}/fee` and `POST /patients/{id}/estimate`
  have zero importers outside the generated client; every charge is priced by
  `dentc-frontend/src/services/feeScheduleResolver.ts` + `coverageResolver.ts` + `procedurePricing.ts`,
  and `procedureEntryService.postCompletedProcedure` always sends `fee`, so
  `PatientProcedureCRUD._price` ([patient_procedure_service.py:150](../../app/services/patient_procedure_service.py))
  short-circuits. Server pricing is structurally unreachable, and no server path fills
  `insurance_estimate`/`patient_estimate` — the columns claims, A/R and the dashboard sum.
- **Two engines, two split rules.** The client lets `entry.insurance_fee` beat the coverage % and
  ignores deductible/max; the server ignores `insurance_fee` and applies both. Pressing *Re-estimate*
  visibly changes numbers the client just wrote.
- **The resolver reads none of the pointers that explain posted history.** Denticon's
  `PATIENT.FEESCHEDULE` (94% of patients, explains 85% of 2025 charge amounts), `Office.FEEID` (all 15
  offices, explains 96% of `ucr_fee`), `Office.PATIENTFEEID` and `Carrier.FEEID` were all dropped by
  the migration; `patients.fee_schedule_id` (34 rows) and `insurance_carriers.fee_id` (13 rows) exist
  but nothing reads them. The only tier that fires today is eight all-NULL "practice-wide" assignment
  rows (two legacy rows inserted four times by `s51`) alternating between two different schedules.
- **Denticon's per-charge provenance was never migrated**: `LEDGERINSD/` (1.45M rows carrying
  `FEEID` + `EFFECTIVEDATE` + per-tier estimates) was skipped by `s32`, which read only the 12k-row
  archive. Joined offline, `FeeScheD[LEDGERINSD.FEEID][CODE].PATAMT == LEDGER.AMOUNT` on **99.66 %**
  of 2025 charges — the Denticon model is fully recoverable and testable.

The intended outcome is one documented hierarchy that three different maintainers can operate without
contradicting each other, with the server as the only place a fee or a split is computed, and every
posted charge carrying the provenance of how it was priced.

---

## 1. The model in one page (this is the architecture)

### 1.1 One owner per number

| Concept | Owner (screen → table) | Must never live in |
|---|---|---|
| **What a code is** (description, category, `coverage_category` band key, clinical `requires_*`, AMB/downgrade, ortho flag) | Procedure Codes → `procedure_codes` | — |
| **What a code costs** on a price list (dollar per code, effective-dated) | Fee Schedules → `fee_schedule_entries.patient_fee` | `procedure_codes.default_fee` (retired as a pricing input — Denticon `Codes.txt` has no fee column), any plan column, a client payload |
| **Plan-pays fixed amount** (copay/capitation/Medicaid lists only) | Fee Schedules → `fee_schedule_entries.insurance_fee` on a schedule with `pricing_model='copay'` | any percentage-model schedule (refused), the PPO split |
| **Who uses which price list** (binding) | Fee Schedule Assignments → `fee_schedule_assignments`; Office Setup → `offices.default_ucr_fee_schedule_id` / `default_fee_schedule_id`; Patient → `patients.fee_schedule_id` | `fee_schedules.ins_plan_id`/`office_id` (dead, NULL on every row → deprecated), `insurance_carriers.fee_id` (folded into assignments), all-NULL assignment rows |
| **How the cost is shared** (coverage %, ded-waived, frequency, age, waiting; deductible/max limits) | Insurance Plans → `insurance_coverage_rules` + `insurance_plans.individual_*`/`family_*`/`ortho_max` | `procedure_insurance_rules` (retired — zero readers), fee schedules, carriers, the browser's `CDT_CATEGORIES` table |
| **Remaining benefits for a person** | Patient Insurance slot → `patient_insurance.deductible_remaining` / `max_remaining` / `ortho_remaining` (NULL = unknown → plan limit; 0 = exhausted) | the estimate engine (never writes them back) |
| **Which fee prints on the claim** | Insurance Plans → `insurance_plans.fees_to_print` (`office_ucr` \| `plan_fees`) | pricing — it never changes the posted fee or the split |
| **Provenance of a posted charge** | Server at post time → `patient_procedures.fee_schedule_id`, `fee_source`, `fee_effective_date`, `ucr_fee`, `insurance_estimate`, `patient_estimate`, `estimated_deductible`, `coverage_pct` | the client; a later Setup edit (snapshot semantics, like Denticon `LEDGERINSD.FEEID`) |

### 1.2 The "insurance" term on the Fee Schedule screen, settled by the data

- `fee_schedule_entries.insurance_fee` = Denticon `FeeScheD.INSAMT`. It is a **fixed dollar amount the
  plan pays per code on an "Assign To Plan" (Medicaid/DHMO/capitation) schedule**, where
  `patient_fee` is the patient's copay. Evidence: `INSAMT` is non-zero on 356 of 13,488 legacy rows and
  354 of them sit on the two `FEETYPE=2` schedules (legacy 147 "Highmark New", 148 "UPMC For You
  Medicaid New") where `PATAMT` is blank (D0120 → 0.00 / 26.16 vs UCR 44.00).
- It is **not** a percentage and **not** a second patient price. Percentages live only in
  `insurance_coverage_rules`.
- `fee_schedules.fee_type` = Denticon `FEETYPE`, an **assignment mode**: `0` unbound (office/patient
  list), `2` assign-to-plan, `3` assign-to-carrier. The migration mapped `1/2/3` but the data holds
  `0/2/3`, so 12 of the 13 schedules labelled `ucr` today (CP-40, CP-50, "Delta Dental Premier - Excel",
  …) are practice/patient price lists, not UCR. Only legacy 109 "UCR -Excel Dental" (+ 146, 135, which
  are other offices' `Office.FEEID`) are UCR lists.
- `insurance_plans.fees_to_print` = Denticon `PRINTOFFICEUCR` (1 on 27,421 plans, 0 on 3,907): claim
  printing only.

### 1.3 Who gets a fee schedule (Denticon parity)

- **Office** gets two pointers: **UCR list** (`default_ucr_fee_schedule_id` ← `Office.FEEID`, set on all
  15 offices) and **default patient list** (`default_fee_schedule_id` ← `Office.PATIENTFEEID`, the list a
  new patient is registered with; 8 offices set it, else the UCR list doubles). One schedule may serve
  both roles (109 does, for 12 offices) — no cloning.
- **Patient** gets one pointer, `patients.fee_schedule_id` ← `PATIENT.FEESCHEDULE`, defaulted from the
  home office at registration. It is the **default input**, not a top override.
- **Plan / carrier** never own a column (Denticon `InsPlans.txt` has no `FEEID`). They are bound
  through `fee_schedule_assignments`, and a payer binding **overrides** the patient's list at post time
  (~16 % of 2025 charges were priced by carrier schedules 110–122 that never appear on any patient).
- **Provider / specialty** are assignment keys only (`FeeScheA.PROVIDERID`; `Providers.txt` has no fee
  column).

### 1.4 Precedence card (the resolver, most specific first)

```
0. Explicit override      fee_override=true + reason (+ permission)          fee_source=override
1. Plan assignment        fee_schedule_assignments.ins_plan_id = primary plan fee_source=assignment_plan
2. Carrier assignment     …carrier_id = primary plan's carrier (no plan key)  fee_source=assignment_carrier
3. Patient's own list     patients.fee_schedule_id                            fee_source=patient_schedule
4. Provider/specialty asg …provider_id / specialty_id (no payer key)          fee_source=assignment_provider
5. Office default list    offices.default_fee_schedule_id                     fee_source=office_default
6. Office UCR list        offices.default_ucr_fee_schedule_id                 fee_source=office_ucr
7. Unpriced               fee=null, policy decides (see §3.4)                 fee_source=unpriced
```

Rules that make the card deterministic:

- Assignment rank is **lexicographic on the key vector** (plan › carrier › provider › specialty), never
  a key count or a weight sum: a `{plan}` row always beats a `{carrier, office}` row. `office_id` and
  `office_group_id` only **narrow** a row (`{carrier, office}` beats `{carrier}`), they never raise it,
  and they **cannot stand alone** — office-wide defaults have exactly one home (tier 5/6).
- The fee is always the **primary dental payer's** allowed amount; secondary/tertiary plans affect the
  split only. A medical (`M`) slot never prices dental.
- Within a schedule the entry in force is the latest `effective_date <= date_of_service`; if none, the
  **earliest** row (all 13,493 legacy rows are dated 2020+ while 71 % of charges predate 2020) with
  warning `entry_predates_service_date` — unless every row is future-dated, which is `unpriced` with
  `entry_not_yet_effective` (never price today at next month's fee).
- A `patient_fee <= 0` entry on a percentage schedule is **not priced** (walk continues) unless the
  entry carries the new explicit `is_no_charge` flag. 3,866 legacy entries are `0.00` blanks (619 on
  CP-50, 225 on CP-40); today they win and post $0.
- A payer tier that **matched but lacks the code** is a distinct outcome (`code_missing_on_bound_schedule`
  warning + health finding), never a silent skip to the practice list.
- `ucr_fee` is looked up on tier 6 **in parallel** whatever tier priced the fee; expected write-off =
  `ucr_fee − fee` (NULL, not 0, when the office has no UCR list).
- Whatever wins is **snapshotted** on the row; later Setup edits never re-price posted history.

### 1.5 The split, per benefit model

Decided by the **schedule that priced the line** (`fee_schedules.pricing_model`), because Denticon's
`INSAMT` lives on the schedule and the plan's `ISPREPAID` code was destroyed by the migration
(8-value code → boolean, True on 9 of 31,337 plans).

- **A · percentage** (PPO / indemnity / Premier — every migrated plan): `fee` = resolved allowed amount;
  `coverage_pct` = ranked band match (`estimate_service.match_coverage_rule`, unchanged);
  cap first, then deductible: if the remaining max is 0 → ins 0 and **no** deductible consumed;
  else `ded = min(remaining_ded, fee)` unless `ded_waived`, `ins = round((fee − ded) × pct)`, capped by
  remaining max (ortho codes against `ortho_remaining`; `exempt_from_dental_max` skips the cap);
  `patient_estimate = fee − ins`. `insurance_fee` is ignored.
- **B · copay** (assign-to-plan Medicaid/DHMO lists): `fee = patient_fee if patient_fee > 0 else
  insurance_fee` (**never summed** — the two SAMPLE plan lists carry both columns and would double);
  `insurance_estimate = insurance_fee`; `patient_estimate = fee − insurance_estimate`; no %, no
  deductible, no max. **Provisional** until validated against `LEDGER` rows whose `LEDGERINSD.FEEID`
  is 147/148 (only 8 such app-era charges exist today, all at exactly `INSAMT`). `per_visit_copay` is
  a **visit-level** line, never folded into a procedure's fee (out of scope for R1; reported only).
- **C · self-pay** (no active dental slot): tiers 3–6; ins 0; patient = fee.
- **Secondary (COB)**, behind `include_secondary` until the 954 destroyed secondary slots are
  restored: standard = `min(pct2 × (fee − ded2), fee − prim_ins, max2)`; non-duplication
  (`is_non_dup_benefits`) = `max(0, pct2 × fee − prim_ins)`. `insurance_estimate` stays the **primary**
  expectation (claims sum it per payer); `sec_insurance_estimate` is its own column;
  `patient_estimate = fee − prim − sec`.
- **Cross-line state**: deductible and max consumed by *already posted* non-void charges on the same
  plan in the benefit year are netted before the line is priced, so a 4-line visit posted as 4 POSTs
  equals one 4-line `/estimate`. Lines are consumed in a deterministic order (payload order in a batch;
  `date_of_service, procedure_code, id` otherwise).

---

## 2. What the evidence says (so nobody re-litigates it)

| Fact | Number |
|---|---|
| Charge fee = schedule named on the charge's `LEDGERINSD.FEEID` | 50,176 / 50,348 (99.66 %) 2025 charges |
| `ucr_fee` = the office's `Office.FEEID` list | 48,781 / 50,667 (96.3 %) |
| Charge fee = the patient's own `FEESCHEDULE` list | 42,227 / 49,561 (85.2 %); the rest priced by carrier lists 110–122 |
| `UCRFEE > AMOUNT` (the PPO write-off) | 32,440 rows, mean **$143.85**/line |
| `PATIENT.FEESCHEDULE` populated | 79,079 / 83,861 patients (never migrated) |
| `Office.FEEID` populated | 15 / 15 offices (never migrated) |
| Practice-wide assignment rows in dev DB | 8, all keys NULL, alternating fs 4 / fs 26 (migration re-run bug, not legacy data) |
| Real offices with any fee pointer | 0 / 15 |
| `patient_fee = 0.00` entries | 3,866 / 13,493 (blank `PATAMT` parsed as 0) |
| `insurance_fee > 0` entries | 361; 354 on the two Medicaid plan lists, 7 stragglers on other lists |
| `procedure_codes.default_fee > 0` | 3 / 1,122 (no legacy source) |
| Coverage rules banded by category vs ADA range | 876,876 vs 25 |
| Secondary insurance slots after migration | 1 (source has 954 `INSTYPE='S'`; `s19` read a column that does not exist) |
| `deductible_remaining > 0` slots | 3 / 55,119 (`s19` read `INDDEDUCTREM`; real column `INDDEDREM`) |
| Charges with a stored `fee_schedule_id` | 0 / 1,372,616 |

---

## 3. Target design (detail)

### 3.1 Vocabulary (one module, published at `GET /fee-schedules/metadata`)

New `app/services/fee_vocab.py`:

- `FEE_TYPES = ('ucr', 'standard', 'plan', 'carrier')` — labels "Office UCR list", "Practice / patient
  price list", "Assign to Plan", "Assign to Carrier". **Advisory**: drives picker filters and the
  Plan-Pays column; it does not gate which pointer may reference the schedule (one list can be an
  office's UCR and a patient's list, as 109 is). Enforced as an enum (Literal + CHECK) after
  normalisation.
- `PRICING_MODELS = ('percentage', 'copay')` on `fee_schedules.pricing_model`; CHECK
  `pricing_model = 'percentage' OR fee_type IN ('plan','carrier')` so a copay list is only reachable
  through a payer tier; `insurance_fee` is refused (422 `insurance_fee_not_allowed`) on percentage lists
  **when the field is being written** (legacy rows stay editable).
- `FEE_SOURCES = ('override','client_legacy','assignment_plan','assignment_carrier','patient_schedule',
  'assignment_provider','office_default','office_ucr','unpriced','plan_item','migrated')`.
- `ASSIGNMENT_RANK = ('ins_plan_id','carrier_id','provider_id','specialty_id')`; `office_id`,
  `office_group_id` are scope-only keys.
- The precedence card text itself, so the Setup landing page renders it from the server.

### 3.2 Resolver — `app/services/pricing_service.py` (rewrite in place, same public shape)

- `resolve_procedure_fee(db, tenant_id, code, *, patient_id, office_id, provider_id, ins_plan_id,
  date_of_service, ctx)`; `build_context` gains `patient_fee_schedule_id`, `office_default_fee_schedule_id`,
  `ucr_fee_schedule_id`, `date_of_service` (default = office today via `office_today`), and takes the
  primary plan from the single coverage picker (§3.3).
- `_candidates` → SQL-side match (`WHERE (ins_plan_id IS NULL OR ins_plan_id = :plan) AND …` for all
  six keys) ordered by the rank vector, then `id DESC`; all-NULL rows ignored with a logged warning
  (belt-and-braces until they are deleted). Keep the Python scorer only for `conflicts[]`, which now
  compares `patient_fee` **and** `insurance_fee`.
- `_entry(db, schedule_id, code, on)` implements the dating rule of §1.4 and returns
  `(entry, warnings)`; `_priced` = `patient_fee > 0 or is_no_charge` on percentage lists,
  `patient_fee > 0 or insurance_fee > 0` on copay lists.
- Tier walk exactly as the card; delete the `fee_schedules.ins_plan_id` tier and the
  `procedure_codes.default_fee` tier.
- Return adds `fee_effective_date`, `fee_type`, `pricing_model`, `entry_id`, `assignment_id`,
  `ucr_fee_schedule_id`, `expected_write_off` (nullable), `is_unpriced`, `skipped[]`, `warnings[]`.
  `fee` stays a non-null Decimal (0 when unpriced + `is_unpriced=true`) so the Orval types do not
  change shape.

### 3.3 One coverage picker + one split engine — `app/services/estimate_service.py`

- `coverage_context(db, patient_id, *, on)` → ordered tiers (primary, secondary, tertiary) of active
  dental slots (`ins_plan_id NOT NULL`, `legacy_plan_type IS DISTINCT FROM 'M'`) with plan, rules,
  remaining figures (NULL → plan limit, 0 → exhausted). Replaces `estimate_service._primary_coverage`,
  `pricing_service.primary_plan_id`, `treatment_service._active_insurance`, `print_service._pick_slot`;
  a grep-based test asserts nothing else selects `PatientInsurance` for pricing.
- `estimate_lines(db, tenant_id, coverage, pricing_ctx, lines, *, date_of_service, consumed)` is the
  only arithmetic; `estimate()` (the `/estimate` endpoint) and the write paths call it. `consumed` =
  deductible/max already applied by posted non-void charges on the same plan since the anniversary
  (one query), so single-line posts and batch estimates agree.
- `apply_split(db, tenant_id, payload, *, current=None, actor_user_id, permissions)` is the **only**
  write-path helper: decides whether pricing runs (create; or an explicit reprice action), enforces
  the override discipline (§3.4), fills `fee`, `fee_schedule_id`, `fee_source`, `fee_effective_date`,
  `ucr_fee`, `insurance_estimate`, `sec_insurance_estimate`, `patient_estimate`, `estimated_deductible`,
  `coverage_pct`, `coverage_rule_id`. `patient_estimate` is **never** read from a payload.
- `treatment_service.re_estimate` becomes a thin caller (delete its duplicated deductible/max code);
  `_upsert_detail` writes one `treatment_plan_insurance_details` row per tier keyed on
  `billing_order` in `('1','2','3')` (vocabulary in `fee_vocab.TIER_KEYS`); `use_new_fees` goes through
  `CRUDBase.update` so the previous fee is in the audit diff.
- `billing_service.expand_explosion_code` returns codes and lets the estimate price them (drop the
  fourth fee source).

### 3.4 Write paths and the override discipline

- `PatientProcedureCRUD._price` → `apply_split`. `TreatmentPlanItemCRUD.create/update` and
  `post_item_to_ledger` likewise; posting a plan item re-prices at the posting office/date by default
  (`keep_planned_fee=true` records `fee_source='plan_item'` with the item's schedule) and always fills
  `ucr_fee` (today plan-posted charges never get one).
- **Compatibility window (R1–R2)**: a client-supplied `fee` is accepted as `fee_source='client_legacy'`,
  counted by the health report, and the split is still recomputed server-side. **R3**: a bare `fee`
  is 422 `fee_not_accepted`; the only client money input is `fee_override=true` +
  `fee_override_reason` (checked with `permission_service.has_strict`, seeded to every role that can
  post charges today so nobody is locked out on release day). `insurance_estimate`/`patient_estimate`/
  `ucr_fee`/`fee_schedule_id` are excluded from the Create/Update schemas (hand-written
  `PatientProcedureCreate/Update`, model-derived base + the two override fields).
- PATCH never re-prices implicitly: a fee change on an unclaimed charge re-runs the **split only**;
  re-pricing is an explicit `POST /patient-procedures/{id}/reprice` (refused with any posted payment).
- **Unpriced policy** per office (`offices.unpriced_charge_policy`): `flag` (post at 0.00 with
  `fee_source='unpriced'`, warning on the quote, health finding) or `refuse` (422 `procedure_unpriced`
  naming the tiers consulted). Default `flag` for the migrated tenant; the health report shows when an
  office can flip to `refuse`. Same switch governs `office_not_configured_for_pricing` (no UCR list).
- `POST /pricing/quote {office_id, provider_id?, ins_plan_id?, patient_id?, date_of_service, lines[]}`
  for the scheduler / templates / add-patient screens that quote before a patient or a DOS exists;
  `POST /patients/{id}/estimate` and `GET /patients/{id}/fee` gain `date_of_service` and echo every
  override they were given in `context`.

### 3.5 Setup screens — responsibilities

- **Fee Schedules** (owner: fee/contract maintainer): schedule header = name, type (enum), pricing
  model (only selectable for plan/carrier types), active. Entries grid: Code, Description, **Fee**
  (`patient_fee`; labelled *Patient Copay* on copay lists), **Plan Pays** (`insurance_fee`, rendered only
  on copay lists), AMB code, Effective, No-charge flag. Bulk actions call the server
  (`PUT /fee-schedules/{id}/entries/bulk`, `POST …/adjust`, both accepting a future `effective_date`
  = the "New Effective Date" workflow **inside one schedule**; no clone-and-repoint). "View by Codes"
  gains a *Try it* box (patient + office + date → which tier wins and why, via `/patients/{id}/fee`).
  A *Where used* panel (`GET /fee-schedules/{id}/usage`); delete/deactivate refused while referenced.
  Never shows a percentage.
- **Fee Schedule Assignments** (same owner, the **only** binding table): target required
  (plan/carrier/provider/specialty; office/group narrow only), Office Group + Specialty become pickers,
  rows editable (PATCH), duplicates 409, rank shown per row, health banner. The "leave blank to apply
  broadly" text is replaced by "Office-wide defaults are set in Office Setup".
- **Procedure Codes** (owner: codes maintainer): description, categories, `coverage_category`
  (relabelled "Insurance coverage category — the band plans price against"), clinical flags, AMB.
  `default_fee` hidden (column kept one release). The *Insurance* tab is removed (410). The *Fee
  Schedules* tab stays read-only (already the case) and states the boundary.
- **Insurance Plans** (owner: insurance maintainer; already permission-gated): coverage grid, limits,
  `is_prepaid` relabelled "Capitation / copay plan (prices from a copay list)", `per_visit_copay`,
  `fees_to_print` relabelled "Fees printed on claims (printing only)", `is_non_dup_benefits`. New
  read-only *Fee schedule in effect* panel (`GET /insurance-plans/{id}/fee-binding`) with a deep link
  to Assignments; "copy from existing" offers `copy_fee_binding`. The wizard never picks a schedule.
- **Office Setup**: UCR list (required to activate an office that posts charges), default patient
  list, unpriced-charge policy; pickers filtered by type; validated by a new `OfficeCRUD`
  (tenant + active; type advisory). Served by `PATCH /offices/{id}/fee-defaults`.
- **Patient**: `fee_schedule_id` defaulted from the home office on create (delete the hard-coded
  `'CP-50'`), tooltip "Used when no plan/carrier list applies; posted charges never change", one flat
  wire shape for create and edit. Bulk `POST /fee-schedules/{id}/reassign-patients` (batched, audited)
  backs the *Change Patient Fee Schedule* utility, which is what makes retiring a list possible.
- **Charge entry** (Transactions, Ledger Add Proc, Restorative, Treatment Plan, Post to Ledger,
  scheduler pickers): preview via the estimate/quote endpoints, post without money fields, render the
  returned provenance ("44.00 from CP-40 · patient list · Ins 80 % Diagnostic on Delta PPO · ded 0 ·
  UCR 50.00 · write-off 6.00") plus warnings; override control only where permitted.

### 3.6 Guardrails (impossible / refused / reported) and operator sync

- **Impossible**: `fee_type`/`pricing_model` CHECKs; `UNIQUE (fee_schedule_id, procedure_code,
  effective_date)` with `effective_date NOT NULL`; `UNIQUE (tenant_id, legacy_id)` on schedules and
  assignments; expression unique index on the assignment key tuple; `tenant_id` on
  `fee_schedule_entries` (closes the cross-tenant write hole — the table has no tenant scope today).
- **Refused**: assignment without a payer/provider key (422); duplicate target (409); schedule from
  another tenant / inactive (422); delete or `is_active=false` while referenced (409 with the
  reference list; `is_active` leaves the generic update schema in favour of `/retire` + `/restore`);
  `insurance_fee` written on a percentage list (422); `fee_not_accepted` (R3); override without
  reason. Validators fire only when the field is **present and changed**, so legacy rows stay editable.
- **Reported**: `GET /setup/pricing-health` (per office) with coded findings — `office_without_ucr`,
  `office_without_default`, `assignment_to_inactive_schedule`, `assignment_never_reachable`,
  `code_missing_on_bound_schedule` (ranked by 12-month volume), `zero_fee_entries`,
  `insurance_fee_on_percentage_schedule`, `capitation_plan_without_copay_binding`,
  `codes_needing_a_price`, `code_without_coverage_category`, `client_legacy_fees_posted`,
  `unpriced_charges_posted`, `legacy_binding_columns_unfolded`. Every finding names the owning screen.
- **Sync between the three maintainers** (the part a pull-based report alone does not give): a
  pre-save impact preview on fee-side writes (`usage` counts + charges in the last 90 days), a change
  feed per Setup screen from the existing `audit_logs` filtered to the fee/coverage tables, the
  *codes needing a price* queue with "add to these N lists at $X", and the precedence card on the
  Setup landing page.
- **Permissions symmetry**: `write_permissions` on FeeSchedule, FeeScheduleEntry,
  FeeScheduleAssignment, ProcedureCode, Office (codes already exist in the catalog; seed via
  `scripts/seed_permissions.py`). Reads never gated.
- **Tenancy caveat to decide**: `procedure_codes` is global (no `tenant_id`), so `coverage_category`
  and `default_fee` edits are cross-tenant. Recommended follow-up: a per-tenant
  `procedure_code_settings` overlay consulted first by `coverage_category_service.category_for`.

### 3.7 Schema changes (one Alembic revision, random hex id, `down_revision='431b5da5630e'`)

- `fee_schedules`: `pricing_model` (default `percentage`), CHECKs (added **after** the in-revision
  normalisation), unique `(tenant_id, legacy_id)` replacing the global unique; `ins_plan_id`/`office_id`
  marked deprecated (unread, excluded from write schemas; dropped one release later).
- `fee_schedule_entries`: `tenant_id` (backfilled from the schedule), `is_no_charge`, `updated_at`/
  `updated_by`, `effective_date NOT NULL`, unique + index `(fee_schedule_id, procedure_code,
  effective_date DESC)`. Pre-flight aborts if duplicates exist (none in dev).
- `fee_schedule_assignments`: `updated_at`/`updated_by`, CHECK has-payer-or-provider key, expression
  unique index (Postgres; CRUD pre-check carries the rule on SQLite), unique `(tenant_id, legacy_id)`.
  All-NULL rows are **not** deleted in this revision (see §4 ordering).
- `offices`: `unpriced_charge_policy`. `patients` unchanged.
- `patient_procedures` + `treatment_plan_items`: `fee_source`, `fee_effective_date`,
  `fee_override_reason`, `estimated_deductible`, `coverage_pct`, `coverage_rule_id`,
  `sec_insurance_estimate` (items also gain `ucr_fee`). **Not** on `ledger_insurance_details` — that is
  the remittance table; claim `total_paid` is derived from it and charge-time rows would corrupt it.
- `patient_insurance`: `legacy_id` (needed to repair secondary slots deterministically).
- `insurance_plans`: `legacy_prepaid_code`, `is_non_dup_benefits`.
- New `patient_procedure_fee_provenance` (procedure_id unique, fee_schedule_id, fee_effective_date,
  per-tier est/ded/max-consumed, contracted amount) — the landing table for the 1.45M `LEDGERINSD`
  rows and the validation set; nothing in billing reads it.

### 3.8 Data: backfill from the export, fix the migration steps

`scripts/backfill_pricing_hierarchy.py` (dry-run default, per-section report with before/after fee
diffs for the top 200 codes, `--apply`, tenant-scoped, idempotent), in this order:

1. `fee_type` normalisation: schedules that are any office's `Office.FEEID` (109, 146, 135) → `ucr`;
   other `FEETYPE 0` → `standard`; `2` → `plan`; `3` → `carrier`; API rows (`office`/`provider`/
   `STANDARD`/NULL) → `standard`, `UCR` → `ucr`. `pricing_model='copay'` where `insurance_fee > 0`
   dominates `patient_fee > 0` (fs 35, 36 only; the SAMPLE lists stay percentage). NULL the 7 stray
   `insurance_fee` values on percentage lists (audited). NULL `patient_fee` where the source `PATAMT`
   was blank.
2. Offices ← `Office.txt` (`FEEID` → UCR, `PATIENTFEEID` else `FEEID` → default; test offices 38/39
   re-pointed off their carrier schedule).
3. Patients ← `PATIENT/*.txt FEESCHEDULE` (79,079 rows; `0` → NULL; `--overwrite` for the 34 hand-set,
   the one on a carrier list reported).
4. Carrier bindings ← `insurance_carriers.fee_id` (13 rows → carrier-keyed assignments; then NULL the
   column). Provider row (legacy `PROVIDERID 102` → 109) only after a read-only re-price of that
   provider's 2025 charges confirms it.
5. `fee_schedule_entries.amb_code` ← `FeeScheD.AMBCODE` (36 clean rows).
6. `insurance_plans` ← `InsPlans.txt`: `fees_to_print` (`PRINTOFFICEUCR` 1 → `office_ucr`, 0 →
   `plan_fees`), `network_type`, `per_visit_copay`, `is_non_dup_benefits`, raw `ISPREPAID` →
   `legacy_prepaid_code` (no `is_prepaid` change until the 8 codes are decoded — decision §6).
7. `patient_insurance` repair ← `PatInsPlans.txt` (`INSTYPE` P/S, `INDDEDREM`, `INDORTHOREM`) with a
   diff of every patient whose **primary** plan would change and a separate `--apply-primary-changes`;
   the NULL-vs-0 deductible change is reported (delta to `insurance_estimate` across 55k slots) and
   applied only with `--apply-deductibles`.
8. Provenance ← `LEDGERINSD/*.txt` into `patient_procedure_fee_provenance` (+ stamp
   `patient_procedures.fee_schedule_id`, `fee_source='migrated'`, `fee_effective_date`); load
   `TREATPLANINSD` the same way (fix the false `s52` stub).
9. **Last**, and only once every office that posted in the last 90 days has both pointers and ≥ 90 %
   of active patients have a list: delete assignment ids 1–8.

Historical `patient_estimate` is **not** mass-updated; `ledger_service.split_of(proc)` becomes the one
reader (fallback `fee − insurance_estimate` for `fee_source='migrated'` rows) and `balance_service`,
`procedure_totals_service`, `print_service.day_totals`, `report_service._ar_components` all use it.

Migration steps fixed for future runs: `s02` (FEEID/PATIENTFEEID/MANCAREFEEID), `s09` (FEETYPE 0/2/3 +
UCR by office membership), `s11` (AMBCODE, tenant_id), `s17` (FEESCHEDULE), `s19` (INSTYPE, INDDEDREM,
INDORTHOREM, legacy_id), `s06` (carrier FEEID → assignment), `s07` (PRINTOFFICEUCR, NETWORKTYPE,
PERVISITCOPAY, ISNONDUPBENEFITS, raw ISPREPAID), new `s32b` (LEDGERINSD → provenance), `s51` (unique
legacy_id, no all-NULL rows), `s52` (TREATPLANINSD exists).

### 3.9 Retired

`procedure_insurance_rules` + its routes (410) and the FE *Insurance* tab; `procedure_codes.default_fee`
as a pricing input and `scripts/seed_procedure_code_rules.py --fee-schedule-id`; the fee half of
`scripts/backfill_office_fee_schedules.py` (its office-keyed hypothesis is disproven: 10–22 % vs 96 %
on UCR); `fee_schedule_service.new_version` re-pointing (kept as "fork", never repoints);
`fee_schedules.ins_plan_id`/`office_id` and `insurance_carriers.fee_id` (read-only → drop);
FE `feeScheduleResolver.ts`, `coverageResolver.ts` (incl. the hard-coded `CDT_CATEGORIES`),
`procedurePricing.ts`, dead `components/patient/AddProcedure.tsx`, the `'CP-50'` literal.

---

## 4. Implementation phases (strictly ordered — never remove a pricing row in the same release that adds its replacement)

### R1 — additive, no behaviour change for the shipped frontend
1. `app/services/fee_vocab.py`; Alembic revision (§3.7) incl. in-revision normalisation; models in
   `app/db/models/codes.py`, `insurance.py`, `identity.py`, `clinical.py`, `treatment.py`, `patients.py`.
2. `scripts/backfill_pricing_hierarchy.py` sections 1–8 (dry-run output reviewed; apply on dev).
3. `pricing_service.py` rewrite + `estimate_service.py` (`coverage_context`, `estimate_lines`,
   `apply_split`) behind `settings.PRICING_ENGINE_V2` (off = today's order, on = the card).
   `apply_split` in `client_legacy` mode in both cases.
4. Setup CRUD classes in `app/services/fee_schedule_service.py` (`FeeScheduleCRUD`,
   `FeeScheduleEntryCRUD`, `FeeScheduleAssignmentCRUD`), `office_setup_service.OfficeCRUD`,
   `PatientCRUD` pointer validation; registry wiring (`crud_class`, `filter_fields` gains `fee_type`/
   `pricing_model`, `hide_soft_deleted=True` on schedules, `write_permissions`).
5. Endpoints on `app/api/v1/fee_schedules.py`: `/metadata`, `/{id}/usage`, `/{id}/entries/bulk`,
   `/{id}/adjust`, `/{id}/retire`, `/{id}/reassign-patients`; `GET /setup/pricing-health`
   (`app/services/pricing_health_service.py`); `GET /insurance-plans/{id}/fee-binding`;
   `POST /pricing/quote`; `date_of_service` on the existing quote/estimate routes;
   `PATCH /offices/{id}/fee-defaults`.
6. `scripts/validate_pricing_against_history.py`: re-price a sample of 2025 charges with
   `date_of_service` and compare to `patient_procedure_fee_provenance`, reporting per-tier match on
   the **reachable** subset (bindings that still exist) and enumerating the unreachable rest.
7. Tests: `tests/test_pricing_hierarchy.py` (one per tier, rank vector, dating incl. pre-2020 floor and
   future-only rows, zero-fee skip, `is_no_charge`, unpriced policies), `tests/test_estimate_models.py`
   (A/B/C, cross-line deductible parity single-vs-batch, cap-before-deductible, both COB formulas,
   `M` slot excluded, NULL-vs-0 remaining), `tests/test_fee_schedule_guardrails.py`,
   `tests/test_pricing_health.py`; update `tests/test_transactions_fee_gaps.py` and
   `tests/test_treatment_plan_edit_gaps.py:337` (use_new_fees must audit).

### R2 — verify (no code)
Run the health report and the parity script on the dev DB with the flag on; fix findings; sign off the
top-200-code fee diff with the fee-schedule owner; decide §6 items.

### R3 — enforce
Flag on by default; delete assignment ids 1–8 (backfill §3.8 step 9); `fee_not_accepted` + strict
override; claim form honours `fees_to_print` (`claim_form_service.py:758`); `treatment_service`
delegates fully; readers switch to `split_of`; drop the `plan_schedule`/`code_default` tiers'
tests.

### R4 — frontend (sibling repo `dentc-frontend`) + cleanup
`procedureEntryService.ts` stops sending money fields and adds `date_of_service`; every charge screen
previews through the estimate/quote endpoints and renders provenance; delete the three client
resolvers and the dead poster; Setup screens per §3.5; regenerate the Orval client; rewrite
`docs/INSURANCE/fee_schedule_setup.md` and the FEE section of
`docs/transactions/transactions_backend_devreport.md` (the "office owns the fee" example is
mis-attributed: 44.00 is CP-40, the patient's list). One release later: drop the deprecated columns
and `procedure_insurance_rules`.

Critical files: `app/services/pricing_service.py`, `app/services/estimate_service.py`,
`app/services/patient_procedure_service.py`, `app/services/treatment_service.py`,
`app/services/fee_schedule_service.py`, `app/api/v1/registry.py`, `app/api/v1/fee_schedules.py`,
the new Alembic revision, `scripts/backfill_pricing_hierarchy.py`,
`denticon_migration/migration/steps/s02|s07|s09|s11|s17|s19|s32|s51|s52`.

---

## 5. Verification

- `pytest` green, including the new suites; the grep test proving one coverage picker.
- Dev DB after R1 backfill (read-only checks): 15/15 offices with a UCR pointer; ~79k patients with a
  list; 13 carrier assignments; `pricing-health` shows no `office_without_ucr`, and `zero_fee_entries`
  / `codes_needing_a_price` are populated work queues rather than surprises.
- Parity script: ≥ 97 % fee match on the reachable subset of 2025 charges, every mismatch attributed
  to a named tier or a retired binding.
- Manual: `GET /patients/{id}/fee?procedure_code=D0120&date_of_service=…` for (a) a CP-40 patient
  (44.00, `patient_schedule`), (b) a patient on a carrier with a fee binding (contracted fee,
  `assignment_carrier`, write-off = UCR − fee), (c) a Medicaid-list patient (26.16, copay model,
  ins 26.16 / pat 0), (d) an uninsured new patient (office default), (e) a code missing from the bound
  list (warning present). Post the same lines and confirm the stored row equals the quote.
- Four-line visit posted as four POSTs equals one four-line `/estimate`.

---

## 6. Decisions (taken 2026-09-12)

1. Unpriced-charge policy for the migrated tenant: **`flag`** — post 0.00 with `fee_source='unpriced'`,
   a warning on the quote and a health-report work queue; each office switches to `refuse` once its
   queue is empty. (Decided.)
2. Copay-list posted fee (Model B): **`patient_fee` if > 0 else `insurance_fee`**; insurance estimate =
   `insurance_fee`; patient portion = fee minus that. Provisional until validated against the
   `LEDGERINSD` rows for legacy schedules 147/148. (Decided.)
3. `ISPREPAID` codes 9 / 2 / 8 / 4 / 3 / 5: store raw in `legacy_prepaid_code`, change nothing until
   decoded — the schedule's `pricing_model` decides arithmetic regardless. (Open, non-blocking.)
4. `procedure_codes` tenancy: defer; add a per-tenant settings overlay in a follow-up. (Open,
   non-blocking.)
5. Scope of the 2026-09-12 session: **document only**. This file is the architecture and flow
   reference the implementation phases in §4 are built against; nothing in §3 is implemented yet.

## Do not do

- Do not make `patients.fee_schedule_id` the top tier (payer bindings override it — proven by the
  carrier lists that never appear on a patient). Do not clone schedule 109 to satisfy a type rule.
- Do not sum `patient_fee + insurance_fee`. Do not let `insurance_fee` beat a coverage %.
- Do not store a percentage anywhere but `insurance_coverage_rules`; do not "wire up"
  `procedure_insurance_rules` as a tenant default.
- Do not pick an entry by newest id; do not clone-and-repoint versions; do not use a future-dated row
  for today's charge.
- Do not put charge-time estimates in `ledger_insurance_details`; do not mass-update historical
  `patient_estimate`; do not re-price on a plain PATCH.
- Do not delete the eight all-NULL assignment rows before the office and patient pointers exist.
- Do not run `scripts/backfill_office_fee_schedules.py --apply` on the fee side, nor
  `seed_procedure_code_rules.py --fee-schedule-id`.
- Do not ship a required-looking Office field that only warns; do not gate only the insurance persona.

---

## R1 progress (2026-09-12)

### Applied to the dev DB

**Alembic `d4f1a9c7b3e2`** (upgrade and downgrade both round-tripped against the real
dev Postgres in a rolled-back transaction before being applied):

- `fee_schedules.pricing_model`, per-tenant `legacy_id` uniqueness, and CHECKs on
  `fee_type` / `pricing_model` / "a copay list must be payer-bound".
- `fee_schedule_entries`: `tenant_id` (closing a cross-tenant read *and write* hole,
  since `CRUDBase` only scopes models that carry one), `is_no_charge`, `created_by` /
  `updated_by` / `updated_at`, `effective_date` NOT NULL, and the uniqueness key
  moved to `(fee_schedule_id, procedure_code, effective_date)`.
- `fee_schedule_assignments`: `updated_at` / `updated_by`, per-tenant `legacy_id`
  uniqueness, and a **partial** unique index on the key tuple.
- `offices.unpriced_charge_policy`; `patient_insurance.legacy_id`;
  `insurance_plans.is_non_dup_benefits` / `legacy_prepaid_code`.
- Provenance on both priced rows (`fee_source`, `fee_effective_date`,
  `fee_override_reason`, `coverage_pct`, `coverage_rule_id`, `estimated_deductible`,
  `sec_insurance_estimate`; items also gained `ucr_fee`), plus the new write-once
  `procedure_fee_provenance` table.
- Six duplicated assignment rows collapsed to one per source row. The ten originals
  are dumped to `scripts/backups/fee_schedule_assignments_pre_d4f1a9c7b3e2.json`,
  because `downgrade()` restores the schema but cannot restore rows. Verified not to
  re-price anything: the practice-wide winner is schedule 26 before and after.

**`scripts/backfill_pricing_hierarchy.py`**, sections `schedules`, `patients`,
`entries`, `plans` — chosen because the *current* engine reads none of those fields,
so applying them changed no live price:

| Result | Count |
|---|---|
| Mislabelled `ucr` lists corrected to `standard` | 10 of 13 |
| Lists left as `ucr` (they are some office's `Office.FEEID`) | 3 |
| Lists detected as `copay` by measurement (plan-pays dominates patient fees) | 2 |
| Patients now carrying their own fee schedule | 79,111 (was 34) |
| Blank source fees separated from real zeros (`0.00` to NULL) | 2,868 |
| Alternate-benefit codes loaded (`D2391A` to `D2140`) | 36 |
| Plans given their real `fees_to_print` / `network_type` / prepaid code | 31,321 |
| Charges re-priced | 0 |

### Deliberately held

- **Office pointers and carrier assignments.** Both feed tiers the *current* resolver
  already walks, so applying them moves live prices: 982 active patients would shift
  to their carrier's contracted list, and 98 codes would go from $0 to a real office
  price. Correct outcomes, but they belong with the flag flip, not with an
  "additive only" release.
- **The `slots` repair.** The dry run proved the shape of the `s19` defect and why a
  partial fix is worse than none: **953 slots the database calls `primary` are
  `INSTYPE='S'` in the source**, so those patients are being priced against what the
  source says is their *secondary* plan. Every one of them has exactly one slot
  (measured), because `ON CONFLICT` discarded the real primary — 836 source slots have
  no row here at all. Demoting the 953 without first inserting the 836 would leave
  those patients with no primary coverage, i.e. self-pay pricing. The repair needs an
  insert-then-rerank pass in one transaction; the script currently only stamps
  `legacy_id` and reports.
- **`insurance_plans.is_prepaid`.** Still untouched. The raw `ISPREPAID` code is now
  preserved in `legacy_prepaid_code` (9 on 15,364 plans, 0 on 8,433, 2 on 7,459, then
  8/4/1/3/5) and nothing prices from it.

### Two findings that changed the design

1. **Dated pricing was forbidden by the database, not merely unimplemented.**
   `fee_schedule_entries` carried a unique on `(fee_schedule_id, procedure_code)` from
   the Denticon `schema.sql`, so a second later-dated fee for a code was rejected.
   That is why Setup's Increase/Decrease overwrites prices in place and loses the old
   one. The revision replaces that key, and a second dated fee was verified to insert.
   `s11`'s upsert target moved with it, or the next migration re-run would fail.
2. **The assignment key-tuple index cannot be total yet.** The two surviving
   practice-wide rows have every key NULL and therefore collide under it, and they may
   not be deleted before offices and patients have pointers. The index is partial,
   covering every row a user can author from now on; the has-a-target CHECK moves to
   R3 with those rows, and `FeeScheduleAssignmentCRUD` refuses new ones from R1.

### Also fixed on the way

- `fee_schedule_service.new_version` cloned entries without a tenant. Once
  `fee_schedule_entries` carried `tenant_id`, `CRUDBase` began scoping the listing and
  a newly created version appeared to have **no prices at all**. Caught by an existing
  test.
- The coverage-rule FK name the repo's naming convention generates is 65 characters
  and Postgres caps identifiers at 63, so it is named explicitly in both the models and
  the revision. Ten pre-existing over-long identifiers remain elsewhere in the schema
  and are a latent trap for any future migration touching those tables.
- The backfill's bulk writes are set-based (`unnest` joined against the target). The
  row-wise first version had not finished 79,077 patient updates in ten minutes; the
  set-based one commits all four sections in 43 seconds.

### Verification run

- Full suite: **1,165 tests, 0 failures**, before and after the model changes.
- `tests/test_pricing_vocabulary.py`: 31 tests pinning the precedence rule and the
  vocabulary against the literals the migration duplicates.
- The precedence rule is tested where it is easy to get backwards: a plan-keyed row
  beats a `{carrier, office}` row, which counting set keys inverts and summing
  per-key weights also inverts.

### Next

R1 step 3: the resolver and the single split engine behind `PRICING_ENGINE_V2`, then
the setup guardrails, the pricing-health report and the parity script. The office and
carrier pointers are applied at the same moment the flag flips, after the parity script
has re-priced 2025 history against `procedure_fee_provenance`.


### R1 step 3 — the resolver and the split engine (behind the flag)

Both engines now exist behind ``settings.PRICING_ENGINE_V2`` (default **off**):

- **``pricing_service.resolve_procedure_fee``** dispatches to ``_resolve_v1``
  (unchanged) or ``_resolve_v2``. v2 walks the precedence card, honours the entry
  in force on the date of service (never a future-dated fee), treats a ``0.00`` on
  a percentage list as "not priced" unless ``is_no_charge``, flags a payer list
  that lacks the code instead of silently falling through, and stamps
  ``fee_source`` / ``fee_effective_date`` / provenance on the result. It shares
  the assignment rank with ``fee_vocab`` — a plan-keyed row beats a
  ``{carrier, office}`` row, which counting keys inverts.
- **``estimate_service``** gains ``coverage_context`` (the single active-dental
  slot picker, replacing three), ``estimate_lines`` (Models A percentage / B copay
  / C self-pay, the annual-max cap applied *before* the deductible is burned, COB
  behind ``include_secondary``, deductible/max consumed across the lines of one
  call), and ``estimate()`` delegates to them under the flag.
- **``estimate_service.apply_split``** (the single write-path pricing/split helper)
  is built and wired into ``PatientProcedureCRUD.create`` / ``.update`` (see the
  next subsection). ``TreatmentPlanItemCRUD`` / ``post_item_to_ledger`` still price
  through ``_price_item`` (fee only, no split) — that is the following increment.

**Tests**: ``test_pricing_hierarchy.py`` (16) + ``test_estimate_models.py`` (14)
cover the tiers, the rank vector, dated entries (in-force / back-dated / future-
only), zero-vs-no-charge, both copay shapes, the cap-before-deductible order, COB
standard vs non-duplication, the medical-slot exclusion, and NULL-vs-0 remaining.
The last hierarchy test pins that with the flag **off** the resolver is unchanged.
Flag-off parity across the wider suite confirmed (the only two failing tests —
``test_office_collections_today`` / ``test_todays_appointment`` — fail identically
on the pre-change baseline; they are the known date-of-"today" flakes).

**A finding**: ``func.current_date()`` (the entry's server default, UTC on SQLite)
and ``office_today`` can differ by a day, so an entry left to default its date can
read as future-dated. Real entries carry an explicit ``effective_date`` (backfill
and bulk endpoints set it); the default is only a safety net.


### R1 step 3b — ``apply_split`` wired into the charge write path

``estimate_service.apply_split(db, data, tenant_id, *, current=None)`` is the one
write-path pricing/split helper, called by ``PatientProcedureCRUD.create`` and
``.update`` (the old ``_price`` staticmethod is gone). The per-line arithmetic was
extracted from ``estimate_lines`` into ``_split_amounts`` so a quoted split and a
posted split share **one** function.

- **Flag off** (production today): byte-identical to the old ``_price`` — a
  fee-less *create* is priced (fee + blank ``fee_schedule_id`` / ``ucr_fee`` only),
  a PATCH is never re-priced, no split column is written. This is what keeps
  shipping the engine dark safe.
- **Flag on**: a create resolves fee + provenance and fills the whole split
  (``insurance_estimate`` / ``sec_insurance_estimate`` / ``patient_estimate`` /
  ``estimated_deductible`` / ``coverage_pct`` / ``coverage_rule_id`` /
  ``fee_source`` / ``fee_effective_date`` / ``ucr_fee``). ``patient_estimate`` is
  **always** server-owned — never read from ``data``. A PATCH re-runs the **split
  only** on a fee change to an **unclaimed** charge (a claimed charge is frozen);
  re-pricing the fee itself stays the explicit reprice action.
- **Override discipline (compatibility window)**: a bare client ``fee`` →
  ``fee_source='client_legacy'`` (honoured, split recomputed, resolver provenance
  recorded); ``fee_override`` (a transient payload flag, consumed before the ORM) →
  ``fee_source='override'`` (off-schedule, no ``fee_schedule_id``, split still
  computed). UCR is recorded even for an override — it is an office-level list,
  independent of what the office chose to charge.
- **Bug fixed in passing**: the resolver returns ``fee_effective_date``
  ISO-formatted (it feeds JSON responses); the charge column is a real ``DATE``, so
  ``apply_split`` coerces it back to a ``date`` before persisting (SQLite rejects
  the string outright).

**Tests**: ``test_apply_split.py`` (13) — flag-off parity (create prices fee only,
PATCH is a no-op), flag-on self-pay / percentage / copay, ``client_legacy`` and
``override``, the PATCH re-split rules (unclaimed re-splits, claimed frozen, no-fee
no-op), a posted charge persisting the split through the real CRUD, and a
single-post == one-line ``/estimate`` parity check.


### R1 step 3c — ``apply_split`` on the treatment-plan-item write path (split-only)

``apply_split`` gains a **split-only** mode (``price_fee=False``, with explicit
``patient_id`` / ``office_id`` because the item row carries neither) wired into
``TreatmentPlanItemCRUD.create`` / ``.update`` via
``treatment_service._fill_item_split``. The reconciliation with PLAN-29:

- The item's **fee / ``fee_schedule_id`` / ``fee_source`` / ``fee_effective_date``
  stay owned by ``_price_item``** — an explicit fee still records the schedule only
  when it is the schedule that would have produced that exact amount ("Fee Schedule
  Used never lies"). Split-only mode never touches them.
- Only the **coverage split** is filled, through the same ``_split_amounts``
  arithmetic the charge path uses, so an item and the charge posted from it can
  never disagree on the split. ``ucr_fee`` is filled too — plan items never got one.
- A ``treatment_plan_item`` has **no ``patient_estimate`` column** (the patient
  portion lives on the ``treatment_plan_insurance_details`` row as ``estimated_pat``);
  split-only mode drops that key so it never reaches the ORM.
- **Flag off**: a no-op — an item's estimate stays owned by the plan-level
  ``re_estimate`` exactly as today (``insurance_estimate`` keeps its 0.00 default,
  the R1 ``coverage_pct`` column stays NULL). **Flag on**: a created line carries a
  provisional per-line split immediately, and a **fee** edit re-splits in place; an
  edit that does not touch the fee leaves the split alone (so it never clobbers a
  ``re_estimate`` result).
- ``post_item_to_ledger`` needs **no** change — it builds the charge and calls
  ``patient_procedure_crud.create``, so the charge's own ``apply_split`` recomputes
  the split at the posting office/date. ``re_estimate`` is still its own loop (it
  nets the deductible across the whole plan); folding it onto ``_split_amounts`` is
  R3 ("treatment_service delegates fully"), and it already shares ``match_coverage_rule``.

**Tests**: ``test_treatment_item_split.py`` (5) — flag-off no-op, flag-on
create-fills-split, self-pay, fee-change re-splits, non-fee edit leaves the split.


### R1 step 4 — Setup write guardrails (§3.6)

The three fee-side ``*CRUD`` classes in ``fee_schedule_service.py``, wired into the
registry (``crud_class``), plus the patient pointer check. **These fire on every
write regardless of ``PRICING_ENGINE_V2``** — they are data-integrity rules for the
three maintainers, not pricing behaviour — and each validator fires only when its
field is present and *changed*, so a legacy row stays editable.

- **``FeeScheduleAssignmentCRUD``** — an assignment must name a payer or person
  (``has_assignment_target``): a **scope-only** row (office / office group) is a
  422 ``assignment_needs_target``, because office-wide defaults have exactly one
  home (Office Setup) — the eight all-NULL migrated rows are what taught this. The
  bound schedule must be a live schedule of this tenant (422
  ``assignment_schedule_invalid`` for inactive / foreign). The target key tuple must
  be unique — a second binding of the same target (even to a different schedule) is
  409 ``assignment_duplicate_target`` (NULL-aware, self-excluded); this backs up the
  Postgres partial unique index for SQLite and gives a coded 409 instead of a raw
  constraint error. Fires on a *move* (create, or a PATCH that changes a key).
- **``FeeScheduleEntryCRUD``** — a negative ``patient_fee`` / ``insurance_fee`` is 422
  ``fee_entry_negative``; a **positive Plan Pays on a percentage list** is 422
  ``insurance_fee_not_allowed`` (allowed on a copay list; a zero/blank is always fine
  so a stray legacy value can be cleared).
- **``FeeScheduleCRUD``** — ``fee_type`` / ``pricing_model`` are canonicalised on
  write (``"office"`` → ``standard``, ``"UCR"`` → ``ucr``); a copay model on a
  non-payer type is 422 ``pricing_model_requires_payer_type`` (the SQLite twin of the
  Postgres ``ck_fee_schedules_pricing_model_needs_payer`` CHECK); retiring a schedule
  (soft-delete, or ``is_active=false``) that is still referenced by an assignment, an
  office pointer or a patient is 409 ``fee_schedule_in_use`` (``referenced_by`` names
  which). Registry also gains ``hide_soft_deleted=True`` and the
  ``fee_type`` / ``pricing_model`` filter params.
- **``PatientCRUD``** — ``patients.fee_schedule_id`` (the default-input pricing tier)
  must point at a live schedule of this tenant when set/changed (422
  ``patient_schedule_invalid``); clearing it or a PATCH that never touches it is free.

**Deferred within step 4**: ``OfficeCRUD`` fee-default pointer validation rides with
the ``PATCH /offices/{id}/fee-defaults`` endpoint (step 5); ``write_permissions`` wait
on ``scripts/seed_permissions.py`` seeding the codes (an ungated user would otherwise
be the only gate, and admins already pass).

**Tests**: ``test_fee_schedule_guardrails.py`` (12) + two in ``test_fee_schedule_setup.py``
(scope-only refused; the FEE-3 filter test now carries a carrier). All existing
fee-side tests that build rows by direct ORM insert are unaffected — the guards are
on the CRUD (API) path.


### R1 step 5 — Setup / pricing endpoints

The routing surface the Setup screens and the charge screens call. All read-only
except the office config and retire.

- **``GET /fee-schedules/metadata``** — ``fee_vocab.metadata()`` verbatim (fee types,
  pricing models, fee sources, assignment keys, the ``precedence`` card, warning /
  error tables), so the Setup landing page renders the hierarchy from the server.
- **``GET /fee-schedules/{id}/usage``** — reference counts (assignments / offices /
  patients / entries) + ``can_retire``; the "Where used" panel and the retire guard
  read the same ``_reference_counts``.
- **``POST /fee-schedules/{id}/retire``** — the ``is_active=false`` counterpart of
  ``/restore``, refused (409 ``fee_schedule_in_use``) while referenced. ``is_active``
  is managed by ``/retire`` + ``/restore`` rather than the generic update.
- **``PATCH /offices/{id}/fee-defaults``** (``office_setup_service.set_fee_defaults``) —
  the office UCR list, default patient list and ``unpriced_charge_policy``; a schedule
  pointer must be a live schedule of this tenant (422 ``office_schedule_invalid``; null
  clears it), an unknown policy is 422 ``invalid_unpriced_policy``. ``exclude_unset``
  distinguishes "not sent" from "sent as null". (This is the plan's ``OfficeCRUD`` role,
  as a focused service function on the office-setup module rather than a CRUD subclass.)
- **``GET /insurance-plans/{id}/fee-binding``** (``pricing_service.fee_binding``) — the
  schedule bound to a plan through the **payer tiers only** (plan-keyed, else
  carrier-keyed with no plan key), ranked as the resolver ranks them; ``bound=false``
  when no payer assignment names the plan (pricing then falls through to patient/office
  tiers, which is not the plan's own binding). Read-only; the wizard deep-links to
  Assignments and never picks a schedule.
- **``POST /pricing/quote``** — with a ``patient_id`` it is the full estimate (fee +
  split, via ``estimate_service.estimate``); with none it is a fee-only quote
  (``pricing_service.quote``) for the office/provider/plan/date context, so the
  scheduler / a template / add-patient can price before a patient or a DOS exists.
- **``GET /setup/pricing-health``** (``pricing_health_service.report``) — coded findings,
  each naming the owning screen and a ``severity``: ``office_without_ucr`` /
  ``office_without_default``, ``assignment_never_reachable`` (the scope-only legacy
  rows) / ``assignment_to_inactive_schedule``, ``insurance_fee_on_percentage_schedule``
  / ``zero_fee_entries``, ``code_without_coverage_category``. The volume-ranked findings
  (a bound schedule missing a high-traffic code, ``client_legacy`` / ``unpriced`` charges
  actually posted) are a later addition that scans charge history.
- **``date_of_service``** added to ``GET /patients/{id}/fee`` and
  ``POST /patients/{id}/estimate`` (passed to the v2 resolver / engine).

**Bulk write ops** (all upsert into the *same* schedule — the "New Effective Date"
workflow — never a clone-and-repoint, because the resolver already picks the entry
in force on the date of service):

- **``PUT /fee-schedules/{id}/entries/bulk``** — upsert many entries in one
  transaction, keyed on ``(schedule, code, effective_date)``; a body-level
  ``effective_date`` (or a per-entry one) writes a new dated set. Each amount runs
  the shared ``_validate_entry_amounts`` (no negative, Plan Pays only on a copay
  list). Returns ``created`` / ``updated``.
- **``POST /fee-schedules/{id}/adjust``** — write a new dated set adjusted from each
  code's most recent entry (``mode`` ``percent`` / ``amount``, floored at 0); a bad
  mode is 422 ``invalid_adjust_mode``. History and current prices are untouched
  until ``effective_date``.
- **``POST /fee-schedules/{id}/reassign-patients``** — move patients off a schedule
  onto another (Change Patient Fee Schedule — what makes retiring a list possible);
  the target must be a live schedule of this tenant (422 ``patient_schedule_invalid``),
  the source need not be. Audited as one mutation by the middleware.

**Tests**: ``test_pricing_endpoints.py`` (18 — the read/config/quote surface plus the
three bulk ops incl. the guard on bulk, the dated-percentage adjust, and
reassign-then-retire).


### R1 step 6 — the parity script

``scripts/validate_pricing_against_history.py`` re-prices a sample of a year's
non-void charges through the v2 engine (flag forced on) at each charge's own
date-of-service and compares the result to the fee actually posted. Read-only
(the session is rolled back). ``--sample N`` (default 2000, a reproducible spread
via ``md5(id)``), ``--all``, ``--year``, ``--tenant``, and ``--against
stored_fee|provenance``.

**Compares to the stored fee, not ``procedure_fee_provenance``**, because that
table is **empty** on the dev DB (the ``LEDGERINSD`` provenance backfill, section 8,
was never run) — the charge's own ``fee`` *is* the historical posted amount.
``--against provenance`` switches the reference once that table is loaded. A charge
posted at ``$0`` (19 % of the migrated year — bundled / written-off lines) is
reported in its own ``posted at $0`` bucket, never counted as a mismatch, since it
is not a test of whether v2 reproduces a *priced* fee.

**Result on the dev DB (2000-charge spread, 2025)** — validates the engine and
sizes the held backfill:

- v2 **priced 90.3 %** of the sample; **9.7 % unreachable**, of which **169 =
  ``no_carrier_binding``** (the office/carrier backfill sections R1 holds), 21 a code
  missing on the reachable list, 4 a patient with no list.
- On the priced-and-comparable subset the **patient-list tier matched 84.7 %** —
  which is the offline-proven number (the patient's own ``FEESCHEDULE`` explains
  85.2 % directly; the rest are the carrier lists 110–122 that never sit on a
  patient). So the engine reproduces exactly the patient-list explanatory power the
  §2 analysis predicted, and the parity script attributes the remaining gap to the
  deferred payer/office bindings.

The §5 target (>= 97 % on the reachable subset) is therefore an **R2** outcome —
reached once the office/carrier backfill sections are applied and the flag is ready
to flip — not an R1 one; step 6 delivers the measurement that gates that decision.


### R2 — bindings applied, and what the parity actually shows (2026-09-13)

Applied to the dev DB: **offices** (15 UCR + default pointers) and **carriers** (13
carrier-keyed assignments). One bug fixed on the way: the backfill derived a carrier
assignment's ``legacy_id`` from the *schedule* (``carrier:{fee_id}``), but several
carriers bind the same schedule (236/248/259 -> fee_id 110), colliding on
``uq_fee_schedule_assignments_tenant_legacy``; it is now ``carrier:{carrier_id}``
(idempotency was already the ``(tenant, carrier)`` set, not the legacy_id).

**The parity did NOT reach 97 %** — it moved 84.7 % -> **84.0 %** overall
(unreachable 9.7 % -> 7.0 %). By tier: patient_schedule 85.1 %, office_default
67.6 %, **assignment_carrier 26.3 %**, office_ucr 100 %.

The reason, established from the posted-fee distributions: **the posted fee is
always a real schedule fee, but charges of the same code posted at *different*
schedules** — D1110 posts at 88 (CP-40), 95 (CP-50), 250 (UCR list), 49.45 and 55
across different charges; D0120 at 145 / 44 / 47 / 25.41 / 28. So reproducing history
is not "apply the bindings" — it is "pick, per charge, the *same* schedule Denticon
used", and the only per-charge record of that is ``LEDGERINSD.FEEID``, which was
never migrated (``procedure_fee_provenance`` is empty). v2's precedence card
reconstructs that choice and lands on a **different but equally legitimate** schedule
~16 % of the time; the carrier tier scores worst (26 %) because a carrier's single
``fee_id`` default is a poor proxy for which list actually priced each of its charges.

**Conclusion — do not flip the flag (R3) on this.** The 99.66 % in §2 was
``AMOUNT == FeeScheD[LEDGERINSD.FEEID][code]`` — a statement that the posted amount
matches *the schedule Denticon recorded per charge*, **not** that the precedence
card re-derives that schedule. Closing the gap needs one of:

1. **Load ``LEDGERINSD`` provenance** (backfill section 8, ~1.45M rows) and validate
   ``--against provenance`` — the definitive test of whether the precedence card
   picks the schedule Denticon actually used, and the input to tuning the card.
2. **A fee-schedule-owner decision** on the precedence ordering itself — in
   particular whether these offices post at UCR and write off to the contracted
   allowed amount (an adjustment) rather than posting at the contracted fee, which
   would change where UCR sits in the card for them.

Go-forward correctness is unaffected either way — v2 applies the documented card to
new charges; this is purely about how faithfully it reproduces migrated history, and
84 % with the reason understood is an honest R2 signal, not a green light.

**Provenance loaded, and the definitive ``--against provenance`` number (2026-09-13).**
``scripts/load_procedure_fee_provenance.py`` loaded all **63,050** 2025 charges'
``LEDGERINSD`` rows into ``procedure_fee_provenance`` (every 2025 charge has one;
53,807 carry a ``FEEID`` that maps to a live schedule, ~9k recorded ``FEEID='0'``).
The loader reads the maps, releases the connection for the multi-minute file scan,
then writes on a fresh session via ``execute_values`` — the idle SSL connection
dropped otherwise. The parity script's ``--against provenance`` mode now measures
**schedule-match**: did v2's precedence card pick the *same schedule Denticon
recorded on that charge*? (``PRIMCONTRACTEDAMT`` is blank almost everywhere, so the
schedule is the signal, not the amount.)

**Result (2000-charge spread): schedule-match 84.7 %** (1338/1579 comparable) —
agreeing with the 84.0 % fee-match, so the engine is internally consistent. The
divergence is fully attributed:

- **``patient_schedule`` where Denticon used ``UCR -Excel Dental``** (~100 incl.
  ``office_default``): the patient is on a contracted list but the office **posted at
  UCR**, not the contracted fee — the UCR-vs-contracted posting question, now
  quantified.
- **``patient_schedule`` where Denticon used a *different* contracted list**
  (CP-40 vs CP-50, ~118): the patient's *current* ``fee_schedule_id`` is not the list
  that priced the charge then — the assignment changed over time.

**This is the ceiling, and it is not a defect.** The 15 % gap is **point-in-time
state** — which list the patient was on at post time, whether the office posted at
UCR — that the precedence card applied to *current* data cannot reconstruct. No
binding backfill closes it, because the posted fee is a *snapshot*. That is exactly
why history keeps ``fee_source='migrated'`` and the provenance table exists: posted
charges are never re-priced. The **>= 97 % target is therefore unreachable by the
precedence card on historical charges and is the wrong gate for R3** — v2 prices
*new* charges by the card (correct by construction), and the migrated ledger is left
as posted. R3 should be gated on a fee-schedule-owner sign-off of the card's ordering
(the UCR-vs-contracted posting behaviour per office), not on a historical-match
percentage.
