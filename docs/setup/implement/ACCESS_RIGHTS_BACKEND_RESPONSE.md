# Backend Response — Access Rights Catalog Cleanup & RBAC Enforcement

> **To:** Frontend
> **From:** DentC Backend
> **Date:** 2026-09-13
> **Re:** [`ACCESS_RIGHTS_BACKEND_HANDOVER.md`](./ACCESS_RIGHTS_BACKEND_HANDOVER.md)
> **Status:** A1 · A2 · A3 · C2 · B1 · B2 · C1 (phased) — **implemented**. The
> catalog curation ships as an Alembic data migration + a curation-aware seeder;
> effective-rights resolution was already correct and is now covered; server-side
> 403 enforcement is wired on the §4 starter set.

---

## TL;DR

| # | Task | Status | Where |
|---|---|---|---|
| **A1** | Delete 210 obsolete codes | ✅ | migration `8e4a6a8e5ab0` |
| **A2** | Insert 44 new codes | ✅ | same migration |
| **A3** | Rename 4 labels | ✅ | same migration |
| **C2** | Cascade delete to group assignments | ✅ | `apply_curation` (delete `user_group_rights` first) |
| **B1** | `me-full.permissions` = union of group rights | ✅ already true | [`auth.py`](../../../app/api/v1/auth.py) · [`permission_service.py`](../../../app/services/permission_service.py) |
| **B2** | What `permissions_enforced` enforces | ✅ answered below | — |
| **C1** | Server-side 403 on high-risk writes | ✅ starter set | CRUD `delete_permissions` + route deps |

Curated catalog = **363 rights** (319 kept + 44 added). Every count is verified by
tests against the three handover data files, so the module can never drift from
what you shipped.

---

## The single source of truth

All of A1/A2/A3/C2 live in one module,
[`app/services/access_rights_catalog.py`](../../../app/services/access_rights_catalog.py):

- `REMOVED_ROWS` — the 210 `(code, label, category)` to delete (labels/categories
  captured from the live seed so a downgrade is a faithful restore).
- `ADDED_RIGHTS` — the 44 `{code, label, category}` from `ADD_rights.json`, verbatim.
- `RENAMES` — the 4 `(code, old_label, new_label)` from §A3.
- `apply_curation(db)` — idempotent: cascade-delete removed → upsert added → rename.
- `revert_curation(db)` — the downgrade.

Both the Alembic migration and `scripts/seed_permissions.py` call `apply_curation`,
so a fresh seed and an in-place upgrade land on the identical 363-row catalog and
**cannot diverge**. (This is the same "lives once" pattern the codebase uses for
coverage categories and the medical-history catalog.)

### How to apply

Already-seeded DB (dev/prod) — the in-place data migration:

```bash
python -c "from alembic.config import main; main(['upgrade','head'])"
```

Fresh DB / re-seed — the seeder now curates automatically:

```bash
python -m scripts.seed_permissions --catalog-only
# catalog: 529 distinct rights (...)
# curation: -210 removed (N group rights cascaded), +44 added, 0 reactivated, 4 renamed
# catalog now 363 rights
```

> The `code` is treated as immutable (as you require): the handful of
> "replacements" (Denticon Practice Analytics → Dashboard, `help_access_invoices`
> → Help Center) are expressed as delete-old (A1) + add-new (A2), never a code
> mutation.

---

## Task B — Effective-rights resolution

### B1 · `me-full.permissions` is the union of the user's group rights — confirmed

This already held before the handover and is unchanged. For a request to
`GET /auth/me-full`:

- **Non-super-admin:** `permissions` = the **union of `right_codes` across every
  *active* `user_group` the user belongs to** (via `user-group-memberships`),
  intersected with the **active** catalog (`permissions.is_active = true`). Exactly
  what §B1 asks for.
- **Super-admin bypass rule (documented):** the bypass is **role-based**. The roles
  that hold every right with no group assignment are **`admin`** and
  **`super_admin`** (`permission_service.FULL_ACCESS_ROLES`). For those, `me-full`
  returns the entire active catalog and `groups: []` — the behaviour you observed
  for `admin`. (The four office-context rights and `owner`/`manager` leadership
  roles are a separate OFF-SCOPE concern and don't change this rule.)
- **The third case — ungated:** a non-admin user who belongs to **no group** gets
  `permissions: []` and **`permissions_enforced: false`** (see B2). This is
  deliberate: the practice hasn't placed them under the rights model yet, and
  refusing every write to such a user would lock a freshly-migrated tenant out of
  its own data on deploy day.

Resolution is two statements in
[`permission_service.effective_permissions`](../../../app/services/permission_service.py);
`me-full` assembles the response in [`auth.py`](../../../app/api/v1/auth.py).

### B2 · What `permissions_enforced: true` enforces today — answered

`permissions_enforced` is **not** informational — it tells the UI whether the
server is actually gating this caller, and it is `true` in exactly two cases:

1. the caller is a **full-access role** (`admin`/`super_admin`) — gated, but every
   check passes; or
2. the caller **belongs to ≥ 1 active group** — gated on the union of that group's
   rights.

It is `false` only for the **ungated** case (non-admin, no group), where the server
falls back to the legacy coarse `users.role` check and does **not** reject based on
the fine-grained rights.

**What the server rejects when `permissions_enforced` is true:** any request to a
guarded endpoint whose right the caller's group set doesn't include → **403
`permission_denied`**, with `details.required_any_of` naming the codes that would
have satisfied it (plus `details.groups`). Before this change the only guarded
surface was the insurance-plan write path (EDIT-PLAN-5) and the plan lock; C1 below
extends that to the §4 high-risk operations. Reads are never gated by this
mechanism. So for the UI: when `permissions_enforced` is `true`, gating a code you
see missing is safe (the server agrees); when it's `false`, the server won't
refuse, so the FE gate is advisory only.

> This flag is unrelated to office-scope enforcement (`OFFICE_ASSIGNMENT_ENFORCED`),
> as your note says.

---

## Task C — Server-side enforcement (C1, phased)

The authoritative check is a route dependency
([`require_permission`](../../../app/api/deps.py) → `permission_service`): it 403s a
**grouped** caller who lacks **any** of the required codes, and lets a full-access
role or an **ungated** caller through (same resolution as B1). This is the "single
dependency that reads the caller's resolved rights and 403s on a missing code"
pattern §4 asked for.

Two wiring mechanisms:

1. **Delete-specific gating on generic CRUD.** New
   `CrudConfig.delete_permissions` gates **only the DELETE verb** (create/update stay
   on the role check), because e.g. `patient_delete_patient_information` should not
   also gate editing a patient.
2. **Per-route dependencies** on the bespoke (non-CRUD) operations.

Starter set now returning 403 without the right:

| Right code | Guarded endpoint |
|---|---|
| `patient_delete_patient_information` | `DELETE /patients/{id}` |
| `patient_delete_patient_insurance_plan_information` | `DELETE /patient-insurance/{id}` |
| `transactions_delete_patient_payments` | `DELETE /patient-payments/{id}` (void) |
| `transactions_delete_insurance_claims` | `DELETE /insurance-claims/{id}` |
| `appointments_delete_existing_appointment` | `DELETE /appointments/{id}` |
| `charting_restorative_delete_condition` *(new)* | `DELETE /chart-conditions/{id}` |
| `imaging_delete_image` *(new)* | `DELETE /image-groups/{id}`, `DELETE /image-details/{id}` |
| `transactions_treatment_plan_post_to_ledger` | `POST /treatment-plan-items/{id}/post` |
| `appointnow_approve_booking` *(new)* | `POST /appointnow/requests/{id}/approve` |
| `appointnow_decline_booking` *(new)* | `POST /appointnow/requests/{id}/decline` |

**Deliberately deferred** (phased, per §4 "not exhaustive"):
`transactions_edit_fee_ledger` — "Edit Fee – Ledger" maps to the generic PATCH on
`patient-procedures`, and gating all patient-procedure updates with a fee-specific
right would over-gate. It needs a fee-field-only guard, which is a follow-up rather
than a one-line wire-up. Everything else in §4's illustrative table is covered.

---

## Acceptance criteria

- [x] `GET /api/v1/permissions` returns **363** rows; none of the 210 REMOVE codes
      remain; all 44 ADD codes present with the given category (test:
      `test_apply_curation_lands_on_363_and_cascades`).
- [x] No `user_group` references a deleted code — the delete cascades to
      `user_group_rights` first (C2; same test).
- [x] A test user in one group: `me-full.permissions` equals that group's
      `right_codes`; a super-admin still gets all codes (test:
      `test_me_full_is_union_of_group_rights_with_super_admin_bypass`).
- [x] B2 answered (above).
- [x] C1 (phased): the delete / post-to-ledger / approve endpoints in §4 return 403
      without the right (tests: `test_delete_patient_is_gated_only_for_grouped_users`,
      `test_supplemental_routes_are_gated`).

---

## Files changed

| File | Change |
|---|---|
| `app/services/access_rights_catalog.py` | **new** — REMOVE/ADD/RENAME data + `apply_curation`/`revert_curation` |
| `alembic/versions/8e4a6a8e5ab0_curate_access_rights_catalog.py` | **new** — data migration (A1/A2/A3/C2) |
| `scripts/seed_permissions.py` | seeder now applies the curation (fresh seed → 363) |
| `app/crud/router_factory.py` | `CrudConfig.delete_permissions` → DELETE-only gate |
| `app/api/v1/registry.py` | `delete_permissions` on patients / patient-insurance / patient-payments / insurance-claims / appointments / chart-conditions / image-groups / image-details |
| `app/api/v1/treatment.py` | post-to-ledger route gated |
| `app/api/v1/appointnow.py` | approve / decline routes gated |
| `tests/test_access_rights_catalog.py` | **new** — data fidelity, curation, B1, C1 |
| `openapi.json` | regenerated |
