# Authentication — Backend Dev Report

Status of backend support for the Authentication module, and the gaps the
frontend depends on. The frontend workflows for these gaps are **already built**
(login modernization, forgot/reset password, legacy activation) and call the
suggested endpoints below; until the endpoints exist they return `404` and the
UI shows a friendly "not available yet" message via
`src/features/auth/utils/authErrors.ts`. No fake/client-side authentication is
performed.

Field naming is **snake_case** throughout, matching `openapi.json` and the
generated Orval client (`src/api/generated/**`).

---

## 1. Endpoints that EXIST today

| Method | Path | Operation | Request | Response |
|--------|------|-----------|---------|----------|
| POST | `/api/v1/auth/login` | `login` | `LoginRequest { username, password }` | `TokenResponse { access_token, refresh_token, token_type?, expires_in }` |
| POST | `/api/v1/auth/refresh` | `refresh_token` | `RefreshRequest { refresh_token }` | `TokenResponse` |
| POST | `/api/v1/auth/logout` | `logout` | `Body_logout { refresh_token? }` | `204/200` |
| GET | `/api/v1/auth/me` | `get_me` | — | `UserRead` |
| GET | `/api/v1/auth/me-full` | `get_me_full` | — | `MeFull { user, tenant?, offices? }` |
| POST | `/api/v1/users/me/change-password` | `change_my_password` | `ChangePasswordRequest { current_password, new_password (≥8) }` | `200` |
| POST | `/api/v1/auth/signup` | `signup` | `SignupRequest { practice_name, practice_code, email, username, password, first_name?, last_name? }` | `TokenResponse` |

`UserRead` already exposes **`must_change_password: boolean`** and
**`last_login_at`**. The frontend now uses `must_change_password` to force a
password change on first login (login routes to
`/setup/security/change-my-password` when it is `true`).

> Note: `src/services/authService.ts` is a legacy hand-written service whose
> `login()` still injects a `tenant_id` that is no longer part of
> `LoginRequest`. It is superseded by the generated client and should be trimmed
> when convenient; it is not on the live login path (`AuthContext` uses the
> generated `login()`).

---

## 2. MISSING APIs (gaps)

### 2.1 Forgot Password — request reset

- **Module:** Authentication · **Screen:** Forgot Password
- **Requirement:** Email a password-reset link to a user.
- **Suggested endpoint:** `POST /api/v1/auth/forgot-password`
- **Request:** `{ "email": "" }`
- **Response:** `{ "message": "" }` — **always 200**, regardless of whether the
  email exists (prevent account enumeration).
- **Impact:** Required for the Forgot Password workflow.
- **Frontend:** `src/pages/ForgotPasswordPage.tsx` →
  `authExtrasService.forgotPassword`.

### 2.2 Reset Password — validate token

- **Module:** Authentication · **Screen:** Reset Password
- **Requirement:** Tell the UI whether a reset link is still valid before showing
  the new-password form.
- **Suggested endpoint:** `POST /api/v1/auth/reset-password/validate`
- **Request:** `{ "token": "" }`
- **Response:** `{ "valid": true, "email": "" }` (`email` optional, for display).
- **Impact:** Drives the validating → valid/invalid states of the reset screen.
- **Frontend:** `src/features/auth/pages/ResetPasswordPage.tsx` →
  `authExtrasService.validateResetToken`.

### 2.3 Reset Password — submit new password

- **Module:** Authentication · **Screen:** Reset Password
- **Requirement:** Set a new password using a valid reset token.
- **Suggested endpoint:** `POST /api/v1/auth/reset-password`
- **Request:** `{ "token": "", "new_password": "" }` (`new_password` ≥ 8)
- **Response:** `{ "message": "" }`
- **Impact:** Required to complete the Forgot Password workflow.
- **Frontend:** `ResetPasswordPage` → `authExtrasService.resetPassword`.

### 2.4 Legacy Activation — verify user

- **Module:** Authentication · **Screen:** Legacy Activation
- **Requirement:** Confirm a legacy user exists and may activate, and start a
  verification challenge.
- **Suggested endpoint:** `POST /api/v1/auth/legacy-user/verify`
- **Request:** `{ "username_or_email": "" }`
- **Response:**
  ```json
  {
    "eligible": true,
    "legacy_activation_completed": false,
    "verification_method": "email",
    "masked_email": "s•••@dental.local",
    "activation_token": ""
  }
  ```
  - `verification_method` ∈ `"email" | "otp" | "magic_link"` (UI supports all three).
  - `legacy_activation_completed = true` → UI blocks with "already activated"
    (see Business Rule 2).
- **Impact:** Entry point of the one-time legacy onboarding flow.
- **Frontend:** `src/features/auth/pages/LegacyActivationPage.tsx` →
  `authExtrasService.legacyVerify`.

### 2.5 Legacy Activation — create password

- **Module:** Authentication · **Screen:** Legacy Activation
- **Requirement:** Store the new password under the new auth platform and mark
  activation complete (one-time).
- **Suggested endpoint:** `POST /api/v1/auth/legacy-user/create-password`
- **Request:** `{ "username_or_email": "", "new_password": "", "activation_token": "" }`
- **Response:** `{ "message": "" }`
- **Impact:** Completes legacy migration; subsequent logins use the new hash.
- **Frontend:** `LegacyActivationPage` → `authExtrasService.legacyCreatePassword`.

---

## 3. Suggested user-model fields (future)

The frontend assumes a future `users` shape similar to the phase brief. Fields
**already present** in `UserRead`: `is_active`, `must_change_password`,
`last_login_at`, `role`, `created_at`. Fields **still needed** for legacy
onboarding:

| Field | Type | Purpose |
|-------|------|---------|
| `is_legacy_user` | bool | Remains `true` after activation, for audit. |
| `legacy_activation_completed` | bool | Gates the one-time activation (Rule 2). |
| `password_created_at` | datetime? | When the new-platform password was set. |

### Business rules the backend must enforce (UI mirrors them, cannot enforce them)
1. `legacy_activation_completed = false` → activation allowed.
2. `legacy_activation_completed = true` → activation rejected; UI tells the user
   to use Forgot Password.
3. Activation is **one-time only** (server-enforced; the verify endpoint is the
   gate).
4. After activation: `is_legacy_user` stays `true`; `legacy_activation_completed`
   becomes `true`.

---

## 4. Security responses to standardize

`authErrors.ts` maps HTTP status → user-facing message. Please return:

| Status | Meaning | UI message |
|--------|---------|-----------|
| 401 | Invalid credentials | "Incorrect username/email or password." |
| 403 | Account disabled | "This account is disabled. Contact your administrator." |
| 423 | Account locked (too many attempts) | "Temporarily locked. Try later or reset your password." |
| 429 | Rate limited | "Too many attempts. Please wait and try again." |
| 400 / 422 | Validation error | Backend `detail` is surfaced verbatim. |

Also relevant for production hardening: rotate/revoke refresh tokens on logout
(endpoint exists), and consider short-lived reset/activation tokens (single-use,
TTL) for §2.2–2.5.

---

## 5. Frontend integration map

| Workflow | Screen | Service call |
|----------|--------|--------------|
| Login | `src/pages/LoginPage.tsx` | generated `login()` + `getMeFull()` (via `AuthContext`) |
| Forgot password | `src/pages/ForgotPasswordPage.tsx` | `authExtrasService.forgotPassword` |
| Reset password | `src/features/auth/pages/ResetPasswordPage.tsx` | `validateResetToken`, `resetPassword` |
| Legacy activation | `src/features/auth/pages/LegacyActivationPage.tsx` | `legacyVerify`, `legacyCreatePassword` |

Shared service: `src/features/auth/services/authExtrasService.ts` (wraps the
shared axios instance). Once these endpoints ship, run `npm run api:sync` and the
service can be swapped to the generated Orval hooks.
