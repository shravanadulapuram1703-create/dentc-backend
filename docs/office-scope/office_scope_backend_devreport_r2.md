# Office Scope — Backend Dev Report, Round 2 (integration follow-up)

> **Module:** cross-cutting (office context) · **Date:** 2026-09-13 · **Backend:** DentC Backend v1.0.0 (`/api/v1`)
> **Follows:** `office_scope_backend_devreport.md` (the OFF-SCOPE-1…19 ask) and
> `office_scope_backend_response.md` (your reply, Alembic `f811e916183e`).
> **Frontend layer:** `src/features/office-scope/**`, `src/services/api.ts`.

## TL;DR

Thanks — the response covers all 19 items. The frontend enforcement slice is now
wired and verified live (flag flipped, `X-Office-ID` on every mutation, 403
handler). **But we cannot finish integration or verify enforcement end-to-end
yet, for two reasons found while wiring it up:**

1. 🔴 **The build in your response is NOT deployed on the dev host `:8000`.** The
   migration `f811e916183e` and the new permission codes are absent there.
2. 🔴 **Permission code names don't match.** `me-full` serves
   `office_scope_view_all_offices`, not the `offices:view_all` family named in
   your response.

Everything else in this report is a short list of contract details we need
pinned down (403/422 body shapes, param serialization, field names/enums) plus a
**test-account request** so both sides can actually exercise the 403 paths.

---

## A. Verified against the running dev host (`:8000`, `admin`/`admin`)

`GET /auth/me-full` for the seeded admin returns:

```
role:                 null            (the JWT carries role "super_admin")
permissions_enforced: true
current_office_id:    <field absent>
offices:              []              (zero user_offices rows → ungated)
office permissions:   ["office_scope_view_all_offices",
                       "appointments_add_appointment_in_other_office", …]
                      (NO colon-style codes: 0 hits for offices:view_all,
                       offices:switch_any, patients:view_cross_office,
                       reports:all_offices)
```

Because the admin is `super_admin` **and** has zero assignments, every 403 path
in OFF-SCOPE-1/6 is short-circuited (privileged + ungated). We confirmed reads
and writes with `X-Office-ID: 1` and `2` all return **200**, and the header
tracks an office switch — but that only proves the *happy* path. **The refusal
paths cannot be reached with this account** (see §D).

---

## B. Blockers

### 🔴 FE-OFF-1 — Deploy the response build to the dev host

Evidence that `:8000` predates your response:

- `MeFull` has **no `current_office_id`** field (OFF-SCOPE-3 says it's added).
- `MeFull.permissions` has **none** of the OFF-SCOPE-13 colon codes.
- The seeded admin still has `offices: []` (OFF-SCOPE-10 backfill not run here).

**Impact:** the frontend work that depends on new params/fields in the generated
Orval client is blocked, and we are deliberately **not** running `npm run api:sync`
(it would regenerate the client against the *old* `openapi.json` and churn ~40
files for nothing). Please deploy `f811e916183e` to the dev host and confirm, and
run `scripts/backfill_user_offices.py` / `scripts/backfill_provider_offices.py`
there so we have realistic assignment data.

### 🔴 FE-OFF-2 — Confirm the final permission code names

Your OFF-SCOPE-13 names four codes:
`offices:view_all`, `offices:switch_any`, `patients:view_cross_office`,
`reports:all_offices`. The deployed catalog instead exposes
**`office_scope_view_all_offices`** (and the legacy
`appointments_add_appointment_in_other_office`).

The frontend now accepts **both** namings for "view all" (alias
`CATALOG_PERMISSION_VIEW_ALL_OFFICES` in `officeScopeModel.ts`), so it will work
whichever ships. To let us drop the alias and wire the other three correctly,
please confirm:

- Will production emit `offices:view_all` or `office_scope_view_all_offices`?
- Do `offices:switch_any`, `patients:view_cross_office`, `reports:all_offices`
  exist as **distinct** codes, or do they collapse into
  `office_scope_view_all_offices` / the legacy coverage right? The FE currently
  maps: view-all → `office_scope_view_all_offices` | `offices:view_all`;
  switch-any → `offices:switch_any` | `appointments_add_appointment_in_other_office`.

---

## C. Contract details to confirm (needed to finish Phase 5 once deployed)

| Id | What we need confirmed | Why the FE needs it |
|---|---|---|
| **FE-OFF-3** | **Exact JSON body of the 403** for `office_not_assigned` and `patient_not_in_office`. Our handler (`services/api.ts`) reads, in order: `data.code`, `data.detail.code`, then string `data.detail`. Which one will you send? | The toast + no-auto-switch behaviour keys off this code; a shape we don't recognise falls through as a generic error. |
| **FE-OFF-4** | **422 body** for `office_id_required` (OFF-SCOPE-11) and `operatory_office_mismatch` (OFF-SCOPE-12) — same `code` location question. | Posting handlers surface these inline. |
| **FE-OFF-5** | **`office_ids[]` serialization.** The FE axios client sends repeated keys (`office_ids=1&office_ids=2`, via `paramsSerializer: { indexes: null }`), **not** `office_ids[]=` or CSV. Confirm FastAPI parses repeated keys. | OFF-SCOPE-8 "My offices" server-side; wrong serialization = silent 422 or ignored filter. |
| **FE-OFF-6** | **`all_offices`** exact param name + encoding (`all_offices=true`?), and the **`include_global`** default per resource (OFF-SCOPE-4). | The FE already emits `all_offices=true` on deliberate all-office reads (`allOfficesParam`); confirm nothing narrows silently otherwise. |
| **FE-OFF-7** | **`MeFull.current_office_id`** + **`UserSelfUpdate.current_office_id`** — field names, nullable, and the fallback/validation rule when the stored office is no longer assigned. | Server-side working-office restore (OFF-SCOPE-3). |
| **FE-OFF-8** | **`GET /patients`**: exact `search_scope` enum values (`current` \| `all` \| `group`?), the `seen_at_office_id` param name, and whether the response row exposes seen-at so we can badge it. | Patient search "This office (home or seen here)" (OFF-SCOPE-5). |
| **FE-OFF-9** | **`X-Office-ID` on GET requests.** The FE attaches it to **every** non-login request (reads included) for audit. Confirm the header does **not** narrow read results and does **not** 403 a read when the working office is one the caller may use. | We rely on reads being filtered only by explicit query params, never by the header. |

---

## D. Test-account request (so enforcement can actually be tested)

The only usable dev account is `super_admin` with zero assignments — it is
privileged *and* ungated, so **no 403/refusal path is reachable**. To verify
OFF-SCOPE-1/2/6/11/13 end-to-end we need, on the dev host:

1. A **non-privileged** user (e.g. `front_desk`) assigned to a **subset** of
   offices (say offices 1 and 4) and **without** `office_scope_view_all_offices`.
2. At least one patient whose `home_office_id` is an office that user is **not**
   assigned to (to exercise `patient_not_in_office`).
3. Credentials we can log in with locally.

With that we can confirm: switching to an unassigned office is refused; omitted
`office_id` narrows to assigned offices; `all_offices=true` is refused without the
right; a cross-office chart 403s; and a create without an office 422s (when
`OFFICE_REQUIRE_POS_OFFICE` is on).

---

## E. Frontend status (for your reference)

**Shipped now (works against the current client; verified live):**

- `OFFICE_ASSIGNMENT_ENFORCED = true` — switcher mirrors server membership;
  privileged users and zero-assignment users are never fenced (matches your two
  escape hatches).
- `X-Office-ID` header attached in `services/api.ts` on every non-login request,
  kept in sync with the working office (`officeHeader.ts`). Verified: header =
  working office, tracked a live switch 1→2 across the scheduler feed,
  `/offices/2/schedule`, and AppointNow polling; all 200, no 403.
- 403 handler for `office_not_assigned` / `patient_not_in_office` (toast, never
  auto-switch, re-rejects so the calling screen still handles it).
- Permission-name alias so `can_view_all_offices` works on either build.

**Deferred until FE-OFF-1 (deploy) + `npm run api:sync`** — each needs new
params/fields in the generated client:

- Server-side `current_office_id` persistence (OFF-SCOPE-3).
- Patient search `search_scope` / `seen_at_office_id` (OFF-SCOPE-5).
- `office_ids[]` server-side for "My offices" (OFF-SCOPE-8).
- Utilities on the real run endpoints (OFF-SCOPE-16).

**No FE change needed:** patient-tab sub-lists (OFF-SCOPE-7) stay org-wide by
patient — we will not office-filter the chart/ledger.

---

### Priority for the backend team

1. **FE-OFF-1** — deploy `f811e916183e` to the dev host + run the backfills.
2. **FE-OFF-2** — confirm the permission code names.
3. **FE-OFF-3 … FE-OFF-9** — confirm the contract details (a one-line answer each is plenty).
4. **§D** — seed a restricted test user.

Ping us when the dev host is on the new build and we'll `api:sync` and close out the deferred items in one pass.
