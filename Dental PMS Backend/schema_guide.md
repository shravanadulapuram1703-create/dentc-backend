# Dental PMS — Schema Simplification Guide

## Overview

Your original schema had **60+ tables** designed for a fully scaled, multi-tenant dental SaaS. This simplified version cuts that down to **17 tables** that cover every core workflow needed to ship a working application. Everything removed is documented below with a clear path to add it back.

---

## What You Can Build With 17 Tables

| Feature | Tables Used |
|---|---|
| Login & multi-clinic access | `tenants`, `users`, `refresh_tokens`, `user_offices` |
| Office setup & scheduling config | `offices`, `providers`, `operatories` |
| Patient chart | `patients`, `patient_insurance`, `patient_alerts` |
| Appointment calendar | `appointments` |
| Treatment planning | `treatment_plans`, `treatment_plan_items` |
| Clinical record (completed work) | `patient_procedures`, `procedure_codes` |
| Billing basics | `patient_payments`, `insurance_claims` |

---

## Simplification Decisions

### 1. Patient: from 7 tables → 1 table (+ 2 small ones)

**What was removed:** `patient_addresses`, `patient_contact_info`, `patient_balances`, `patient_clinical_info`, `patient_account_members`, `responsible_parties`

**What was done instead:** Contact info, address, and key clinical dates (`first_visit`, `last_visit`, `next_recall`) are columns on the `patients` table. This is perfectly fine for a single-address, single-contact patient record — which covers 95% of cases.

**When to add back:**
- `patient_addresses` — when you need multiple addresses per patient (home + work + mailing)
- `patient_contact_info` — when you need multiple contacts (patient + emergency contact + guardian as separate rows)
- `patient_balances` — when you have a high transaction volume and need a cached/precomputed balance; for now, compute `SUM(fees) - SUM(payments)` on the fly
- `patient_account_members` — when you need family billing (one account, multiple members)
- `responsible_parties` — when the payer is different from the patient (e.g., parent pays for child)

---

### 2. Users & Permissions: from 10 tables → 1 field

**What was removed:** `roles`, `permissions`, `role_permissions`, `user_permissions`, `user_roles`, `office_roles`, `office_permissions`, `office_role_permissions`, `groups`, `user_group_memberships`

**What was done instead:** A single `role` varchar column on the `users` table with values like `admin`, `provider`, `front_desk`, `staff`. Enforce this in your application/API middleware.

**When to add back:**
- Add `roles` + `user_roles` when you need custom roles per tenant (e.g., "Office Manager" with specific permissions)
- Add `permissions` + `role_permissions` when you need fine-grained feature flags (e.g., "can_void_payments")
- Add `groups` + `user_group_memberships` when you need org-unit-level access control

---

### 3. Ledger system: removed entirely

**What was removed:** `patient_ledger_entries`, `patient_payment_applications`, `patient_adjustment_applications`, `patient_adjustments`, `adjustment_codes`, `payment_codes`, `transaction_types`

**What was done instead:** `patient_payments` records money in. `patient_procedures` records charges. `insurance_claims` tracks what was sent to insurance. Patient balance = query `SUM(procedures.fee) - SUM(payments.amount)` per patient.

**When to add back:** When you need a full audit trail of every balance change (required for accounting, AR reconciliation, and EOB matching). At that point, introduce a `ledger_entries` table as a log of all debits/credits, and `payment_applications` to link payments to specific procedures.

---

### 4. Office configuration: from 12 tables → inline columns

**What was removed:** `office_advanced_settings`, `office_collections`, `office_holidays`, `office_imaging_systems`, `office_integrations`, `office_other_info`, `office_patient_urls`, `office_payment_methods`, `office_schedules`, `office_smart_assist`, `office_smart_assist_items`, `office_statements`, `office_transworld`

**What was done instead:** Scheduler hours and slot interval are columns on `offices`. Everything else is deferred.

**When to add back:** Add these as you build the features that need them — e.g., add `office_schedules` when you build the weekly schedule editor, add `office_integrations` when you integrate with EDI or an imaging system.

---

### 5. Treatment plan phases: 3 tables → 2 tables

**What was removed:** The `treatment_plan_phases` middle tier

**What was done instead:** `treatment_plan_items` has a `priority` integer. Items with priority 1 are "Phase 1", priority 2 are "Phase 2", etc. This is enough for the UI to render phases without an extra join.

**When to add back:** When you need named phases with descriptions, start/end dates, or individual phase status tracking, add a `treatment_plan_phases` table back and foreign-key `treatment_plan_items.phase_id` to it.

---

### 6. Reference / lookup tables: removed

**What was removed:** `genders`, `marital_statuses`, `titles`, `pronouns`, `states`, `contact_preferences`, `referral_types`, `responsible_party_relationships`, `patient_types`, `appointment_types`, `appointment_statuses`, `procedure_categories`, `claim_statuses`

**What was done instead:** Plain `varchar` fields. Values are validated in your application layer (not the database).

**When to add back:** When users need to customize these lists in a UI (e.g., "add a new referral type"), pull them into lookup tables. Until then, keep them as enums in your application code — they're easier to change.

---

### 7. Audit logs, impersonation, IP rules: deferred

**What was removed:** `audit_logs`, `impersonation_sessions`, `ip_addresses`, `user_ip_rules`

**When to add back:** Audit logs should be added before you go to production with real patient data. They're critical for HIPAA compliance. Add `audit_logs` as a append-only table (no updates/deletes) that captures actor, action, resource, and timestamp for every write operation.

---

### 8. Duplicate and backup tables: removed

**Removed:** `refresh_tokens` (old), `scheduler_operatories_backup`, `procedure_codes_archive`, `refresh_tokens_2` renamed to `refresh_tokens`, `scheduler_providers` and `office_providers` merged into `providers`, `tenant_1.fee_schedules` and `public.fee_schedules` resolved.

---

## Scaling Roadmap

```
Phase 1 — MVP (now)
  17 tables
  Simple role field on users
  Patient info inline
  Basic payments + claims
  Treatment plan items (no phases)

Phase 2 — Production Hardening
  + audit_logs (HIPAA)
  + patient_balances (cached balance)
  + patient_addresses (multi-address)
  + office_schedules (weekly schedule editor)
  + office_holidays
  + treatment_plan_phases (named phases)
  + payment_applications (link payment → procedure)

Phase 3 — Advanced Billing
  + patient_ledger_entries (double-entry ledger)
  + patient_adjustments + adjustment_codes
  + claim_attachments, claim_events (full EDI workflow)
  + payment_codes, transaction_types

Phase 4 — Enterprise / Multi-Office
  + roles + permissions + role_permissions (custom RBAC)
  + groups + user_group_memberships
  + office_integrations (EDI, imaging)
  + ip_addresses + user_ip_rules
  + impersonation_sessions
  + time_clock_entries
```

---

## Key Design Notes

**IDs:** The original schema mixed `serial` (int), `varchar(50)` (nanoid/uuid), and `uuid` types. This simplified schema uses `serial` (int) for tenant-anchored tables (tenants, users, offices, patients) and `varchar(50)` for clinical records (appointments, procedures, plans) where you may want to generate IDs in the app layer. Keep this consistent — pick one pattern and stick with it.

**tenant_id propagation:** Every table that holds patient or clinical data has `tenant_id` (via patient → tenant_id or directly). When you add multi-schema tenancy later, you can move the `tenant_1.*` tables into per-tenant schemas. For now, `tenant_id` as a column is sufficient.

**No `tenant_1` schema prefix:** In this simplified version, everything lives in the `public` schema. The schema-per-tenant approach from your original design is a solid scalability pattern but adds complexity to every query and migration. Revisit when you have > 10 tenants with strong data isolation requirements.
