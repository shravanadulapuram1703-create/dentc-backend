# Account Information — Backend Implementation (DONE)

> Implements `ACCOUNT_INFO_BACKEND_MAPPING.md` + `backend_devreport.md` gaps **#1a, #2, #4, #5, #6, #7, #8, #9** (the Setup → Account Info section only). Scope was limited to this module; Offices/Office-Groups/Security/Providers gaps (#10–#20) are untouched.
> All tables are `tenant_id`-scoped (Tenant = Account) → multi-account scales automatically. Verified: app builds (183 paths, 424 unique operationIds), **90 tests pass** (6 new), live + sqlite smoke green.

---

## 1. Database (new tables, Alembic `c3d4e5f6a7b8`, applied to `recondental_migrated`)

| Table | Cardinality | Backs |
|---|---|---|
| `account_settings` | 1:1 tenant (80 cols) | Basic + Advanced tabs |
| `account_communications` | 1:1 tenant | Communications tab |
| `office_phone_assignments` | N per tenant | Communications → phone assignment |
| `account_holidays` | N per tenant | Holidays tab |
| `account_consents` | versioned per tenant | Online Registration tab |

- Created from the SQLAlchemy model metadata (`app/db/models/account.py`) so the migration never drifts from the models. Downgrade drops all five. Additive — **no migrated table was altered**.
- FKs into existing resources: `ortho_visit_code → procedure_codes.code`, `model_office_id` / `transworld_office_id → offices.id`; code dropdowns (`*_code`, ledger colors, `payment_portal_posting_office`) stored as string values referencing `definitions`/`chart-colors`/`offices` (soft refs, sentinels allowed).
- Reference data: `scripts/seed_account_definitions.py` seeds **20 `definitions` group_codes** (111 rows/tenant, idempotent).

## 2. Endpoints (all under `/api/v1/tenants/{tenant_id}/…`, JWT + tenant-guarded)

| Tab | Endpoints |
|---|---|
| Basic+Advanced | `GET/PATCH /account-settings` · `POST/DELETE /logo` |
| Communications | `GET/PATCH /communications` · `POST /communications/verify-telecom` · `GET/PUT /phone-assignments` |
| Holidays | `GET/POST /holidays` · `PATCH/DELETE /holidays/{id}` · `POST /holidays/bulk-delete` · `POST /holidays/federal` · `POST /holidays/range` |
| Online Registration | `GET /consents` · `GET /consents/active` · `POST /consents` · `GET /consents/{id}` · `GET /consents/{id}/preview` |

The path `{tenant_id}` must equal the authenticated/effective tenant (`super_admin` may target another via `X-Tenant-ID`); mismatch → `403`. Tenancy is also enforced in every service by `tenant_id`.

## 3. Gap resolution

| Gap | Resolution |
|---|---|
| **#1a** account settings | `account_settings` (1:1) + `GET/PATCH /account-settings`. Row auto-created on first access (upsert). All ~70 Basic/Advanced fields persisted. |
| **#2** PATCH verb | Confirmed: updates are `PATCH` (account-settings, communications, holidays). FE switches PUT→PATCH. |
| **#4** logo | `POST /logo` (multipart, validates JPG/PNG ≤2 MB) stores the file and sets `logo_url`; `DELETE /logo` clears it. Served via the static mount. |
| **#5** holidays | Full CRUD + `bulk-delete` + `federal` (computes the 11 US federal holidays for a year, dedup-safe) + `range` (one row/day, dedup-safe). |
| **#6** communications | `communications` settings (EIN encrypted, returned masked) + `verify-telecom` (records status — see blocker) + `phone-assignments` (PUT replace, **max-5 Office-Specific** rule enforced). |
| **#7** consents | Versioned: each `POST` creates a new version and auto-archives the prior active one; `body_html` is sanitized (XSS) on write; `active` + `preview` reads. |
| **#8** audit / pgid / oid | `updated_at` + `updated_by` + `pgid` + `oid` live on `account_settings` (the migrated `tenants` table is intentionally left unaltered). |
| **#9** lookups | 20 canonical group_codes seeded + documented (below). |

## 4. Canonical `definitions` group_codes (for FE dropdown binding)

`state`, `country`, `culture`, `theme`, `charting_option`, `charting_tab`, `edi_vendor`, `holiday_status`, `holiday_type`, `business_type`, `company_status`, `stock_exchange`, `required_field_mode` (shared by phone/dob/ssn modes), `ortho_claim_fee_mode`, `default_treatment_plan_filter`, `pronoun_field_visible`, `comm_number_type`, `payment_method`, `adjustment`, `claim_status`.

Bind via `GET /api/v1/definitions?group_code=<code>` (`key1` = value, `description` = label). `business_industry` is intentionally a free-text field (not seeded).

## 5. Secrets & validation

- **Encrypted at rest** (Fernet, `app/core/crypto.py`): AI-assist client secret (write-only, never returned — `ai_assist_has_secret` flag instead) and EIN (returned masked to last 4). Key from `ENCRYPTION_KEY` env, else derived from `JWT_SECRET_KEY`.
- Logo type/size validation; phone max-5 rule; consent HTML sanitization; password-expiry/discount bounds via schema.

## 6. Blockers / assumptions (deliverable #5)

1. **Logo storage** uses the local filesystem (`UPLOAD_DIR`, served at `/uploads`). **Assumption / future work:** swap for object storage (S3/GCS) in production — only `account_service.save_logo`/`delete_logo` change; the API contract (`{logo_url}`) stays.
2. **Telecom verification** (`verify-telecom`) is a **stub** that records `telecom_status="submitted"` + timestamp. The real TCR/Twilio provider sync is a separate integration (out of this module's scope).
3. **Consent PDF** (`/consents/{id}/pdf` in the speculative spec) is **not implemented** — needs an HTML→PDF library. `preview` (returns sanitized header+body) is provided; the production screenshot shows only Header+Body+Save, so PDF/Preview may not be required — **confirm with product**.
4. **pgid/oid/audit on `account_settings`, not `tenants`** — chosen to avoid altering the migrated core table. If the FE expects them on `TenantRead`, we can surface them there too (decision needed).
5. **Code-ref fields stored as strings** (e.g. `treatment_plan_discount_code`) rather than hard FKs to `definitions`, because `definitions` keys are `(group_code, key1)` not a single PK. Values validate against the seeded group_codes client-side.
6. **HTML sanitizer is a pragmatic regex pass** (strips script/style/iframe/on*/javascript:). For hardened production, swap in `nh3`/`bleach` behind `sanitize_html()`.
