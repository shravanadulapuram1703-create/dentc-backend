# Edit Insurance Plan from the patient screen — Backend Dev Report

| | |
|---|---|
| **Screen** | Patient → Insurance → any slot (Primary/Secondary/Third/Fourth Dental, Primary/Secondary Medical) → **Edit Plan** (left rail beside PLAN ID, and the footer of View Plan) |
| **Frontend** | `src/features/patient-insurance/EditPlanModal.tsx` (host) over the shared `src/components/setup/insurance/plan-details/InsuranceDetailsWizard.tsx`; usage counts in `patientInsuranceService.loadPlanUsage` |
| **Backend resources touched** | `insurance_plans` (PATCH), `insurance_coverage_rules` (diff POST/PATCH/DELETE), `patient_insurance` + `insurance_claims` (read, counts), `audit_logs` (read) |
| **Verified against** | running backend `127.0.0.1:8000`, tenant 1, 2026-09-11 evening — plan #58062 (1 patient) edited end-to-end from the UI and reverted; plan #11423 (2 patients) taken to the confirmation and cancelled (no write); probes on QA plan #89895 |
| **Open gaps** | 9 (EDIT-PLAN-1 … EDIT-PLAN-9) |

Until now the patient screen only offered **View Plan** and sent staff to Setup → Insurance →
Plans to change anything. Editing is a core legacy function (the Denticon patient insurance
window opens INSURANCE DETAILS editable), so it is now available in place. Because one
`insurance_plans` row is shared by every patient linked to it, the frontend wraps the edit in
an impact banner and a confirmation. Several of the safeguards a shared master-data edit
needs can only come from the backend; they are listed in §2.

---

## 1. What the frontend does today

### Flow

1. **Edit Plan** opens the same 4-step INSURANCE DETAILS wizard Setup uses (PLAN · BENEFITS ·
   COVERAGE & LIMITATIONS · FREQ LIMITATION CODE GRP), in edit mode, for the slot's plan.
2. A **shared-plan banner** above the steps shows *how many patients* and *how many claims*
   sit on the plan, with **Open in Setup** for the full grid context.
3. **FINISH** runs the usual validation and the duplicate-group check, then — when more than
   this one patient is linked (or the count is unknown) — a confirmation
   *"Update shared plan? … Saving changes the plan for all of them."* Nothing is written
   before **Update for all N patients**; **Back** returns to the form.
4. On success the slot screen re-reads plan + carrier + employer so the read-only Ind./Fam.
   benefit columns and the CARRIER / EMPLOYER blocks show the saved values. The slot's own
   **Group #** (stored on the subscriber, see EDIT-PLAN-4) follows the plan only when it was
   blank or still equal to the plan's previous group number.

### Calls made

| Step | Call | Measured |
|---|---|---|
| Banner — patients on plan | `GET /patient-insurance?ins_plan_id=&is_active=true&size=1` → `meta.total` | < 1 s |
| Banner — claims on plan | `GET /insurance-claims?ins_plan_id=&is_active=true&size=1` → `meta.total` | **3.9 s** |
| Load | `GET /insurance-plans/{id}`, `GET /insurance-coverage-rules?ins_plan_id=` (paged 200), definitions lookups | 1–3 s (40 s once while another request hung — EDIT-PLAN-7) |
| Duplicate check on Finish | `GET /insurance-plans?group_number=&is_active=true` (PLAN-DTL-7) | ~10 s in the UI run |
| Save | `PATCH /insurance-plans/{id}` then per-row coverage diff | PATCH **1.3 s warm / 7.5 s cold** |

### Now server-side (was browser-stored)

The nine legacy PLAN/BENEFITS fields of PLAN-DTL-1 (`fees_to_print`, `claim_option`,
`form_to_print`, `reporting_subtype`, `network_type`, `noa_only`, `per_visit_copay`,
`lifetime_ortho_benefits`, `plan_notes`) **are columns on `insurance_plans` now** and the
wizard reads/writes them through the API (verified: PATCH persists, GET returns them). The
old localStorage copy is read once as a fallback when the server row is still empty and is
removed after the first successful save. With editing reachable from every patient screen, a
per-browser copy would have been a correctness bug, so this was switched in the same change.

### Delivered backend items this feature relies on (do not re-open)

- `InsurancePlanRead.updated_at` / `updated_by` / `updated_by_name` are populated by PATCH
  (INS-PT-8 and PLAN-DTL-9 are **delivered for plans**; `modified_on` / `modified_by` stay null).
- `audit_logs` records plan PATCHes with a `before` / `after` field diff
  (`resource_type = "insurance-plans"`, `resource_id = <plan id>`).
- `ins_plan_id` filters on `GET /patient-insurance` and `GET /insurance-claims`.
- `GET /insurance-plans/group-availability` (2.2 s) — a lighter duplicate check than the list
  filter; the wizard still uses the list filter (frontend follow-up).

---

## 2. Gaps

Priority reflects impact on data integrity and on users, not implementation effort.

### 🔴 High — a shared-plan edit is unsafe or its blast radius is unknown

- **EDIT-PLAN-1 — No optimistic concurrency on `PATCH /insurance-plans/{id}` (or on coverage
  rules).** Last writer wins. The client reads the plan when the wizard opens and writes
  minutes later; nothing lets it say "only if unchanged since `updated_at` X". With Edit Plan
  reachable from every patient screen *and* Setup, two users editing the same shared plan
  is a realistic case, and the loser's benefit or coverage changes vanish silently.
  **Wanted:** accept a precondition — `If-Unmodified-Since` / `If-Match` (ETag from
  `updated_at`) or an `expected_updated_at` body field — and return **409/412** with the current
  row so the UI can show a "changed by X at Y, reload?" prompt. Same for the coverage-rule
  bulk PUT.

- **EDIT-PLAN-2 — No plan usage / impact endpoint.** The banner's two counts are list totals
  fetched with `size=1`, and they are incomplete: *patients* counts active `patient_insurance`
  links (a patient with the plan in two slots counts twice), *claims* is every active claim
  regardless of status, and treatment-plan items estimated against the plan, subscribers and
  appointments are not represented at all. The claims count alone costs 3.9 s.
  **Wanted:** `GET /insurance-plans/{id}/usage` →
  `{ patients (distinct), subscribers, claims_open, claims_total, treatment_plan_items_pending, last_used_at }`
  in one cheap call.

- **EDIT-PLAN-3 — No re-estimate cascade after a coverage change.** Coverage %, deductibles
  and frequency rules drive the patient/insurance split. After an edit, existing treatment-plan
  estimates and unsubmitted claim estimates keep the old numbers. Only per-object calls exist
  (`POST /treatment-plans/{plan_id}/re-estimate`, `POST /insurance-claims/{claim_id}/recalculate`),
  and there is no way to even *list* the affected treatment plans (`GET /treatment-plans`
  filters by `patient_id` / `office_id` / `status` only).
  **Wanted:** either `POST /insurance-plans/{id}/re-estimate` (async job, returns counts) or an
  `ins_plan_id` filter on `/treatment-plans` so the frontend can offer "re-estimate N pending
  treatment plans" after Finish.

### 🟠 Medium — works, but with a gap the backend should close

- **EDIT-PLAN-4 — `insurance_subscribers.group_number` is a denormalised copy that does not
  follow the plan.** The patient screen's Group # is the subscriber's column (verified:
  subscriber 64644 stores `"3328213"` independently of plan 58062). Changing the plan's group
  number in Edit Plan leaves every subscriber on the old value; the frontend only nudges the
  *current* slot's value (and only when it still matched) and asks the user to Save.
  **Wanted:** decide the source of truth — either cascade plan → subscribers on PATCH, or
  derive the subscriber value on read, or document that the subscriber column is authoritative
  (in which case the plan column should not be editable).

- **EDIT-PLAN-5 — The current user's effective permissions are not exposed, so Edit Plan
  cannot be gated.** `GET /permissions` lists 529 codes including
  `patient_insurance_plan_information_screen_full_control` / `_view_only`,
  `setup_insurance_plans_screen_full_control` / `_view_only` and
  `setup_insurance_plans_screen_edit_locked_plan`, but `GET /auth/me-full` returns only
  `user / tenant / offices / last_patient_id / provider_id` and `UserRead.role` is a coarse
  role. There is also no `is_locked` on `InsurancePlanRead` although a "locked plan"
  permission exists. Today every user who can open the slot screen sees Edit Plan, and
  whether PATCH is refused for a view-only role is unknown (only super-admin was tested).
  **Wanted:** `permissions: string[]` (effective codes) on `me-full`, server-side enforcement
  of the plan permissions on POST/PATCH/DELETE, and an `is_locked` column honoured by
  `setup_insurance_plans_screen_edit_locked_plan`.

- **EDIT-PLAN-6 — Plan change history is recorded but not consumable per plan.**
  `GET /audit-logs?resource_type=insurance-plans&resource_id={id}` returns the PATCH with a
  field diff (good), but coverage-rule and frequency-group edits log under their own resource
  types keyed by *rule id*, so reconstructing "what changed on plan X" needs one lookup per
  rule, and `AuditLogRead` carries `user_id` only (no name).
  **Wanted:** `GET /insurance-plans/{id}/history` aggregating plan + coverage-rule +
  frequency-group changes with user names, so the wizard can show a "Modified by / on"
  strip and a change log like Medical History has.

- **EDIT-PLAN-7 — Latency on the edit path.** Measured on the dev backend:
  `PATCH /insurance-plans/{id}` 7.5 s cold / 1.3 s warm; the Finish duplicate check
  (`GET /insurance-plans?group_number=` — PLAN-DTL-7) ~10 s; `GET /insurance-claims?ins_plan_id=`
  3.9 s; and during the run a single slow request (`GET /patients/83892`, > 90 s, never
  returned) made an unrelated `GET /insurance-plans/58062` take 40 s — which looks like a
  synchronous DB call blocking the single async worker.
  **Wanted:** index on `insurance_plans (tenant_id, group_number)` and on
  `insurance_claims (tenant_id, ins_plan_id)`; investigate the request that blocks the worker.
  (Frontend follow-up: switch the duplicate check to `group-availability`.)

### 🟡 Low — hygiene

- **EDIT-PLAN-8 — `PATCH /insurance-plans/{id}` silently drops unknown keys.** A body with
  `bogus_field` returned 200 and ignored it. A client-side typo or a stale field name would
  fail silently (same family as the procedure-codes landmine).
  **Wanted:** reject unknown fields with 422 (`extra="forbid"` on the update schema).

- **EDIT-PLAN-9 — Migrated plans hold NULL in the nine new columns, so the first edit writes
  legacy defaults.** The wizard shows the legacy defaults for NULL (`fees_to_print=office_ucr`,
  `claim_option=submit`, `form_to_print=ADA2024`, `network_type=unknown`) and Finish persists
  them; the audit diff then shows four "changes" the user did not make. `lifetime_ortho_benefits`
  defaults to **false** server-side while the legacy dialog defaults to **true**.
  **Wanted:** backfill the columns with the legacy defaults in a migration (or declare NULL ≡
  default in the API docs), and confirm the intended default for `lifetime_ortho_benefits`.

---

## 3. Behaviour notes

- Edit Plan is intentionally the **same component** as Setup → Plans, so validation, the
  duplicate-group dialog ("Use this plan / Back to form / Save anyway"), Copy From Existing and
  the diff-save of coverage rows behave identically wherever a plan is edited.
- The confirmation is skipped when the plan is linked to this patient only; an unknown count
  (either list call failed) is treated as "possibly many" and asks.
- **Back** on the confirmation writes nothing (verified: no PATCH issued for plan 11423).
- View Plan stays read-only and now offers **Edit Plan** in its footer next to Open in Setup.
- Related reports: `docs/patient-insurance/patient_insurance_backend_devreport.md` (INS-PT-*),
  `docs/insurance/insurance_plan_details_backend_devreport.md` (PLAN-DTL-*).
