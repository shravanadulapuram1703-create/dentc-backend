# Authentication — Backend Response to FE Dev Report

_Module: Authentication. Backend response to `authentication_backend_devreport.md`._
_Date: 2026-06-07._

All five missing endpoints (§2.1–2.5) are now **implemented**, the new user-model
fields (§3) are **added**, and the standardized login security responses (§4) are
**in place** (401/403/423). Field naming stays snake_case throughout.

> Run `python -m scripts.export_openapi` → `npm run api:sync` (Orval) to generate
> the typed client, then `authExtrasService` can be swapped to the generated hooks.

---

## ✅ §2.1 Forgot password — DONE

`POST /api/v1/auth/forgot-password`
- **Request:** `{ "email": "" }`
- **Response:** `200` `{ "message": "If an account exists for that email, a reset link has been sent." }`
- **Always 200**, identical message whether or not the email exists (no account
  enumeration). When the account exists and is active, a single-use reset token is
  created and a reset email is dispatched.

> **Email delivery:** sent via `app/integrations/email.py`. The default transport
> is **log-only** (logs the reset link) — production SMTP/provider wiring is a
> separate infra task and does not change this contract. The reset link points at
> `PASSWORD_RESET_URL_BASE` (configurable; default `…/reset-password?token=`).

## ✅ §2.2 Reset password — validate token — DONE

`POST /api/v1/auth/reset-password/validate`
- **Request:** `{ "token": "" }`
- **Response:** `200` `{ "valid": true, "email": "user@x.com" }` (`email` null when invalid)

## ✅ §2.3 Reset password — submit — DONE

`POST /api/v1/auth/reset-password`
- **Request:** `{ "token": "", "new_password": "" }` (`new_password` ≥ 8)
- **Response:** `200` `{ "message": "Your password has been reset…" }`
- **`422`** `{ error.code: "invalid_reset_token" }` when the token is invalid/expired/used.
- Side effects: sets the new hash, clears `must_change_password`, stamps
  `password_created_at`, and **consumes the token (single-use)**.

## ✅ §2.4 Legacy activation — verify — DONE

`POST /api/v1/auth/legacy-user/verify`
- **Request:** `{ "username_or_email": "" }`
- **Response (eligible):**
  ```json
  {
    "eligible": true,
    "legacy_activation_completed": false,
    "verification_method": "email",
    "masked_email": "s•••@dental.local",
    "activation_token": "<raw token>"
  }
  ```
- Not a legacy user / inactive / not found → `{ "eligible": false, … "activation_token": null }`.
- Already activated → `{ "eligible": false, "legacy_activation_completed": true, … }`
  (UI blocks with "already activated" → Forgot Password — Business Rule 2).
- `verification_method` is currently `"email"`. The contract supports
  `"otp" | "magic_link"`; those channels are a follow-up (the field is already in
  the response so the FE need not change when they land).

## ✅ §2.5 Legacy activation — create password — DONE

`POST /api/v1/auth/legacy-user/create-password`
- **Request:** `{ "username_or_email": "", "new_password": "", "activation_token": "" }` (`new_password` ≥ 8)
- **Response:** `200` `{ "message": "Your account is activated…" }`
- **`422`** when the token is invalid/expired/used, doesn't match the named user,
  or the account is already activated (`error.code: "already_activated"`).
- Enforces **Business Rules 3 & 4**: one-time only (token consumed); on success
  `legacy_activation_completed = true` while `is_legacy_user` stays `true`.

---

## ✅ §3 User-model fields — ADDED

`UserRead` now also exposes (alongside the existing `is_active`,
`must_change_password`, `last_login_at`, `role`, `created_at`):

| Field | Type | Notes |
|-------|------|-------|
| `is_legacy_user` | bool | Stays `true` after activation (audit). |
| `legacy_activation_completed` | bool | Gates the one-time activation (Rule 2). |
| `password_created_at` | datetime? | Set when the new-platform password is created. |

DB: Alembic `b9c0d1e2f3a4` adds these columns to `users` and creates
`auth_action_tokens` (single-use, TTL-bounded, SHA-256-hashed tokens for reset +
activation). Run `python -c "from alembic.config import main; main(['upgrade','head'])"`.

---

## ✅ §4 Security responses — STANDARDIZED

| Status | When | `error.code` |
|--------|------|--------------|
| 401 | Invalid username/email or password | `invalid_credentials` |
| 403 | Account exists but is disabled (`is_active = false`) | `account_disabled` |
| 423 | Too many failed attempts (lockout) | `account_locked` |
| 400/422 | Validation error (`detail` surfaced verbatim) | `validation_error` |

- **403:** login now distinguishes a disabled account from bad credentials (was
  previously 401). 
- **423 lockout:** after `LOGIN_MAX_FAILED_ATTEMPTS` (default 5) failures within
  `LOGIN_LOCKOUT_MINUTES` (default 15), login returns 423 until the window
  expires; a successful login clears the counter. **Backed by Redis** and
  **degrades open** — if Redis is unavailable the lockout is skipped (an outage
  never blocks all logins). Both thresholds are env-configurable.
- All error bodies use the standard envelope `{"error": {"code","message","details"}}`,
  so `authErrors.ts` can map on `status` (and refine on `error.code`).

### 429 (rate limiting) — note
Per-IP request rate limiting is best enforced at the gateway/reverse-proxy
(or a dedicated middleware) rather than in the auth service; it's **not** added
here. The 423 account-lockout above covers the brute-force-on-one-account case.
`authErrors.ts` can keep its 429 mapping for when the gateway returns it.

---

## Token security notes (addressing §4 "production hardening")
- Reset & activation tokens are **single-use** and **TTL-bounded** (reset 60 min,
  activation 24 h — both configurable), stored only as SHA-256 hashes in
  `auth_action_tokens`. Raw values are never persisted.
- Logout already revokes/blacklists tokens (unchanged).

## CORS — deployed login failure (follow-up fix)

The reported browser error —
`Access to XMLHttpRequest at '…/api/v1/auth/login' … blocked by CORS policy: No
'Access-Control-Allow-Origin' header is present` — had **two** causes, both now fixed:

1. **Origin not allowed.** Default `CORS_ORIGINS` was `["*"]`, which a browser
   rejects for credentialed requests, and the Cloud Run frontend origin wasn't
   explicitly listed. Fixed by:
   - `CORS_ORIGINS` now defaults to the local dev origins (exact match), and
   - a new `CORS_ORIGIN_REGEX` (default `https://.*\.run\.app`) that matches the
     Cloud Run frontend (whose URL carries a project-number hash). With
     credentials enabled, the server now echoes the **specific** origin +
     `Access-Control-Allow-Credentials: true` (never `*`).
2. **CORS headers missing on error responses.** The CORS middleware was added
   *first* (innermost), so when `/auth/login` 500'd (it did — see below), the
   error response carried no `Access-Control-Allow-Origin`, surfacing in the
   browser as a CORS error. CORS is now the **outermost** middleware, so even
   4xx/5xx responses carry the header.

### Root cause of the underlying 500
The deployed DB was at Alembic `b8c9d0e1f2a3`; the auth migration adding
`users.is_legacy_user` (et al.) had **not** been applied, so every user query
(including login) failed with `UndefinedColumn`. **Applied `b9c0d1e2f3a4` to the
dev DB** (`recondental_migrated`) — login now returns a clean `401` with CORS
headers.

> **Deploy checklist:** (a) ship this backend build; (b) ensure
> `alembic upgrade head` has run against the target DB; (c) for any non-Cloud-Run
> frontend host, set `CORS_ORIGINS` (comma-separated) on the backend service.

## Summary

| § | Item | Status |
|---|------|--------|
| 2.1 | Forgot password | ✅ `POST /auth/forgot-password` |
| 2.2 | Validate reset token | ✅ `POST /auth/reset-password/validate` |
| 2.3 | Reset password | ✅ `POST /auth/reset-password` |
| 2.4 | Legacy verify | ✅ `POST /auth/legacy-user/verify` |
| 2.5 | Legacy create-password | ✅ `POST /auth/legacy-user/create-password` |
| 3 | User fields | ✅ `is_legacy_user`, `legacy_activation_completed`, `password_created_at` |
| 4 | 401 / 403 / 423 | ✅ standardized error codes |
| 4 | 429 rate limit | ⚠️ gateway-level (documented), not in-service |
| — | Email delivery | ⚠️ log-only transport; SMTP wiring pending |
