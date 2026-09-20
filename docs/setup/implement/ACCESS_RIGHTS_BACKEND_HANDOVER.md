# Backend Handover — Access Rights Catalog Cleanup & RBAC Enforcement

> **To:** DentC Backend team
> **From:** Frontend
> **Date:** 2026-09-13
> **Purpose:** Turn the placeholder "User Group Access Rights" catalog into a curated, DentC-accurate set,
> and confirm/complete the server-side pieces the frontend needs to actually enforce access per user.
> **Companion analysis (why):** [`ACCESS_RIGHTS_CATALOG_AUDIT.md`](./ACCESS_RIGHTS_CATALOG_AUDIT.md)
> **Data files (what — machine-actionable):** [`handover/REMOVE_codes.txt`](./handover/REMOVE_codes.txt),
> [`handover/ADD_rights.json`](./handover/ADD_rights.json), [`handover/KEEP_codes.txt`](./handover/KEEP_codes.txt)

---

## 0. What we're asking you to do (checklist)

| # | Task | Type | Priority |
|---|---|---|---|
| **A1** | **Delete 210** obsolete permission codes from the catalog | Data migration | P1 |
| **A2** | **Insert 44 new** permission codes (DentC operations with no right today) | Data migration | P1 |
| **A3** | Apply a few **label/category renames** on surviving rows (optional polish) | Data migration | P3 |
| **B1** | Confirm `GET /auth/me-full.permissions` = **union of the signed-in user's group rights** (with super-admin bypass) | Confirm/fix | P1 |
| **B2** | Clarify what `permissions_enforced: true` **enforces server-side today** (if anything) | Confirm | P1 |
| **C1** | Add **server-side enforcement** (403) on high-risk write endpoints, keyed to the right codes | Feature | P2 |
| **C2** | Referential integrity: deleting/renaming a code must **cascade to group assignments** | Data integrity | P1 |

The result should be a catalog of **363 rights** (319 kept + 44 added), every one mapping to a real DentC
screen or operation.

---

## 1. Current state (as the frontend sees it)

The catalog is served by `GET /api/v1/permissions` → `PermissionRead { code, label, category }`, **529 rows
today**. It is the **legacy Denticon rights list, imported wholesale** (evidence in the audit: 12 rows are
literally audit metadata like `Modified On: 1/14/2022 6:09:00 AM PT`; ~31 are other Denticon tenants' custom
office reports).

Endpoints already in place (no change needed to their shape):

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/permissions` | The assignable-rights **catalog** (this is what we're curating) |
| `GET/PUT /api/v1/user-groups/{group_id}/rights` | A group's assigned right codes (`GroupRightsSet { right_codes: string[] }`, PUT = full replace) |
| `GET/POST /api/v1/user-group-memberships` | User ↔ group membership |
| `GET /api/v1/auth/me-full` | Returns `permissions: string[]`, `permissions_enforced: bool`, `groups: string[]` for the signed-in user |

**Key fact for enforcement:** `GET /auth/me-full` **already returns `permissions`** — the current user's
effective right codes. The frontend will gate on this array; we do **not** need a new endpoint for it,
provided B1 below holds. (Today, for the `admin` super-user it returns all 529 and `groups: []` — i.e.
super-admin gets everything. We need to confirm a normal user gets exactly the union of their groups' rights.)

**`code` is the stable key.** The frontend binds enforcement to `code`, not to `label` or DB id. So:
renaming a **label** or **category** is safe; changing a **code** is a breaking change (treat a code change
as delete-old + add-new and update any group assignments).

---

## 2. Task A — Curate the catalog (data change)

### A1 · DELETE 210 codes → [`handover/REMOVE_codes.txt`](./handover/REMOVE_codes.txt)

Tab-separated: `code <TAB> reason <TAB> (label)`. These fall into two groups:

- **143 Tier-1** — junk / not-DentC: scraped audit-metadata rows, Denticon/3rd-party products (Practice
  Analytics, MyTooth, AthenaNet, EHR, Dentilytics, MouthWatch, Transworld, Voice/AI charting), ~31
  client-org-specific office reports, Automated Campaigns (20), DHA/DCA/EDI/837/835 utilities, Task
  Manager / Tickler / Time Clock.
- **67 Tier-2** — Denticon features with no DentC screen (Code Bundling, Collection Agencies, Provider
  Goals, SSO/Multi-PGID, Reset Benefits, Ortho setup, Consolidate/Replace utilities, Caries Risk, Status
  Tracker, Flash Alerts, Reallocate, Postcards, DHA/Ortho/Recall/Excel/Labels reports, Batch Schedule
  Report, Capitation, Batch Insurance/835/Dentical, Short call/notice list).

> **We deliberately KEPT 13 Tier-2 rows** (do **not** delete these): the cross-coder rights (6), External
> API / Vendor Access (3), DPS Ins Verification (2) — all have DentC placeholder routes and are roadmap
> stubs — plus Two-Way Communication (2), which is real (see A3 rename).

### A2 · INSERT 44 codes → [`handover/ADD_rights.json`](./handover/ADD_rights.json)

Array of `{ code, label, category }`, ready to seed. These are shipped DentC screens/operations with **no**
permission today. Highlights:

| Area | New rights | Notes |
|---|---|---|
| **Charting** *(new category)* | Restorative chart (full/view/delete-condition), Perio chart (full/view/compare/print) | Catalog's only "Charting" row was Denticon AI Assist (deleted) |
| **Imaging** *(new category)* | X-rays/images (full/view/capture/delete/export) | No imaging right existed at all |
| **Patient** | Lab Tracking cases, Documents (full/view/upload/delete), Letters (full/view/generate), Consent e-sign, Emergency Contacts | |
| **Transactions** | Claims ADA Direct Print, Claims Save-as-Draft, Create Secondary/Tertiary/Quaternary claim | |
| **Appointments** | Scheduler Print | |
| **AppointNow** *(new category)* | Request inbox (full/view), Approve booking, Decline booking | + `setup_appointnow_config_full_control` under Setup |
| **Messaging** *(new category)* | Direct Messages (full/view) | User↔user DM (`/api/v1/messaging/**`) |
| **Setup** | Communications / Phone Assignments (full/view), Signature Pad device | |
| **Help** | Help Center access, Report an Issue, My Tickets | replaces deleted Denticon `help_access_invoices` |
| **Dashboard** *(new category)* | Dashboard view, My Page access | replaces deleted Denticon Practice Analytics |
| **General** | View Data Across All Offices | pair with the `user_offices` scope work when ready |

**5 new categories** will appear: `Charting`, `Imaging`, `AppointNow`, `Messaging`, `Dashboard`. The
frontend picker groups by `category` automatically — no FE change needed.

> Codes verified: no collision with any kept/removed code, no duplicates.

### A3 · Label / category renames on surviving rows (optional, P3)

Cosmetic only — **keep the `code` unchanged**, update the display `label`:

| code | current label | → new label |
|---|---|---|
| `utilities_two_way_communication_full_control` | Utilities - Two Way Communication Full Control | Utilities - Patient SMS / Two-Way Communication Full Control |
| `utilities_two_way_communication_view_only` | …View Only | Utilities - Patient SMS / Two-Way Communication View Only |
| `patient_messaging_hub_user_full_control` | Patient - Messaging Hub User Full Control | Patient - SMS / Communication Full Control |
| `patient_messaging_hub_view_only` | Patient - Messaging Hub View Only | Patient - SMS / Communication View Only |

Also, any surviving labels containing "PGID" should read "organization/tenant" (none remain after A1, but
please flag if your data differs).

### C2 · Referential integrity (must accompany A1)

Group rights are stored as code strings (`GroupRightsSet.right_codes`). When you delete a catalog code in
A1, **also remove it from every group's assignment** so no group references a dead code. After curation,
the "Save with Full Access" button (which sends the entire catalog's codes) should resolve to the new
~363-code set automatically.

---

## 3. Task B — Effective-rights resolution (confirm/fix)

### B1 · `me-full.permissions` must be the union of the user's group rights

The frontend will enforce by reading `GET /auth/me-full.permissions` and checking membership of a `code`.
Please confirm (or implement) that for a **non-super-admin** user this array is exactly:

> the **union of `right_codes` across all `user_groups` the user belongs to** (via `user-group-memberships`),
> intersected with the live catalog.

and that a **super-admin / owner role bypasses** (gets all codes) — today `admin` returns all 529 with
`groups: []`, which implies a role-based bypass we want to keep. Please document the exact rule
(which `role` / flag grants the bypass).

### B2 · What does `permissions_enforced: true` mean today?

`me-full` returns `permissions_enforced: true`. The frontend currently enforces **nothing**. Please tell us
whether the backend **already rejects** any request based on these permissions, or whether this flag is
currently informational. This determines whether C1 is net-new or hardening existing checks.
*(Note: this flag is unrelated to office-scope enforcement — `OFFICE_ASSIGNMENT_ENFORCED` is a separate
frontend concern.)*

---

## 4. Task C — Server-side enforcement (the real security boundary)

Frontend gating is UX only (hides buttons/routes); it is **not** a security boundary and can be bypassed.
The authoritative check must be server-side: reject the request with **403** when the caller lacks the
required right. Recommend starting with the highest-risk **write** operations and expanding.

Illustrative right → endpoint mapping (starter set — not exhaustive):

| Right code | Guard on (example) |
|---|---|
| `transactions_delete_patient_payments` | `DELETE` patient payment |
| `transactions_delete_insurance_claims` | `DELETE` insurance claim |
| `transactions_edit_fee_ledger` | fee edit on a ledger line |
| `transactions_treatment_plan_post_to_ledger` | post-to-ledger |
| `patient_delete_patient_information` | `DELETE /patients/{id}` |
| `patient_delete_patient_insurance_plan_information` | delete patient insurance plan |
| `appointments_delete_existing_appointment` | `DELETE` appointment |
| `imaging_delete_image` *(new)* | delete image / tile |
| `charting_restorative_delete_condition` *(new)* | delete chart condition/procedure |
| `appointnow_approve_booking` *(new)* | approve online booking |

A single dependency/decorator that reads the caller's resolved rights (same resolution as B1) and 403s on a
missing `code` is the pattern we'd expect.

---

## 5. Data contract (unchanged, for reference)

`PermissionRead`:
```json
{ "code": "string (stable key, snake_case)", "label": "string (display)", "category": "string (picker grouping)" }
```
- `code` — immutable identifier the FE enforces on. snake_case, unique.
- `label` — human text shown in the Group Setup picker.
- `category` — groups rows in the picker; new categories appear automatically.

---

## 6. Acceptance criteria

- [ ] `GET /api/v1/permissions` returns **363** rows; none of the 210 `REMOVE_codes.txt` codes remain; all
      44 `ADD_rights.json` codes present with the given category.
- [ ] No `user_group` references a deleted code (C2).
- [ ] For a test user in one group with a known right set, `GET /auth/me-full.permissions` equals that
      group's `right_codes` (B1); a super-admin still gets all codes.
- [ ] B2 answered in writing (what `permissions_enforced` enforces today).
- [ ] (C1, phased) At least the delete/post-to-ledger endpoints in §4 return 403 without the right.

---

## Appendix · File manifest

| File | Contents |
|---|---|
| `handover/REMOVE_codes.txt` | 210 codes to delete (`code <TAB> reason <TAB> (label)`) |
| `handover/ADD_rights.json` | 44 new rights (`{code,label,category}`) ready to seed |
| `handover/KEEP_codes.txt` | 319 surviving codes (reference; `code <TAB> category <TAB> (label)`) |
| `ACCESS_RIGHTS_CATALOG_AUDIT.md` | Full rationale: remove/keep/add analysis + per-module Tier-2 decision |
