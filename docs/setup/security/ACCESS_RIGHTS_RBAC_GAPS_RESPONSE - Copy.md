# Backend Response — RBAC Gaps From Frontend Wiring

> **To:** Frontend
> **From:** DentC Backend
> **Date:** 2026-09-13
> **Re:** [`ACCESS_RIGHTS_RBAC_GAPS.md`](./ACCESS_RIGHTS_RBAC_GAPS.md)
> **Status:** RBAC-1 · RBAC-2 · RBAC-3 · RBAC-4 · RBAC-5 — **fixed**. RBAC-6 —
> **phase-1 shipped** (mechanism + a well-mapped set), remainder itemised below.

---

## Summary

| ID | Fix |
|---|---|
| RBAC-1 | New `require_read_access(*codes)` read gate — a screen's `*_view_only`/`*_full_control` right now grants read of that screen's data (full-access roles still bypass). |
| RBAC-2 | `GET /user-groups/{id}/rights` reads for a holder of `setup_security_groups_screen_view_only`/`_full_control`. |
| RBAC-3 | `GET /users` + `GET /users/{id}` read for a holder of `setup_security_users_screen_view_only`/`_full_control`; user **writes** stay admin-only. |
| RBAC-4 | `transactions_edit_fee_ledger` enforced, **field-scoped** — only a `PATCH /patient-procedures/{id}` that actually **moves the fee** is gated. |
| RBAC-5 | `DELETE /patient-procedures/{id}` gated on `transactions_delete_procedure`. |
| RBAC-6 | New per-verb `create_permissions`/`update_permissions` on the CRUD factory; gated: patient-payment post, insurance-payment post, perio charting writes, treatment-plan delete. Rest itemised. |

---

## RBAC-1 — read gating (root cause)

The read rule you asked for is a new dependency,
[`require_read_access(*codes)`](../../../app/api/deps.py):

> a read passes when the caller **holds** one of the screen's `*_view_only` /
> `*_full_control` codes, **or** is a full-access role (`admin`/`super_admin`).

It is deliberately **not** `require_permission` (the write gate): an **ungated**
non-admin does *not* pass a `require_read_access` endpoint, because these endpoints
were admin-only and an ungated user was already refused — so granting the view
right is the *only* thing that opens them, exactly as the screen expects. (Writes
keep the B2 ungated-fallthrough; reads that were public generic-CRUD lists were
never gated and still aren't.)

RBAC-2 and RBAC-3 are the two concrete role-gated reads; both now use this gate.
Other historically admin-only reads (e.g. `GET /audit-logs`) are intentionally
admin-only and were left as-is — tell us any screen whose data a view right should
open and it's a one-line `require_read_access` swap.

## RBAC-2 — `GET /user-groups/{id}/rights`

Was `require_roles("admin")`; now `require_read_access("setup_security_groups_screen_view_only",
"setup_security_groups_screen_full_control")`. `qa_viewonly` can now open the rights
panel for any group.

## RBAC-3 — `GET /users`

The whole `/users` router was `require_roles("admin")`, so a `staff` view-only user
was refused (the FE rendered that 403 as an empty grid). The router now gates
**reads** (`GET ""`, `GET /{id}`) with `require_read_access("setup_security_users_screen_view_only",
"setup_security_users_screen_full_control")` and keeps **writes** (POST/PATCH/DELETE)
admin-only. A view-only user lists users; creating/editing/deactivating still needs
admin.

## RBAC-4 — `transactions_edit_fee_ledger` (field-scoped)

"Edit Fee – Ledger" is a `PATCH /patient-procedures/{id}`, so a blanket right on the
resource would over-gate every charge edit. Instead the guard lives inside
[`PatientProcedureCRUD.update`](../../../app/services/patient_procedure_service.py)
and fires **only when the payload changes the fee** (`data["fee"] != current.fee`).
A tooth/surface edit, a re-price of a migrated charge, or re-sending the same fee is
untouched; a *different* fee from a grouped user without the right is
403 `permission_denied`. Actorless/internal writes and full-access/ungated callers
pass as everywhere else.

## RBAC-5 — `DELETE /patient-procedures/{id}`

Gated on `transactions_delete_procedure` via the resource's `delete_permissions`
(the same DELETE-only mechanism as the C1 payment/claim deletes). Payment deletes
keep `transactions_delete_patient_payments`; the two no longer share a gate.

## RBAC-6 — extended coverage (phased)

**Mechanism:** the CRUD factory now has `create_permissions` and
`update_permissions` alongside `delete_permissions`, each gating exactly one verb on
top of the shared `write_permissions`. So any generic resource's create/edit/delete
can be gated with a one-line registry entry.

**Enforced now:**

| Right | Endpoint |
|---|---|
| `transactions_add_post_patient_payments` | `POST /patient-payments` |
| `transactions_add_post_insurance_payments` | `POST /ledger-insurance-details/payment` + `/payment-batch` |
| `charting_perio_full_control` | perio-exam + perio-exam-detail writes, and `PUT /perio-exams/{id}/details` (bulk chart save) |
| `transactions_treatment_plan_delete` | `DELETE /treatment-plans/{id}` |

**Still ungated (next phase — FE gates stay advisory):** `patient_prescription_strike_off`
(field-scoped on the prescription PATCH, like RBAC-4), treatment-plan
`discount`/`edit_fee`/`change_status` (field-scoped on the item PATCH),
progress-note lock override, medical-history edits, `imaging_capture_acquire`
(the capture route), `transactions_add_post_adjustments`. These are field-level or
bespoke-route guards; each is a small, separate change and mis-mapping one breaks a
workflow, so they're deferred rather than rushed. Say which the FE is about to flip
live and we'll prioritise those.

---

## Acceptance / verification

Tests in [`tests/test_access_rights_catalog.py`](../../../tests/test_access_rights_catalog.py):
`test_view_only_right_grants_users_list_read` (RBAC-1/3, incl. write-still-admin),
`test_view_only_right_grants_group_rights_read` (RBAC-2),
`test_delete_procedure_is_gated` (RBAC-5),
`test_fee_edit_is_field_scoped` (RBAC-4, incl. the no-move and non-fee cases),
`test_rbac6_write_gates` (RBAC-6 set).

Enforcement model is unchanged: full-access roles bypass, ungated users fall through
on **writes** (but not on the RBAC-1 reads), and a grouped user is 403'd naming
`details.required_any_of`.
