# Office Scope — Backend Response, Round 2

> **Follows:** `office_scope_backend_devreport_r2.md` (your integration follow-up).
> Prior: `office_scope_backend_response.md` (Alembic `f811e916183e`).

## TL;DR

- **FE-OFF-2 fixed in code** — the invented `offices:*` colon codes are gone.
  The server now keys on and emits the **real catalog code**
  `office_scope_view_all_offices` (plus the legacy coverage alias). You can drop
  the FE alias.
- **§D done** — `scripts/seed_office_scope_test_user.py` seeds a restricted
  `front_desk` account with the refusal paths reachable.
- **FE-OFF-1 is deploy/ops** (I can't reach your dev host) — the build,
  migration `f811e916183e`, and the backfills are all ready; run them there.
- **FE-OFF-3 … FE-OFF-9 answered below** (one line each). The one that needs a FE
  tweak: our error code is at **`error.code`**, not `data.code`/`data.detail`.

---

## FE-OFF-1 — Deploy the build + run backfills (ops)

Nothing more to write on the backend; it's a deploy to `:8000`:

1. `alembic upgrade head` — brings `f811e916183e` (and the concurrent
   access-rights migration that chains after it, `8e4a6a8e5ab0`). Confirm with
   `GET /auth/me-full` showing `current_office_id` and, for a full-access admin,
   `office_scope_view_all_offices` in `permissions`.
2. `python -m scripts.backfill_user_offices` — seeds `user_offices` from evidence
   (so the seeded admin stops being zero-assignment/ungated).
3. `python -m scripts.backfill_provider_offices` — the provider↔office rosters.
4. `python -m scripts.seed_office_scope_test_user` — the §D restricted account.

## FE-OFF-2 — Permission code names (fixed)

Reconciled to the deployed catalog. **`office_scope_view_all_offices` is the one
master office-scope right.** There is **no** distinct `offices:switch_any` /
`patients:view_cross_office` / `reports:all_offices` — they collapse into the
master right; the legacy `appointments_add_appointment_in_other_office`
additionally grants *targeting/switching* to another office.

- Production emits **`office_scope_view_all_offices`** (not `offices:view_all`).
- The three others do **not** exist as distinct codes. Server mapping:
  - **view-all / narrowing-bypass / switch** → `office_scope_view_all_offices`
    **OR** `appointments_add_appointment_in_other_office`;
  - **cross-office patient charts** (OFF-SCOPE-6) → `office_scope_view_all_offices`;
  - **all-office reports / dashboard** (OFF-SCOPE-18) → `office_scope_view_all_offices`.
- Leadership roles (`owner`/`admin`/`manager`/`super_admin`) hold the master
  right implicitly (surfaced in `MeFull.permissions`).

You can drop `CATALOG_PERMISSION_VIEW_ALL_OFFICES`'s `offices:view_all` alias and
map view-all → `office_scope_view_all_offices`, switch-any →
`office_scope_view_all_offices | appointments_add_appointment_in_other_office`.

## FE-OFF-3 — 403 body shape

Standard API envelope (unchanged across the whole API): the code is at
**`error.code`**, structured context at `error.details`.

```json
// 403 office_not_assigned
{"error": {"code": "office_not_assigned", "message": "Office '2' is not assigned to you",
           "details": {"office_id": 2, "field": "office_id", "assigned_office_ids": [1, 4]}}}
// 403 patient_not_in_office
{"error": {"code": "patient_not_in_office", "message": "...",
           "details": {"patient_id": 55, "home_office_id": 2,
                       "required_any_of": ["office_scope_view_all_offices"]}}}
```

**Action for the FE:** read `data.error.code` (not `data.code` / `data.detail`).
This is the app-wide error contract, so aligning the handler to `error.code`
fixes it for every endpoint, not just office scope.

## FE-OFF-4 — 422 body shape

Same envelope; code at `error.code`.

```json
// 422 office_id_required  (OFF-SCOPE-11, only when OFFICE_REQUIRE_POS_OFFICE is on)
{"error": {"code": "office_id_required", "message": "...", "details": {"field": "office_id"}}}
// 422 operatory_office_mismatch  (OFF-SCOPE-12)
{"error": {"code": "operatory_office_mismatch", "message": "...",
           "details": {"code": "operatory_office_mismatch", "field": "operatory_id",
                       "operatory_office_id": 2, "office_id": 1}}}
```

(`details.code` is duplicated on the operatory error for the appointment domain's
existing readers; `error.code` is now set uniformly on both, so read `error.code`.)

## FE-OFF-5 — `office_ids[]` serialization

**Repeated keys** — `?office_ids=1&office_ids=2` — is exactly what FastAPI parses
(`list[int]` query param). Not `office_ids[]=` and not CSV. Your axios
`paramsSerializer: { indexes: null }` is correct. Same on the AppointNow inbox.

## FE-OFF-6 — `all_offices` + `include_global`

- `all_offices` param name and encoding: `?all_offices=true` (a bool;
  `true`/`false`/`1`/`0` accepted). Omitted = default scoping (assigned offices
  for a non-privileged caller). `all_offices=true` needs the master right (403
  `office_not_assigned` otherwise).
- `include_global` default is **per resource kind**: **true** for catalogs
  (fee-schedules, labs, referrals, place-of-service-codes, explosion-codes,
  sms-templates, postcard-templates, campaigns, appointnow-reasons), **false**
  for day-data. Pass `include_global=false`/`true` to override.

## FE-OFF-7 — `current_office_id`

- `MeFull.current_office_id`: `int | null`. Falls back to the caller's **primary**
  `user_offices` (else the first assignment) when the stored value is null or is
  no longer one of the caller's assignments.
- `UserSelfUpdate.current_office_id`: `int | null`, writable via `PATCH /users/me`.
  Validated against the caller's assignments (403 `office_not_assigned` if not
  assigned, unless privileged/ungated); `null` clears it. `last_patient_id` is
  writable the same way (validated against the tenant).

## FE-OFF-8 — patient search (OFF-SCOPE-5)

- `search_scope` enum: **`current` | `all` | `group`** (default = all, org-wide).
  `current` = the caller's working office's home patients; `group` = that office's
  office-group; both resolve the working office from `X-Office-ID`.
- `seen_at_office_id` (int): patients with an appointment **or** a posted
  procedure at that office.
- The patient **row does not expose seen-at** (it would be an N+1 join per row);
  badge from `home_office_id` (+ `home_office_name`/`home_office_code`, already on
  `PatientRead`). Filter by `seen_at_office_id`, don't badge from it.

## FE-OFF-9 — `X-Office-ID` on GET requests

Confirmed:
- The header **never narrows read results** — list reads are filtered only by
  explicit query params (`office_id`/`office_ids`/`office_group_id`/`all_offices`)
  or, for a non-privileged caller with no such param, the default (assigned
  offices). `X-Office-ID` is used only for the write default-stamp and the audit
  trail.
- The header **never 403s a read when the working office is usable** — it is
  validated against the caller's assignments, so an assigned (or, for a privileged
  caller, any) office passes. It 403s only if the working office is genuinely not
  the caller's and they lack the master right — which the switcher never selects.

## §D — restricted test account

`python -m scripts.seed_office_scope_test_user [--tenant N] [--offices 1,4]`
creates/updates:
- `front_desk` / `frontdesk` (role `front_desk`, **no** `office_scope_view_all_offices`),
  assigned to a subset of offices (first two, or `--offices`);
- reports (and creates if absent) a patient homed at an office that user is **not**
  assigned to, for `patient_not_in_office`.

With it you can reach every refusal: switch to an unassigned office (403
`office_not_assigned`), `?all_offices=true` (403), the cross-office chart (403
`patient_not_in_office`), and — with `OFFICE_REQUIRE_POS_OFFICE=true` — a create
without an office (422 `office_id_required`).
