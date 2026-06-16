# Security → Users — Missing user fields (sample-user gap report)

> Raised from a sample "View User" screen (legacy DentC) that contains fields the
> current `users` contract does not model. Captured for backend routing.
> Date: 2026-06-08.

The Tranche-C work covers the large majority of the sample screen. The following fields
have **no place to live** today — neither the form nor the backend contract supports them.

## Structural gaps (need backend contract + UI)

### 1. User Short ID (6 chars)
- **Sample:** `Short ID = KRIUDA`.
- **Status:** `short_id` exists on `OfficeRead` but **not** on `UserRead`/`UserCreate`/
  `UserCompleteCreate`. Legacy assigns each user a 6-char code.
- **Suggested:** add `short_id` to the user model (unique per tenant) + a form field.

### 2. Report Access Provider
- **Sample:** `Report Access Provider` (links a user to a provider for reporting scope).
- **Status:** no field; `provider_id` exists only on clinical resources.
- **Suggested:** `report_access_provider_id?: number | null` on the user, fed by
  `GET /api/v1/providers`.

### 3. Custom Fields (Custom 1, Custom 2)
- **Sample:** two free-text custom fields under Login Info.
- **Status:** no field. (Could be modeled as preferences, but they are presented as
  first-class labeled inputs, not settings.)
- **Suggested:** `custom_1` / `custom_2` on the user, or a defined `custom_fields` map.

### 4. Signature (Topaz pad)
- **Sample:** signature capture ("install Topaz Systems Inc. Signature Pad").
- **Status:** `signature_*` fields exist on other resources, not on the user.
- **Suggested:** `signature_id`/`signature_data` on the user + a capture control.

### 5. User Image
- **Sample:** `User Image` (avatar).
- **Status:** no field; no upload endpoint for user avatars.
- **Suggested:** `image_url`/`avatar_id` + an upload endpoint.

## ✅ Preference-storable — now wired (frontend)

These four are stored as preference keys and now have form inputs in the User Settings tab
(`AddEditUserModal`) and read-outs in the View modal. Still pending: backend confirmation
of the canonical `user_preferences_schema` keys (open question #2).

| Sample field | Pref key | Control |
| --- | --- | --- |
| Toolbar | `toolbar` | text input |
| Perio Setup Template | `perio_setup_template` | text input |
| Production View? | `production_view` | checkbox |
| Show Production Colors in Appt Units? | `show_production_colors` | checkbox |

**Remaining work:** route the five structural fields above (Short ID, Report Access
Provider, Custom Fields, Signature, User Image) as backend contract additions.

---

## ✅ Backend resolution (2026-06-09)

All five structural gaps are now modelled and exposed. Migration:
`c0d1e2f3a4b5_add_user_structural_fields` (additive ALTERs on `users`).

| # | Field on user | Type | Notes |
| --- | --- | --- | --- |
| 1 | `short_id` | `str?` (≤6) | Unique per tenant (`uq_users_tenant_short_id`); 409 on collision. |
| 2 | `report_access_provider_id` | `str?` | FK → `providers.id`; populate the dropdown from `GET /api/v1/providers`. |
| 3 | `custom_1`, `custom_2` | `str?` | Free-text. |
| 4 | `signature_data` | `str?` | Base64/data-URL string from the Topaz pad. |
| 5 | `image_url` | `str?` (read-only) | Set via the upload endpoint below, **not** via create/update bodies. |

**Where the fields live in the contract**
- `UserRead` (returned by `GET /users`, `GET /users/{id}`, `GET /auth/me-full`) — exposes all six (incl. `image_url`).
- `UserCreate` / `UserUpdate` (`POST /users`, `PATCH /users/{id}`) — accept gaps 1–4.
- `UserCompleteCreate` / `UserCompleteUpdate` (`POST /users/complete`, `PUT /users/{id}/complete`) — accept gaps 1–4 alongside the existing related-resource sections.

**User image (gap #5) — dedicated multipart endpoints**
- `POST /api/v1/users/{user_id}/image` — multipart `file`; allowed types `image/jpeg`/`image/png`, ≤2 MB (`422` otherwise). Returns `{ "image_url": "…" }` and replaces any prior avatar.
- `DELETE /api/v1/users/{user_id}/image` — clears the avatar (`204`).

---

## Gap 8 — Audit Information (Last Updated By / On) ✅ resolved (2026-06-09)

**Requirement:** show *Last Updated By* / *Last Updated On* next to *Created By* / *Created On*,
with a person name rather than a raw user id.

Migration: `e2f3a4b5c6d7_add_user_updated_by` (adds `users.updated_by`, FK → `users.id`;
`updated_at` already existed via the timestamp mixin).

**New `UserRead` fields**

| Field | Type | Notes |
| --- | --- | --- |
| `updated_at` | `datetime?` | Auto-set on every row change (`onupdate`). |
| `updated_by` | `int?` | Actor user id of the last edit. |
| `created_by_name` | `str?` | Resolved display name for `created_by` (full name, else username). |
| `updated_by_name` | `str?` | Resolved display name for `updated_by`. |

- `*_by_name` are resolved server-side in **one batched query** (no N+1) and returned on the
  Users-module read endpoints: `GET /users` (list), `GET /users/{id}`, `POST /users`,
  `PATCH /users/{id}`, `POST /users/complete`, `PUT /users/{id}/complete`. No separate
  id→name lookup endpoint needed for the panel.
- `updated_by` is stamped to the authenticated actor on every write that mutates the user row:
  `PATCH /users/{id}`, `PUT /users/{id}/complete`, `PUT /users/{id}/security-settings`,
  and the image upload/delete endpoints. `created_by` is now also stamped on `POST /users`
  (previously only `POST /users/complete` set it — this is why the panel used to show "System").

**Frontend:** `mapUsersGrid` can bind `updated_at`/`updated_by_name` directly; the audit panel
shows the person name from `created_by_name` / `updated_by_name`.
