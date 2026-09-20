# RBAC — Gaps Observed During Frontend Wiring

> **To:** DentC Backend team
> **From:** Frontend
> **Date:** 2026-09-13
> **Context:** After the catalog curation + C1 enforcement shipped
> ([`ACCESS_RIGHTS_BACKEND_RESPONSE.md`](./ACCESS_RIGHTS_BACKEND_RESPONSE.md)), the frontend built a
> gating layer (`src/features/access-control/`) and wired it onto the high-risk writes. This report
> records the gaps found while wiring + live-verifying with a real view-only user.
>
> **Test fixtures (left in the shared dev DB for future RBAC verification):** group **"QA View Only
> (RBAC test)"** (id 22, rights = `setup_security_groups_screen_view_only` +
> `setup_security_users_screen_view_only`); user **`qa_viewonly` / `ViewOnly@123`** (id 841, role
> `staff`, member of group 22).

---

## Summary

| ID | Severity | Gap | Owner |
|---|---|---|---|
| RBAC-1 | 🔴 | `*_view_only` rights don't grant reads — reads gated by coarse `users.role` | Backend |
| RBAC-2 | 🔴 | `GET /user-groups/{id}/rights` 403s a groups-view-only user | Backend |
| RBAC-3 | 🔴 | `GET /users` returns empty for a users-view-only staff user | Backend |
| RBAC-4 | 🟠 | `transactions_edit_fee_ledger` not server-enforced (deferred) | Backend |
| RBAC-5 | 🟠 | `transactions_delete_procedure` (ledger charge delete) not server-enforced | Backend |
| RBAC-6 | 🟡 | Server-side enforcement stops at the C1 starter set — many catalog writes still ungated | Backend |
| FE-RBAC-1 | 🟠 | No FE delete UI for `patient_delete_patient_information` | Frontend |
| FE-RBAC-2 | 🟠 | No FE delete/un-attach UI for `patient_delete_patient_insurance_plan_information` | Frontend |
| FE-RBAC-3 | 🟡 | Restorative / Perio / Imaging screens lack full-vs-view gating | Frontend |
| FE-RBAC-4 | 🟡 | FE gating kill-switch still dark (`RIGHTS_ENFORCED_DEFAULT=false`) | Frontend |

---

## Backend gaps

### RBAC-1 🔴 — `*_view_only` rights do not actually grant reads (root cause)

Per [`ACCESS_RIGHTS_BACKEND_RESPONSE.md`](./ACCESS_RIGHTS_BACKEND_RESPONSE.md) §B2, reads are **never** gated
by the fine-grained rights; the server falls back to the coarse `users.role`. Consequence: assigning a
`setup_*_screen_view_only` (or any `*_view_only`) right to a low-role user does **not** grant read access to
that screen's data — the role check still refuses it. So "view-only" groups are not functional for `staff`,
`front_desk`, etc. RBAC-2 and RBAC-3 are concrete instances.

**Ask:** make a screen's `*_view_only` / `*_full_control` right grant read on that screen's data
endpoints (i.e., a read passes when the caller holds either the view or the full right, **or** the legacy
role allows it) — so a group's view right means what it says.

### RBAC-2 🔴 — `GET /user-groups/{id}/rights` refuses a groups-view-only user

**Observed:** signed in as `qa_viewonly` (holds `setup_security_groups_screen_view_only`), the Groups
screen opens (FE route allows view), but selecting any group triggers a **403** ("Insufficient role for
this operation") and the rights panel shows "No rights assigned yet" for every group.
**Ask:** allow this read for a caller holding `setup_security_groups_screen_view_only` (or `_full_control`).

### RBAC-3 🔴 — `GET /users` returns empty for a users-view-only staff user

**Observed:** signed in as `qa_viewonly` (holds `setup_security_users_screen_view_only`), the Users screen
opens but the grid shows **"No users found"** — the list endpoint (users + home-office join) returns nothing
for a `staff` role.
**Ask:** the users list should be readable by a caller holding `setup_security_users_screen_view_only`.

### RBAC-4 🟠 — `transactions_edit_fee_ledger` not enforced

Backend deferred (response §C1): "Edit Fee – Ledger" maps to the generic `PATCH /patient-procedures/{id}`,
and gating all patient-procedure updates with a fee-specific right would over-gate. **Ask:** add a
fee-field-scoped guard so the right can be enforced. Until then the FE gate on this right is advisory only.

### RBAC-5 🟠 — `transactions_delete_procedure` not enforced

`DELETE /patient-procedures/{id}` (deleting a **charge** from the account ledger,
`EditTransactionModal`) is not gated by `transactions_delete_procedure` (only payment deletes are gated,
via `transactions_delete_patient_payments`). The FE gates the charge-delete button on
`transactions_delete_procedure`, but that is advisory until the server enforces it.
**Ask:** gate the patient-procedure DELETE on `transactions_delete_procedure`.

### RBAC-6 🟡 — enforcement coverage stops at the C1 starter set

Server-side 403 currently covers the ~10 endpoints in response §C1. Many other catalog writes the FE will
gate remain ungated server-side, e.g.: `patient_prescription_strike_off`, treatment-plan
`delete`/`discount`/`edit_fee`/`change_status`, payment posting (`transactions_add_post_*`),
progress-note lock override, medical-history edits, `charting_perio_*` writes, `imaging_capture_acquire`.
**Ask:** extend `require_permission` to the rest of the catalog's write operations (phased). FE gates on
these are advisory (hide/disable) until the server enforces them.

---

## Frontend gaps (tracked here; FE will action)

### FE-RBAC-1 🟠 — no delete UI for `patient_delete_patient_information`

The backend enforces `DELETE /patients/{id}`, but the FE currently exposes **no** patient-delete action
(the Security → Users "Delete" is a stub for *users*, not patients). Nothing to gate today; when a
patient-delete action is added it must wrap on `patient_delete_patient_information`.

### FE-RBAC-2 🟠 — no delete/un-attach UI for patient insurance plans

The backend enforces `DELETE /patient-insurance/{id}`, but the FE has no delete/detach action on a
patient's insurance plans (`src/features/patient-insurance/**` has no delete call). When added, gate on
`patient_delete_patient_insurance_plan_information` (and `patient_un_attach_patient_insurance_plan_information`
for detach).

### FE-RBAC-3 🟡 — clinical screens lack full-vs-view gating

Only discrete deletes are gated so far. The Restorative chart, Perio chart, and Imaging workspace are not
yet gated on their `*_full_control` / `*_view_only` rights, so a view-only user can still edit. Note:
automated chart-condition deletes (missing/implant transitions in `RestorativeChart`) also hit the
enforced `DELETE /chart-conditions/{id}`, so a user lacking `charting_restorative_delete_condition` would
get a 403 mid-edit — the screen-level full/view gate (a follow-up) is what should keep them out of edit
mode in the first place.

### FE-RBAC-4 🟡 — kill-switch still dark

`RIGHTS_ENFORCED_DEFAULT = false` in `src/features/access-control/rights.ts`. Flip to `true` only after
enforcement coverage is broad enough and RBAC-1 (read gating) is resolved — otherwise a view-only user
would be able to *open* screens whose data the backend then refuses to serve.

---

## What's wired on the FE so far (for reference)

Route guards + button gating using `<RequireRight code={…}>` / `useHasRight`:

| Area | Gated action | Right |
|---|---|---|
| Setup → Security | Users/Groups route entry; Add/Copy/Edit/Delete/Save actions | `setup_security_{users,groups}_screen_{full_control,view_only}` |
| Transactions | Delete Claim (ClaimDetail) | `transactions_delete_insurance_claims` |
| Transactions | Post to Ledger (TxPlanToolbar) | `transactions_treatment_plan_post_to_ledger` |
| Account Ledger | Delete row (EditTransactionModal) | `transactions_delete_patient_payments` / `transactions_delete_procedure` |
| Appointments | Delete appointment (Scheduler context menu) | `appointments_delete_existing_appointment` |
| Charting | Delete charted condition (RestorativeChart) | `charting_restorative_delete_condition` |
| Imaging | Delete image (ImageThumbnail) | `imaging_delete_image` |
| AppointNow | Approve / Decline booking (RequestInbox) | `appointnow_approve_booking` / `appointnow_decline_booking` |

All are **dark** until FE-RBAC-4 flips. `me-full.permissions` (union of group rights) drives every check;
super-admin (`admin`/`super_admin`) bypasses; `permissions_enforced === false` (ungated users) grants.
