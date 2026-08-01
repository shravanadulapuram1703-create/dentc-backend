# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> The backend was rebuilt greenfield (see [ARCHITECTURE.md](ARCHITECTURE.md)). The
> previous POC lives in `legacy_app/` as **reference only** — never import from it.

## Commands

**Development server:**
```bash
dentc-env\Scripts\activate            # Windows  (source dentc-env/bin/activate on *nix)
uvicorn app.main:app --reload --port 8000
#   docs http://localhost:8000/docs · spec http://localhost:8000/api/v1/openapi.json
```

**Production (Gunicorn + PM2):**
```bash
gunicorn app.main:app -c gunicorn_config.py
pm2 start ecosystem.config.js
```

**Install / test / tooling:**
```bash
pip install -r requirements.txt
pytest                                 # full suite (in-memory SQLite, no DB needed)
python -m scripts.seed                 # dev tenant + super-admin
python -m scripts.export_openapi       # -> openapi.json for Orval
```

**Migrations (Alembic):** schema is owned by the models in `app/db/models/`.
```bash
python -c "from alembic.config import main; main(['revision','--autogenerate','-m','<msg>'])"
python -c "from alembic.config import main; main(['upgrade','head'])"
```
The current DB (`recondental_migrated`) is already stamped at the baseline revision.

**Environment:** `.env` — `DATABASE_URL` (or `DB_*` parts), `JWT_SECRET_KEY`, `REDIS_*`.

## Conventions

### API field naming — snake_case
The frontend UI operates on **snake_case**. All API field names, JSON keys, query
parameters, and OpenAPI schema property names must be snake_case. Never add `alias`
or `by_alias` that would convert to camelCase.

### Migration reference folder
`denticon_migration/` contains the Denticon→Dental-PMS migration scripts and the
authoritative DB schema (`migration/db/schema.sql`). **Reference-only** — don't
modify unless explicitly doing data-migration work.

---

## Architecture

**Stack:** FastAPI · SQLAlchemy 2.x (sync, `Mapped[]`) · Pydantic v2 · PostgreSQL · Alembic · Redis

**Entry point:** [app/main.py](app/main.py) — app factory; middleware order CORS →
`RequestContextMiddleware`; mounts the v1 router under `/api/v1`; registers exception
handlers; asserts unique `operation_id`s; injects the global `BearerAuth` scheme.

**Error contract:** every error is `{"error": {"code", "message", "details"}}`,
enforced by handlers in [app/core/exceptions.py](app/core/exceptions.py). Raise
`AppError` subclasses (`NotFoundError`, `ConflictError`, `ValidationError`, …).

### Multi-tenancy — COLUMN-BASED (not schema-per-tenant)
All 75 tables live in the `public` schema; root tables carry a `tenant_id` column.
Each request resolves `tenant_id` from the JWT via `get_tenant_id`
([app/api/deps.py](app/api/deps.py)); a `super_admin` may target another tenant with
the `X-Tenant-ID` header. `CRUDBase` filters every query by it. There is **no
`SET search_path`, no `tenant_{id}` schemas, and no TenantMiddleware.**

### The CRUD engine (how 75 entities stay maintainable)
- [app/crud/base.py](app/crud/base.py) — `CRUDBase`: generic, tenant-aware
  list/get/create/update/soft-delete (pagination, search, filter, sort).
- [app/schemas/factory.py](app/schemas/factory.py) — `build_schemas()` derives
  `Create`/`Update`/`Read` Pydantic models from an ORM model (named OpenAPI components).
- [app/crud/router_factory.py](app/crud/router_factory.py) — `register_crud()` emits
  the 5 standard routes with explicit `operation_id`s. **Must NOT use
  `from __future__ import annotations`** (the dynamic body annotation must be a real class).
- **Add an entity = add one `_cfg(...)` row** in
  [app/api/v1/registry.py](app/api/v1/registry.py). Entities with real rules get a
  service + a supplemental router (see `billing.py`, `treatment.py`).

### Auth & Security
JWT access+refresh pair at login. Refresh tokens whitelisted in Redis
(`refresh_token:{user_id}:{jti}`); access tokens blacklisted on logout
(`blacklist:access:{jti}`). [app/integrations/redis_store.py](app/integrations/redis_store.py)
degrades gracefully when Redis is off. Logic: [app/core/security.py](app/core/security.py)
+ [app/services/auth_service.py](app/services/auth_service.py).

### Authorization (Phase 1)
Single `users.role` varchar (`admin | provider | front_desk | staff | super_admin`).
Guard endpoints with `require_roles("admin")` from `app/api/deps.py`. Full RBAC
tables are deferred to Phase 4.

### Router layout (`/api/v1/...`)
Assembled in [app/api/router.py](app/api/router.py): `auth`, `users`, the billing /
treatment **service** routers, then every generated CRUD router from the registry.
Tags map to domains (Organization, Patients, Insurance, Procedures, Appointments,
Treatment Plans, Clinical, Billing, Metadata, Communications, Staff, Imaging) →
Orval `tags-split`.

### Database session
`get_db()` in [app/db/session.py](app/db/session.py) yields a sync `SessionLocal`,
closed in `finally`. Pool tuning (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, …) and a 30s
statement timeout are set there. Models register on `Base.metadata` via
`import app.db.models`.

### Phased roadmap
Phase 1 (org/patients/insurance/scheduling/treatment/codes), Phase 2 (clinical,
billing, reference, comms, staff, imaging + service overrides), and Phase 3
(audit logging + cached balances) are **implemented** — all 75 migrated tables
modelled, plus `audit_logs` (Alembic `a1b2c3d4e5f6`) and the Phase-4 user-access
tables `user_preferences`/`user_groups`/`user_group_memberships`/`user_ip_rules`
(Alembic `b2c3d4e5f6a7`) — **77 entities exposed as CRUD**.

**Frontend-alignment work** (see [docs/BACKEND_IMPLEMENTATION_PLAN.md](docs/BACKEND_IMPLEMENTATION_PLAN.md))
is implemented: list endpoints expose **typed, OpenAPI-visible filter params**
(generated from `filter_fields` via a dynamic signature in `router_factory.py`)
plus `{field}_from`/`{field}_to` date ranges; `GET /definitions?group_code=` drives
all dropdowns; `GET /patients/{id}/balance` is enriched (aging/estimates/recent
activity) and `GET /patients/{id}/ledger` gives a running-balance feed;
`POST /auth/signup` (new tenant + admin) and `GET /auth/me-full` round out auth.

**Account Information module** (Setup → Account Info; see
[docs/setup/account-info/ACCOUNT_INFO_IMPLEMENTATION.md](docs/setup/account-info/ACCOUNT_INFO_IMPLEMENTATION.md))
adds 5 tenant-scoped tables (`account_settings` 1:1, `account_communications` 1:1,
`office_phone_assignments`, `account_holidays`, `account_consents`; Alembic
`c3d4e5f6a7b8`) and routes under `/tenants/{tenant_id}/…`
([app/api/v1/account.py](app/api/v1/account.py)): account-settings, logo,
communications (+verify-telecom), phone-assignments, holidays (+federal/range/bulk),
consents (versioned + sanitized). Secrets (AI-assist secret, EIN) encrypted via
[app/core/crypto.py](app/core/crypto.py). Dropdown `group_code`s seeded by
`scripts/seed_account_definitions.py`.

**Direct Messaging module** (user-to-user DMs; gaps MSG-1…MSG-5 of
[docs/messaging_backend_devreport.md](docs/messaging_backend_devreport.md), wire
contract in [docs/api-contracts/MESSAGING_API_CONTRACT.md](docs/api-contracts/MESSAGING_API_CONTRACT.md)).
The **first WebSocket surface in the app** and the first non-CRUD real-time
subsystem, so it sits outside the registry entirely:
- 8 tables (`conversations`, `conversation_participants`, `messages`,
  `message_receipts`, `message_recipient_states`, `message_attachments`,
  `message_reactions`, `user_presence`; Alembic `c4d5e6f7a8b9`) in
  [app/db/models/messaging.py](app/db/models/messaging.py). Conversation/message ids
  are **UUIDv7** ([app/core/ids.py](app/core/ids.py)) so they are time-sortable —
  that is what makes keyset history pagination (`?before=`) work.
- REST in [app/api/v1/messaging.py](app/api/v1/messaging.py) + logic in
  [app/services/messaging_service.py](app/services/messaging_service.py).
  Sends are idempotent per `client_id`; conversations are get-or-create per user
  pair via `dedupe_key`.
- WS gateway `/api/v1/messaging/ws?token=` in
  [app/api/v1/messaging_ws.py](app/api/v1/messaging_ws.py). Auth is **query-string
  JWT decoded by hand** (browsers can't set headers on a WS handshake), so it
  bypasses `HTTPBearer`/`get_db` — it uses a `_session()` seam instead.
- Fan-out via Redis Pub/Sub on `msg:{tenant}:{user}`
  ([app/integrations/redis_pubsub.py](app/integrations/redis_pubsub.py) async
  subscriber + `redis_store.publish` sync publisher). **Falls back to in-process
  delivery without Redis** — fine for dev, but does not cross gunicorn workers.
- Presence in [app/services/presence_service.py](app/services/presence_service.py):
  Redis TTL keyed on the client's 30s heartbeat, socket refcount for multi-tab,
  `user_presence.last_seen_at` written on the transition to offline.
- **All ids serialize as strings** on the wire (the frontend compares them with
  `===` against auth-context values). MSG-6…MSG-11 (attachments, push, FTS search,
  rate limiting, audit) are not implemented.

**Add New Patient module** (gaps in
[docs/patients/add_patient_backend_devreport.md](docs/patients/add_patient_backend_devreport.md),
response in [docs/patients/add_patient_backend_response.md](docs/patients/add_patient_backend_response.md);
Alembic `d5e6f7a8b9c0`). Persists every previously-dropped Add-Patient field:
additive `patients` columns (`pronouns`, `driver_license`, `student_status`/
`school_name`, `preferred_hygienist_id`, `fee_schedule_id`, `referred_to`/
`referral_to_date`, `responsible_party_relationship`, `patient_types` JSON,
`assign_benefits`/`add_to_quickfill`/`no_correspondence`, `hipaa_sharing_notes`),
plus 3 tables (`patient_medical_alerts`, `patient_questionnaire_responses`,
`patient_opening_balances`). `chart_no` auto-generates when omitted via
`PatientCRUD` ([app/services/patient_service.py](app/services/patient_service.py)).
Opening A/R (`PUT/GET /patients/{id}/opening-balance`) folds into the computed
`/patients/{id}/balance`. Atomic `POST /patients/register`
([app/api/v1/patient_intake.py](app/api/v1/patient_intake.py) +
[app/services/patient_intake_service.py](app/services/patient_intake_service.py))
composes patient + responsible-party + alerts + questionnaire + recalls + opening
balance in one transaction. Shared `PatientCreate` schema lives in
[app/schemas/patient.py](app/schemas/patient.py).

**Legacy-parity extension** (LEG-1…14,
[docs/patients/add_patient_legacy_parity_devreport.md](docs/patients/add_patient_legacy_parity_devreport.md)
/ [response](docs/patients/add_patient_legacy_parity_response.md); Alembic
`e6f7a8b9c0d1`). Adds the standalone **`responsible_parties`** guarantor/billing
entity (demographics + per-account billing flags + `collection_agency_id` +
statement/financial notes + `resp_party_type`), creatable inline via
`POST /patients/register` (`responsible_party.person`) and exposed as CRUD;
`GET /responsible-parties/{id}/patients` is the account roster (balance/age/sex).
`chart_no` auto-gen is now collision-safe (probes `{id}`,`{id}-1`,…). Additive:
`patient-medical-alerts.response` enum (`yes|no|unknown`),
`patient_emergency_contacts.is_primary`, `definitions.section`,
`patient_insurance` Dentical-Share cols, `insurance_plans.anniversary_expiry_date`,
`patient_recalls.interval_unit`/`scheduled_date`/`scheduled_time`,
`insurance-plans?group_number=` + `GET /patients/{id}/account-plans`, and
`home_office_name`/`home_office_code` on `PatientRead` (LEG-16, via
`enrich_patient_office`). Catalog seeding (MEDALERT/DENTQUEST/MEDQUEST, LEG-1) and
outbound `referral_type="1"` practices (LEG-15) are deferred pending source data;
`resp_party_type` is seeded (provisional) via `seed_account_definitions.py`.

**Patient Overview module** (PO-1…12,
[docs/patients/patient_overview_backend_devreport.md](docs/patients/patient_overview_backend_devreport.md)
/ [response](docs/patients/patient_overview_backend_response.md); Alembic
`a8b9c0d1e2f3`). Aggregate `GET /patients/{id}/overview`
([app/api/v1/patient_intake.py](app/api/v1/patient_intake.py) +
[app/services/patient_overview_service.py](app/services/patient_overview_service.py))
composes patient+balance+responsible-party+account-members+appts+recalls+insurance+
referrals+contracts in one call (was ~20 requests). `GET /responsible-parties/{id}/patients`
now takes the **raw string** id (migrated legacy-guarantor accounts resolve) + returns
aging/estimates/visits per member (PO-3). Also: `GET /appointments/family` (PO-4),
`is_archived` filter on `/appointments` (PO-5), `legacy_id` filter on
`/responsible-parties` (PO-2b) + `/referrals` (PO-6), `responsible_parties.legacy_id`/
`home_office_id` (PO-2b/11), `patients.photo_document_id` (PO-10), single-letter
`resp_party_rel` seed codes (PO-9), `GET /patients/{id}/insurance-plans` alias (PO-12).
PO-2a/6-backfill/7/8-populate remain migration-only data tasks (API enablers shipped).

**Edit Patient module** (PE-1…4,
[docs/patients/patient_edit_backend_devreport.md](docs/patients/patient_edit_backend_devreport.md)
/ [response](docs/patients/patient_edit_backend_response.md); Alembic `c0d1e2f3a4b6`).
`patients.updated_by` ("Modified By", stamped by `CRUDBase.update`) + `created_by_name`/
`updated_by_name` on `PatientRead` (via `enrich_patient_office`, PE-4); `opening_balance`
folded into `GET /patients/{id}/context` (PE-3); `patient_type` catalog seeded
(CH/CP/EF/OR/SN/SR/SS/UP, PE-2). PE-1: `patient_types` JSON is the canonical home for the
patient-type multi-select (the FE-only `patient_flags` shape has no backend columns).

**Payment Plans module** (Ortho + Regular contracts; PP-1…8, OPP-1…11, RPP-1…6 of
[docs/payment-plans/payment_plans_backend_devreport.md](docs/payment-plans/payment_plans_backend_devreport.md)
/ [response](docs/payment-plans/payment_plans_backend_response.md); Alembic
`e1f2a3b4c5d6`). `ortho_plans` + `patient_payment_plans` gain every legacy column
(two billing codes — `procedure_code` **is** the periodic one, `initial_procedure_code`
the banding one; `pref_provider_id`; patient-sub-plan setup date/notes/remarks; a
secondary insurance tier symmetric with the primary; `tx_plan_amt` +
`treatment_plan_id` FK; `billing_code`; `financial_disclosure`; `total_of_payments`;
`created_by_id`/`updated_by`/`created_office_id`) plus a **tokenised** payment-method
block — `payment_token_id`/`card_last4`/exp only, **never a PAN or CVV**.
New `patient_plan_installments` (OPP-9/RPP-5) is the patient-side instalment store
for both contract kinds (`plan_side` discriminator); `patient_ins_payment_plans`/
`patient_sec_ins_payment_plans` gain `ortho_plan_id` (PP-6). Non-CRUD surface in
[app/api/v1/payment_plans.py](app/api/v1/payment_plans.py) +
[app/services/payment_plan_service.py](app/services/payment_plan_service.py):
`POST /{instalment-table}/{id}/post` and `POST /payment-plans/post-due` write a real
`patient_procedures` charge and stamp `is_billed`/`ledger_id` (PP-2 — 409 on
re-post, never double-charges); `…/installments/generate` amortises the contract
server-side (last instalment absorbs the rounding residue); `…/contract(.pdf)` and
`…/coupons.pdf` render the Truth-in-Lending contract via **reportlab** (lazy import).
PP-1: `CrudConfig.hide_soft_deleted` (opt-in, on the three contract resources) keeps
soft-deleted rows out of the default listing — `?is_active=false` still surfaces them.
PP-4: **`patient_payment_plans` is canonical**; `patient_reg_plans` is migration-only.
PP-5: the balance aggregate is 2 index-backed scans instead of 6 statements, and a
post invalidates the Redis cache.

**AppointNow module** (external online booking; AN-1…13 of
[docs/book/appointnow_backend_devreport.md](docs/book/appointnow_backend_devreport.md);
Alembic `b3c4d5e6f7a8`). The app's **first anonymous public surface** — an
embeddable, login-free booking page resolves the tenant from `office_code` (never
a JWT, and never 401 → AN-12) and lets external patients request a slot; staff
approve/decline from an authed inbox. Two tables in
[app/db/models/appointnow.py](app/db/models/appointnow.py): `appointnow_reasons`
(per-office reason→duration catalog, generic CRUD; a built-in default catalog is
served when an office customises none) and `booking_requests` (UUIDv7 string PK so
the inbox pages chronologically by id; a `hold_expires_at` soft-hold, AN-8).
Logic in [app/services/appointnow_service.py](app/services/appointnow_service.py),
routes split into `public_router` (unauth, AN-1..3) + `staff_router` (auth,
AN-4..5,9) in [app/api/v1/appointnow.py](app/api/v1/appointnow.py). The
**availability engine** mirrors the frontend reference: office window
(`office_schedule_days`, else the office default hours) ∩ provider window
(`provider_schedule_days`) − holidays (`account_holidays` + `provider_holidays`) −
booked appointments − active holds, sliced into `slot_interval_minutes`, timezone-
correct for "today" (AN-10), short-TTL Redis-cached (AN-2). Intake (AN-3) is
per-IP/office rate-limited (`incr_counter`), optionally Turnstile-gated
(`APPOINTNOW_TURNSTILE_SECRET`), re-validates the slot at submit, and soft-holds
it. **Approve is atomic** (AN-5): re-check → book a real `appointments` row →
link `appointment_id` → mark `approved`, with optional duplicate-patient match/
create (AN-9, `GET …/requests/{id}/patient-matches`). The inbox (AN-4/AN-13) does
server-side `q`/reason/`is_new_patient`/slot-date-range filter + sort + paging and
returns an unfiltered per-status **count summary** for the tab badges.
`Provider.visible_in_appointnow` (AN-7) gates which providers are offered. AN-6
(realtime push) ships only a best-effort publish seam on `appointnow:{tenant}:{office}`
— no WS consumer yet (the FE `subscribe()` is a no-op, falls back to Refresh);
AN-11 (per-practice CORS / iframe `frame-ancestors`) is deploy-config, not code.

**Help Center support tickets** (Help → Report an Issue → Jira; HELP-1…5 of
[docs/help/help_module_backend_devreport.md](docs/help/help_module_backend_devreport.md)
/ [response](docs/help/help_module_backend_response.md)). `POST/GET /api/v1/support/tickets`
([app/api/v1/support.py](app/api/v1/support.py) +
[app/services/support_service.py](app/services/support_service.py)) file and list
support tickets. Every submission is **persisted durably** to `support_tickets`
([app/db/models/platform.py](app/db/models/platform.py), Alembic `b0c1d2e3f4a5`) with
the reporter stamped from the **token** (HELP-3 — client `context.user_id` is display
metadata only). All outbound Atlassian REST calls are isolated in
[app/integrations/jira_client.py](app/integrations/jira_client.py): when
`JIRA_BASE_URL`+`JIRA_EMAIL`+`JIRA_API_TOKEN` (the `JIRA_*` block in
[config.py](app/core/config.py)) are set the issue is created in Jira Cloud (REST v3)
with the FE-built **ADF** description, attachments (base64→multipart,
`X-Atlassian-Token: no-check`) are uploaded, and the list read **syncs live status**
(Jira workflow → Open|In Progress|Done, persisted); otherwise the ticket lives locally
with a `LOCAL-<id>` key (zero-config dev/test — `is_configured()` False). A configured-
Jira create failure persists `status="Failed"` and returns **502** so the FE retries.
Live cutover = fill the three env secrets + `VITE_JIRA_MODE=proxy`, no code change.

**Phase 3 specifics:**
- **Audit logging (HIPAA):** `AuditMiddleware` ([app/middleware/audit.py](app/middleware/audit.py))
  records authenticated 2xx mutations (POST/PUT/PATCH/DELETE) to `audit_logs` via
  [app/services/audit_service.py](app/services/audit_service.py) — exception-safe,
  never breaks a request. Read API: `GET /audit-logs` (admin-only,
  [app/api/v1/audit.py](app/api/v1/audit.py)).
- **Cached balances:** `GET /patients/{patient_id}/balance`
  ([app/api/v1/balances.py](app/api/v1/balances.py)) → `balance_service` computes
  charges − payments and caches in Redis (30s TTL) via `redis_store.cache_*`.

Phase 4 = full RBAC, EDI claims, AI chat, optional schema-per-tenant.
