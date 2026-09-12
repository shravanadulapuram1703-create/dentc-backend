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

**Full-wizard registration pass** (GAP-AP-19…26 of
[docs/patients/add_patient_full_wizard_backend_issues.md](docs/patients/add_patient_full_wizard_backend_issues.md)
/ [response](docs/patients/add_patient_full_wizard_backend_response.md); Alembic
`b317b3c05b47`, **applied to the dev DB**).
- **GAP-AP-20 had three halves, not one**: `alert_code`/`question_code` were
  `VARCHAR(50)` with no `max_length`, so the 12 legacy questions whose derived
  slug runs 51–60 chars were a 500 that rolled back the whole registration.
  Columns widened to **100** — *including* `medical_history_details.question_code`,
  because the MH-6 signed snapshot copies both codes into it and a widened source
  with an unwidened sink only moves the 500 to `/sign`. The FE clamped its
  `toCode` to 50, and the backend's own `to_code` (which keys the built-in
  catalogs the Medical History document resolves answers against) still sliced
  at 60 — left alone, the 12 answers would have read as Not Answered.
  `medical_history_catalog.CODE_MAX_LENGTH = 50` is the derivation cap;
  `patient_catalog.CATALOG_CODE_MAX_LENGTH = 100` is the storage bound; both
  published on `/metadata/medical-history-rules → code_convention`.
- **GAP-AP-21** `POST /patients` had no duplicate guard at all, so the FE's
  fallback path created the duplicate the composite had just refused.
  `PatientCRUD.create` now runs `patient_extra_service.raise_if_duplicate`
  (same 409, same `candidates[]`, + `override_field`) and `PatientCreate` gains
  `force_create` (not a column). **Placeholder identifiers never match**
  (`is_synthetic_identifier`: all-one-digit, keyboard runs, the never-issued
  SSNs, SSA-impossible area/group/serial) — the dev DB's shared `123456789` /
  `123456` had been blocking every registration. A real SSN/chart-no needs one
  corroborating field (last name or DOB) to be *strong*; a lone hit is still
  reported.
- **GAP-AP-22** `POST /patient-medical-alerts/bulk` + `/patient-questionnaire-responses/bulk`
  (one transaction, upsert by code, `replace`, ≤500). Built on
  `medical_history_service.apply_alert_answers` / `apply_questionnaire_answers`
  — the **non-committing** reconcile now shared by the composite `PUT
  …/medical-history`, the bulk endpoints **and `POST /patients/register`**,
  which had been writing bare rows past MH-12/MA-3/MH-8/MH-14. `alert_flags`
  is cached per session (`Session.info`, invalidated by any flush touching
  `definitions`/`definition_groups`); it was read three times per single-row
  write against a remote DB.
- **GAP-AP-23/24** `RecallIn` carries the LEG-8 trio (LEG-17 closed) and
  `RegisterRequest.insurance[]` = `{subscriber | subscriber_id,
  subscriber_is_patient, link}` per slot, applied **primary-first regardless of
  payload order** so `validate_coverage_slot` judges the set; results in
  payload order; every failure a 422 with `details.index`. The two register
  components are factory-derived from `InsuranceSubscriber`/`PatientInsurance`
  with the transaction-supplied ids excluded.
- **GAP-AP-25** `resp_party_rel` was seeded twice (lowercase keys + the PO-9
  single-letter codes). **The code is canonical** and the column now holds it:
  `patient_rules_service.normalize_resp_party_relationship` folds key/label/code
  on every write (unknown stored as written — the PROV-3 call), the migration
  normalised stored rows and **deactivated** (not deleted — Setup-editable, and
  the FE hooks pass `is_active=true`) the lowercase set; the seeder gained a
  `RETIRED_KEYS` step. Published on `/metadata/patient-flag-rules`.
- **GAP-AP-26** `app.core.exceptions.app_error_from_db` maps `DataError` →
  422 (`value_too_long` w/ `max_length`, `value_out_of_range`, `invalid_value`)
  and `IntegrityError` → 409 `constraint` (unique) / 422
  (`foreign_key_violation`, `not_null_violation`, `check_violation`), naming
  table/column/constraint from the Postgres `diag` block or the SQLite message;
  used by global handlers **and** `CRUDBase._commit`/`_flush` (which had 409'd
  every kind as the generic `conflict` with the raw driver string — **breaking**:
  a DB unique collision is now code `constraint`). Genuine 500s carry
  `details.request_id`; `CatchAllMiddleware` reads it off `request.state`
  because it sits outside `RequestContextMiddleware`'s contextvar scope.
- **GAP-AP-19** `patients.middle_name` + `responsible_parties.middle_name`;
  `middle_initial` is derived (`fold_middle_name`) unless sent explicitly, and
  a derived initial is cleared with the name while a typed one survives.

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

**Transactions module** (Dashboard + global feed + charge/payment/refund entry; DASH-1…5,
SRCH-1/3, LED-1, INS-1, ADJ-1, REF-1…4, STMT-1…3, AUD-1…3, SVC-1, CHG-1…9 of
[transactions/transactions_backend_devreport.md](transactions/transactions_backend_devreport.md)
/ [response](transactions/transactions_backend_response.md); Alembic `c7d8e9f0a1b2`). The
office-level financial layer the per-patient endpoints never had, plus refunds/statements
which had **no** backend at all:
- **Office dashboards** ([app/api/v1/transactions.py](app/api/v1/transactions.py) +
  [app/services/transactions_service.py](app/services/transactions_service.py)):
  `GET /offices/{id}/financial-summary` (DASH-1), `/collections?period=` (DASH-2),
  `/insurance-receivables` (DASH-3, total + by-carrier), `/adjustment-summary?period=`
  (DASH-4, split by `write_off_type`), `/transactions` (DASH-5). Tenant-wide
  `GET /transactions?search=&type=&status=&amount_min=&amount_max=&transaction_number=`
  is the unified cross-patient feed (SRCH-1/3) composing charges+payments+adjustments+
  refunds+claims, denormalised + paged. `patient_payments`/`insurance_claims`/
  `patient_procedures` carry no `tenant_id`, so tenancy is enforced via the patient-id set.
- **Refunds** ([app/api/v1/refunds.py](app/api/v1/refunds.py) +
  [app/services/refund_service.py](app/services/refund_service.py)): first-class
  `patient_refunds` — never an ad-hoc negative payment. `POST /patients/{id}/refunds`
  (REF-1, policy-checked), `/patient-{payments,adjustments}/{id}/reverse` (REF-2),
  `GET /patients/{id}/refundable-balance` (REF-3), `GET /metadata/refund-policy` (REF-4).
  A refund folds into the computed balance (`balance += refund`; **`balance_service` now
  nets `payments − refunds`** and exposes `total_refunded`/`credit_balance`).
- **Statements** ([app/api/v1/statements.py](app/api/v1/statements.py) +
  [app/services/statement_service.py](app/services/statement_service.py)): `patient_statements`
  snapshot rows. `POST /patients/{id}/statements` (STMT-1), `…/{sid}/pdf` (reportlab, STMT-3),
  `…/{sid}/deliver`, `POST /offices/{id}/statements/batch` (STMT-2, outstanding/aged filter,
  office aging messages consumed). Email delivery records intent only (no SMTP wired).
- **Billing supplements** ([app/api/v1/billing.py](app/api/v1/billing.py) +
  [app/services/billing_service.py](app/services/billing_service.py)):
  `POST /ledger-insurance-details/payment` adds check/bank/EOB/EFT-trace remittance ids
  (INS-1); `POST /insurance-claims/{id}/submit` (SVC-1) + `GET …/status-history` (AUD-3,
  composed from `audit_logs` + claim date columns); `POST /patients/{id}/estimate` is the
  coverage+fee-schedule estimate engine (CHG-1/7,
  [app/services/estimate_service.py](app/services/estimate_service.py));
  `GET /patients/{id}/insurance-summary` (CHG-8), `/todays-appointment` (CHG-9),
  `GET /explosion-codes/{code}/expand` (CHG-4).
- **Ledger/audit**: `GET /patients/{id}/ledger` gains `transaction_type`/`status`/`sort_by`/
  `sort_order` (LED-1) + `created_by`/`created_at`/`provider_name` per row (AUD-2);
  `GET /audit-logs?resource_id=` (AUD-1). Additive columns: `patient_payments.bank_number`
  (CHG-5), `patient_procedures.hygienist_id` (CHG-6), `patient_adjustments.write_off_type`
  (ADJ-1), `procedure_codes.{anatomy,surface,material}_rules` JSON (CHG-2). CHG-3 ("All
  Medical" CPT codes) stays a data-seeding task (the category filter already works).

**Transactions second pass** (ADJ-1 allocation, CHG-5 rollups, PROV-1/2 of
[docs/transactions_backend_devreport.md](docs/transactions_backend_devreport.md) /
[response](transactions/transactions_backend_response_2.md); Alembic `d8e9f0a1b2c3`):
- **PROV-1** a provider is multi-office, so `GET /providers?office_id=` now matches the
  **union** of `provider_offices` and the legacy `providers.office_id` home scalar —
  `ProviderCRUD` in [app/services/provider_directory_service.py](app/services/provider_directory_service.py),
  on the engine's new `CRUDBase.custom_filter_fields`/`_extra_list_clauses()` seam (a
  declared filter the subclass resolves itself). `GET /offices/{id}/providers/effective`
  returns that union; `GET/PUT …/providers` stays the assignment grid (GET mirrors PUT).
  `scripts/backfill_provider_offices.py` reconstructs the unseeded join from the home
  scalar + where the provider actually produced/was scheduled.
- **ADJ-1** an adjustment splits across procedures through the *same* table as a payment:
  `payment_allocations.adjustment_id` + `POST /patient-adjustments/{id}/allocate`
  (over-allocation/foreign-procedure/void guards, `replace` re-issues the split).
- **CHG-5** `PatientProcedureRead` carries `paid_to_date`/`insurance_paid_to_date`/
  `adjusted_to_date`/`remaining_amount` ([app/services/procedure_totals_service.py](app/services/procedure_totals_service.py)
  via the `enrich_patient_procedure` hook — an adjustment counts through its split *or*
  its scalar `procedure_id`, never both), plus
  `GET /patient-procedures/{id}/allocations-summary`. **PROV-2** was a stale `openapi.json`
  (regenerated). CHG-3 keeps its data-task status; `scripts/seed_medical_codes.py` loads a
  practice-supplied CSV (CPT is AMA-licensed, so no list is bundled).

**Transactions third pass** (FEE-1/2/3, CHG-10, PROV-3 of
[docs/transactions/transactions_backend_devreport.md](docs/transactions/transactions_backend_devreport.md)
/ [response](docs/transactions/transactions_backend_response_3.md); Alembic
`d3e4f5a6b7c8`). The pricing half of the module — everything the first two passes
computed *with*:
- **FEE-1 is the load-bearing fix**: every coverage percentage lives in
  `insurance_coverage_rules` (876,732 rows) banded on **Denticon coverage-category
  codes** (`01`, `01A`, `03A`, `11B`), while a charge carries an ADA code — so
  `estimate_service` compared `"D2393"` against the band `"03"`–`"03"`, matched
  nothing, and returned **0 % insurance on every migrated plan**. (A minority of
  plans band on real ADA ranges, `D0100`–`D0999`; those always worked, which is why
  the bug looked intermittent.) The link cannot be re-read — Denticon's
  `Codes.INSCATEGORYID` was consumed by migration step `s10` for the display label
  and dropped — so it is reconstructed from the published **CDT family ranges**, the
  same taxonomy `seed_procedure_code_rules.py` uses. New
  `procedure_codes.coverage_category` (+ `?coverage_category=` filter); the range
  table lives once in [app/services/coverage_category_service.py](app/services/coverage_category_service.py)
  so seeder / engine / `GET /metadata/coverage-categories` cannot drift.
  `_match_rule` matches a band as an ADA range **or** by category and is **ranked,
  not first-wins** — an exact sub-category outranks its parent, so a crown prices at
  the plan's `03A` 50 % rather than `03`'s 80 % (rows come back in insertion order,
  so first-wins made the answer depend on how the plan was typed in). Applied:
  722/1,122 codes classified, **only 2 D-shaped codes unmapped**; verified live —
  `D2393` @ 131.00 now returns **104.80 (80 %)**, previously `0.00`. This is also the
  blocker treatment-plan **PLAN-3** shares. An unmapped code stays **NULL**, never
  `12` "Non-covered Services" — "unknown" and "denied" are different answers, and
  the 167 medical/CPT codes are the former.
- **FEE-3** fee resolution existed only in the frontend, so two clients could
  disagree and nothing stopped a charge posting at an arbitrary fee.
  [app/services/pricing_service.py](app/services/pricing_service.py) is the same
  algorithm server-side (assignment specificity → plan-linked → office default →
  code default; ties → newest row; inactive excluded) behind **three** callers so
  they cannot diverge: `GET /patients/{id}/fee` (returns *how* it resolved, and
  reports equally-specific `conflicts` instead of silently picking one), the estimate
  engine, and the write path — `PatientProcedureCreate.fee` is now **optional** and
  an omitted fee is priced server-side. An explicit fee always wins: an office may
  charge what it decides to charge.
- **CHG-10** `key2` was NULL on all `payment_method`/`adjustment` definitions across
  all 43 tenants, so the pickers had nothing to group by. The cause was structural —
  `seed_account_definitions.py` is add-only and its row shape has no `key2` slot, so
  it could never have fixed them. New `scripts/seed_transaction_definitions.py` owns
  both groups, **patches existing rows**, and widens them (5→11 methods, 3→12
  adjustments); the account seeder delegates to it. `payment_method.key2` =
  `patient|insurance`, `adjustment.key2` = `production|collection`.
- **PROV-3** `providers.role` is free text (`dentist` 78, `Dentist` 2, `Hygenist` 1).
  Seeded `provider_role` group + `canonical_role()` on every write + a derived
  `provider_kind` on `ProviderRead` (a clinical role wins; otherwise the licence
  **title** decides, so a `staff` row holding an `RDH` still lands in the hygiene
  list) + `?role=` filter + `scripts/normalize_provider_roles.py`. Applied: 3 rows,
  split now 80/17/2. Deliberately **not an enum** — an unrecognised role is stored as
  written, since a 422 on save is a worse failure than an unfamiliar string.
- **FEE-2 is tooling only, not applied**: `scripts/backfill_office_fee_schedules.py`
  scores each active schedule against an office's own posting history (a schedule
  that priced those charges matches them column-for-column). Dry run: 3 of 15 offices
  clear the 60 % bar on the contracted side (offices 8/10/11), the rest genuinely
  bill from several plan schedules. Nothing written — a wrong default silently
  mis-prices every future charge, where NULL falls through and is visibly $0.
  **CHG-3 is closable**: 167 CPT codes are in `procedure_codes` today.

**Letters module** (print menu → Letters dialog → Report Viewer; LTR-1…12 of
[docs/letters/letters_backend_devreport.md](docs/letters/letters_backend_devreport.md)
/ [response](docs/letters/letters_backend_response.md); Alembic `e9f0a1b2c3d4`).
The catalog (153 seeded `letter_templates`) and the consent/document stores already
existed; what was missing was the *engine*:
- **Server-side merge** ([app/services/letter_service.py](app/services/letter_service.py)
  + [app/api/v1/letters.py](app/api/v1/letters.py), LTR-5). `MERGE_FIELDS` is exactly
  the **56 `#TOKEN#`s** that appear across the seeded corpus (extracted from
  `body_html`, so it cannot drift from the templates). `POST /letters/render` merges
  one template for one patient — values are **HTML-escaped**, the body goes through
  `sanitize_html`, an unresolvable token prints **blank** and is reported in
  `unresolved_tokens` (never a visible `#TOKEN#`), and the expensive balance aggregate
  runs only when the body actually contains `#RP_TOTAL_BAL#`. `POST /letters/render-batch`
  makes the `CS001…CS009 - Batch Coll N` sweeps possible at all — a durable job over
  `letter_batch_runs`/`letter_batch_items`, run inline, one bad patient records a
  `failed` item instead of killing the sweep.
- **`GET /patients/{id}/letter-context`** (LTR-6) collapses the dialog's 2–6 round
  trips; `include_balance` is opt-in because that call was ~28 s cold.
- **LTR-1 object storage**: [app/services/document_store.py](app/services/document_store.py)
  routes `document_type=consent-form` to
  `gs://{GCS_BUCKET_DOCUMENTS}/consent-forms/{tenant}/{patient}/{uuid}.pdf` (local disk
  when the bucket is unset, so dev/tests need no creds), records
  `storage_backend`/`storage_bucket`/`storage_path` on the row, and returns `file_url`
  as a **signed URL or the `/patient-documents/{id}/content` proxy** — never `gs://`.
  `GET /consent-forms` lists the bucket's blank masters.
- **LTR-3** the merge blocks that had no source: `providers.address_*/city/state/zip/
  phone/email`, `offices.corporate_name`, `account_settings.marketing_*` — each with a
  documented fallback chain (provider→office, marketing→corporate→office).
  **LTR-4** `#TX_PLAN_TH_NUMBER#` binds only when `treatment_plan_id` is passed.
  **LTR-7** `GET /offices/{id}/letter-templates/effective` pins the semantic
  **unassigned = all** (the plain assignment grid stays as-is).
  **LTR-10** `POST /patient-consents/{id}/sign` + the published `consent_status`
  vocabulary. **LTR-12** `/patient-documents` gains `document_type`/`office_id`/`search`
  and the standard paginated envelope (**breaking**: was a bare array).
- **LTR-11 is API-wide**: naive UTC `TIMESTAMP`s now serialise with an offset via
  [app/core/datetimes.py](app/core/datetimes.py) — `UtcDatetime` in the schema factory
  plus a `jsonable_encoder` patch for the dict-returning endpoints. OpenAPI is
  unchanged (`format: date-time`), so Orval needs no change.
- **Round 2 (LTR-13..16)**: the appointment merge block means *the appointment this
  letter is about* — `#APPT_PRDR#`/`#APPT_DATE#`/`#APPT_DATETIME#` resolve
  next appointment -> last appointment -> preferred provider, because a consent form is
  printed at the chair (no upcoming appointment) and was rendering `Dr. ___` on a
  signed legal document; `last_appointment_provider` is on the context payload.
  `#TODAY_DATE#` is computed in the **printing office's** timezone via
  `office_today()` in [app/core/datetimes.py](app/core/datetimes.py) (AppointNow's
  `_office_tz` now delegates to the same helper) — a UTC date post-dated evening
  consents. `/letters/render(-batch)` accept `overrides: {token: value}` +
  `signing_provider_id` (which re-points only `#APPT_PRDR#`/`#DOC_LAST_NAME#`, never
  the letterhead), reporting `applied_overrides`/`rejected_overrides`; unknown keys
  are rejected, values still HTML-escaped. The catalog is now **57** = the 56 corpus
  tokens + `APPT_DATETIME` (a deliberate FE-requested extension;
  `tests/test_letters_module.py::CORPUS_TOKENS` pins the distinction).
  **LTR-17**: `/letters/render` + `/letter-context` report `appointment_source`
  (`next|last|null`) and `appointment_provider_source` (`next|last|preferred|null`)
  plus a `fallback_tokens` `{token: tier}` map listing only *degraded* resolutions —
  a three-tier chain can name a provider unconnected to the visit, and "caught at the
  chair" only works if the chair can see it. A caller-overridden token is never listed;
  render filters the map to tokens the template actually uses.
  LTR-16: the GCS paths are covered by
  [tests/test_document_storage.py](tests/test_document_storage.py) against a fake
  client, and `scripts/check_document_storage.py` probes a **real** bucket in one
  command — but no deployed bucket run has happened yet.
- **LTR-8/9 are data tasks with tooling, not applied**:
  `scripts/repair_letter_templates.py` (dry-run by default) repairs the `?` mojibake
  under three narrow contextual rules — the loss is **upstream** (the corpus holds zero
  non-ASCII bytes, so re-running the migration cannot recover it). The `channel`
  pollution is a **field-offset** bug in the migration reader (embedded commas in the
  HTML `BODY`); those 11 `Financial Agreement` bodies are truncated and need re-import.

**Add / Edit Appointment module** (scheduler → Add Appointment / double-click an
appointment; APPT-PROC-1…4, SCHED-DEL-1/2, APPT-5…12 of
[docs/scheduler/add_edit_appointment_backend_devreport.md](docs/scheduler/add_edit_appointment_backend_devreport.md)
/ [response](docs/scheduler/add_edit_appointment_backend_response.md); Alembic
`f0a1b2c3d4e5`).
- **SCHED-DEL-1 is the load-bearing fix**: `DELETE /appointments/{id}` is a *soft*
  delete, but `GET /appointments/scheduler` returned the tombstones — so a deleted
  appointment reappeared on every refetch, and every consumer of the feed
  (dashboard KPIs, report metrics, lab tracking, patient overview) inherited the
  bug. The feed now filters `is_archived=false` by default (`?include_archived=true`
  opts back in) and `AppointmentSchedulerRead` exposes `is_archived`. The FE's
  subtract-the-archived-ids workaround can be deleted.
  **SCHED-DEL-2**: soft delete is deliberate (`sms_messages`/`patient_procedures`
  reference the appointment, plus audit history) — the missing half was
  `POST /appointments/{id}/restore` (idempotent, tenant-checked).
- **APPT-PROC-4** the same shape one level down: `appointment-procedures` opts into
  `CrudConfig.hide_soft_deleted`, so a removed line stops coming back;
  `?is_archived=true` still surfaces it.
- Additive columns: `appointment_procedures.duration_minutes` (**nullable on
  purpose** — Calc Time must tell "unset" from "0 minutes" so it can fall back to
  `default_duration_minutes`) / `provider_units` / `bill_to` (APPT-PROC-1/2/3),
  `appointments.lab_dds` (APPT-5, free text — legacy lab slips carry initials or an
  outside dentist, so a providers FK would make it unfillable).
- **APPT-7** new `campaigns` catalog ([app/db/models/comms.py](app/db/models/comms.py))
  behind the Campaign ID box; `appointments.campaign_id` stays a **string holding
  the code**, so a free-typed migrated value still saves.
- **APPT-10** `GET /procedure-code-categories` (grouped from the same
  `procedure_codes.category` column `/stats` uses, so it cannot drift).
- **APPT-8/9 were seeded, not just tooled**: every `requires_*` flag was false
  across all 1,122 codes, so enforcement could never fire.
  `scripts/seed_procedure_code_rules.py` derives them from the **CDT family ranges**
  (the published `D<category><series>` taxonomy — no licensed CDT file), plus
  per-family `default_duration_minutes` and CHG-2 `surface_rules` for the families
  whose descriptor *is* the surface count. Applied: 418 flag sets, 693 durations,
  15 surface rules. `default_fee` is **not** invented — fee schedules stay the
  source of truth (`--fee-schedule-id` copies a real schedule into the blanks).
- **APPT-6 needed no work** — explosion codes have been a resource since CHG-4
  (`/explosion-codes`, `/explosion-code-items`, `/explosion-codes/{code}/expand`);
  the FE removed the filter believing there was no backend.
- **APPT-11/12 confirmed as-is**: `patients.phone` *is* the home number (the
  `home_phone` column lives on `responsible_parties`, a different entity);
  `chart_no` is **not** unique and cannot be — 10,045 duplicated
  `(tenant_id, chart_no)` groups across 83,898 migrated patients — so the numeric
  `patients.id` is the only safe key.

**Lab Tracking module** (Add/Edit Appointment → LAB section · Patient → Lab Tracking
tab; LAB-1…11 of
[docs/lab-tracking/lab_tracking_backend_devreport.md](docs/lab-tracking/lab_tracking_backend_devreport.md)
/ [response](docs/lab-tracking/lab_tracking_backend_response.md); Alembic
`587baa6a0ba7`, **applied to the dev DB**). A lab case **is an appointment** with
`has_lab` — there is deliberately no lab-case row (legacy M12 + the FE model).
- **LAB-1** new `labs` vendor catalog ([app/db/models/scheduling.py](app/db/models/scheduling.py),
  `/labs` CRUD, 409 `duplicate_lab_name` + `allow_duplicate_name` on *create only*,
  `/labs/name-availability`) + `appointments.lab_vendor_id` (FK, tenant-checked, an
  inactive lab only blocks a *move*) + `lab_short_notice`. **`lab_dds` is the
  dentist, not the vendor** — settled. The catalog is empty on the migrated tenant:
  the Denticon export has no vendor/short-notice column, so no seed.
- **LAB-8 contract lives once** in [app/services/lab_tracking_service.py](app/services/lab_tracking_service.py)
  (`apply_lab_rules`, run by `AppointmentCRUD` on every write): `has_lab=false`
  **clears** the lab block *including values in the same payload* — the Add/Edit form
  sends the stale DDS/cost along with the un-tick, so "reject" would 422 every
  un-tick; lab data on a non-lab row **derives** `has_lab=true` (a `lab_cost` of `0`
  is empty — the migration wrote `0.00` everywhere). **LAB-9** `lab_date_order` 422
  on the merge of payload + stored row, only when a date is touched (one migrated
  row holds received-before-sent).
- **LAB-6 was the schema factory**, not one field: `build_schemas` never carried
  `String(n)` onto Create/Update, so every over-long string API-wide was a 500. It
  now emits `max_length` for every generated write schema (reads untouched, `Text`
  unbounded). **LAB-7** `lab_cost` `ge=0, max_digits=10, decimal_places=2` (the old
  round-to-2dp is gone). **LAB-10** `AppointmentCreate/Update` are `extra="forbid"`
  (checked the FE's payload keys first — all real columns).
- **LAB-2** `has_lab`/`lab_vendor_id`/`lab_short_notice`/`lab_status`
  (`not_received` = sent|overdue) + three lab date ranges on `GET /appointments`;
  `lab_status` + `lab_vendor_name` are **on `AppointmentRead`** (via
  `enrich_appointments`) and on the scheduler feed (**LAB-3**), one derivation
  (`derive_lab_status`, mirrors the FE's) for read/filter/report. Generic-list
  "today" is UTC; `/lab-cases` uses the office's date. **LAB-11** `GET /appointments`
  now `hide_soft_deleted` (18 lab cases live, 14 of them archived tombstones).
- **LAB-4/5** [app/api/v1/lab_tracking.py](app/api/v1/lab_tracking.py):
  `GET /appointments/lab-cases` (denormalised, paged, `counts` over every filter
  *except* `lab_status` so the tabs keep badges, `total_cost`, `as_of`), `…/cost-report`
  (`date_basis` × `group_by`), `…/report.pdf`, `…/cost-report.pdf`, `…/export.csv`
  (all audited as `PRINT`/`lab_report`; `ReportHeader.show_patient=False` for
  office-wide PDFs); `GET /metadata/lab-tracking-rules`. Index
  `appointments(office_id, has_lab)` — planner verified.

**Add/Edit Patient checkbox integrity** (Patient Status / Coverage Type / Patient
Type panels; [docs/patients/patient_flag_rules_backend_response.md](docs/patients/patient_flag_rules_backend_response.md)).
Every box in the three panels was independently selectable, so a patient could be
saved as both a *Child* and a *Senior Citizen*, or flagged **No Correspondence**
while automated e-mail/SMS stayed on — and the API persisted it, so the recall
sweeps, batch letters and SMS reminder job all inherited the contradiction. The
rule table lives once in
[app/services/patient_rules_service.py](app/services/patient_rules_service.py)
and is enforced on **every** write path (`PatientCRUD.create/update`,
`POST /patients/register`, `PatientInsuranceCRUD`), so no client can route around
it. **Two rule kinds, deliberately different**: *implications* (`no_correspondence
⇒ no_auto_email/no_auto_sms`; `is_active=false ⇒ add_to_quickfill=false`) are
**auto-applied** and returned corrected — the combination is unambiguous;
*exclusions* (`CH ⊕ SR`) are **422** because there is no way to know which the
user meant and silently dropping one discards intent. Implications evaluate
against the **merge of payload + stored row**, so a PATCH carrying only the
touched box still reaches flags already true in the DB. Coverage: an active slot
requires an active slot one rank below **of the same plan type**
(`primary→secondary→tertiary→quaternary`, per `D`/`M`); inactive slots are never
checked. **`No Coverage` has no column and must not get one** — it is the derived
"zero active slots" state; a column would be a second source of truth that can
disagree with the slots. `GET /metadata/patient-flag-rules` publishes the table so
the form drives its tick/untick from the same source (add a rule → UI picks it up,
no FE release). Migrated rows are **not** rewritten — a stored `["CH","SR"]`
survives until edited.

**Patient Notes document upload/download** (Patient → Notes → New Note →
*Documents (Upload)* / *Document (Scan)*; NOTE-DOC-1…5 of
[docs/patient_note_documents_backend_devreport.md](docs/patient_note_documents_backend_devreport.md)
/ [response](docs/patient_note_documents_backend_response.md); Alembic
`a1b2c3d4e5f7`). The binary store was already right — the gaps were around it.
- **NOTE-DOC-1** `patient_notes.document_id` (FK → `patient_documents.id`,
  nullable) is the link that let a file be uploaded but never recorded as
  belonging to a note, so re-opening the note could not find it.
  `PatientNoteCRUD` ([app/services/patient_note_service.py](app/services/patient_note_service.py))
  enforces **same tenant + same patient** on create *and* PATCH (422
  `document_patient_mismatch`) — a note renders inside one patient's chart, so a
  mis-pointed id is a PHI disclosure, not a cosmetic bug; a PATCH carrying only
  `document_id` checks against the note's **stored** `patient_id`.
  `enrich_patient_notes` embeds a `document` block (name/type/size/`file_url`) on
  `PatientNoteRead` so a 40-row Notes list doesn't fan out 40
  `GET /patient-documents/{id}`. **Deleting a note never deletes the document** —
  it is a patient-level record that also lists under `/patient-documents` and may
  back a consent; an undeleted note pointing at nothing would be worse.
- **NOTE-DOC-3 was the load-bearing fix**: `app.mount(UPLOAD_URL_BASE, StaticFiles(UPLOAD_DIR))`
  was a *blanket* mount, so every patient document, **claim attachment** and
  **progress-note attachment** under it was readable with no token and no tenant
  check. Only `settings.UPLOAD_PUBLIC_SUBDIRS` (logos / office_logos /
  provider_watermarks) is mounted now; `document_store.public_url` returns the
  authenticated `/content` proxy for **local** rows too (it used to fall back to
  the public path), and the two attachment kinds gained the `/content` route they
  never had (`…/attachments/{id}/content` on progress-notes and insurance-claims),
  which is what their `file_url` now points at. **Breaking**: `file_url` is never
  a `/uploads` path again.
- **NOTE-DOC-5** `filestore.validate_upload` is the single rule set (size cap +
  extension **and** content-type allow-list) applied on every binary upload route;
  an *uninformative* declared type (`application/octet-stream`, empty) defers to
  the extension, because scanners send that for real PDFs and rejecting them would
  break Document (Scan) for no security gain. Published at
  `GET /patient-documents/limits` so the picker states what the server enforces.
- **NOTE-DOC-2** every patient file now lives under one `documents/` root in
  `gs://reco-documents` — `documents/notes/{tenant}/{patient}/{uuid}{ext}`,
  `documents/consent-forms/…`, `documents/general/…` (was two branches at the
  bucket root). The class is chosen by `document_store.prefix_for`, where the
  upload **`context` beats `document_type`**: a consent form uploaded from Notes
  files with the note, because the note is the record it belongs to. `context` is
  a new form field on `POST /patient-documents` and **must come from the caller**
  — the file is uploaded *before* the note row exists, so nothing server-side can
  infer it; an unrecognised value is 422 `invalid_document_context` rather than a
  silent fall-through, since a typo would bury a file in a folder nobody checks.
  `DOCUMENT_CONTEXTS` is published on `/patient-documents/limits`. The local
  fallback mirrors the object key, so `uploads/` and the bucket read alike.
  Turning it on is still just `GCS_BUCKET_DOCUMENTS` + `PUBLIC_API_BASE_URL`.
  **NOTE-DOC-4** seeds the `document_type` definitions group (14 codes); `CF` is
  in `CONSENT_DOCUMENT_TYPES`, which now only decides where a consent goes when
  it is uploaded *outside* a note.

**Insurance second pass** (patient insurance slots + Setup -> Insurance -> Plans;
INS-PT-7…21 of
[docs/patient-insurance/patient_insurance_backend_devreport.md](docs/patient-insurance/patient_insurance_backend_devreport.md)
/ [response](docs/patient-insurance/patient_insurance_backend_response.md); Alembic
`e4f5a6b7c8d9`). INS-PT-1…6 shipped in the first pass (`d6e7f8a9b0c1`).
- **INS-PT-15 is the load-bearing fix, and it is a migration bug**:
  `s07_insurance_plans` read `row.get("GROUPNO")` where `InsPlans.txt` writes
  **`GROUPNUMBER`** — `.get` returns `None`, so all 31,331 migrated plans stored
  a NULL group number and never failed. That field is what the legacy "Search
  For = Group #" dialog and **both** duplicate-prevention layers key off, so the
  feature was correct and completely inert. The same wrong-name mistake hit the
  BENEFIT INFO panel: `INDIVIDUALMAX`/`INDIVIDUALDEDUCTIBLE`/`INDIVIDUALORTHOMAX`/
  `FAMILYDEDUCTIBLE` were all read under abbreviations that do not exist, and
  only `FAMILYMAX` matched — which is why family_max was the one column with
  data, and why plans priced as if they had **no benefit left**. `s07`/`s18`/`s05`
  are fixed and `scripts/backfill_insurance_source_fields.py` repairs the live
  rows (NULL-guarded; the five money columns treat `0` as empty because the
  migration wrote a literal zero). **Applied**: group_number 8 -> 31,329;
  individual_max 4 -> 31,263; ortho_max 3 -> 29,720; plus 46,973 `marital_status`,
  42,604 `sub_phone`, 3,246 `sub_address2` on `insurance_subscribers` (INS-PT-1/2/4
  had columns and no data — `RespInsplan.txt` carries `MSTATUS`/`SUBPHONE`/
  `SUBADDRESS2` and `s18` never read them). `--group-from-subscribers` recovers
  the group number without the export, unanimous plans only. `employers.address2`
  (INS-PT-11) exists but `Employers.txt` is blank on all 4,302 rows — nothing to
  backfill.
- **INS-PT-19** duplicate prevention was client-side only. `InsurancePlanCRUD`
  409s `duplicate_plan_group` on an active plan with the same **carrier +
  group_number** (trimmed, case-insensitive; NULL never collides). Deliberately
  **not** a DB constraint: two offices can legitimately hold separate plans on
  one group and legacy allows it, so `allow_duplicate_group` overrides — a
  constraint cannot express "refuse the *accidental* one" (and the honest cost is
  that two concurrent saves can still both land). Same-carrier-inactive
  (INS-PT-21) and other-carrier matches are **reported, never blocking**. The
  guard fires on a **move**, not on stored state — the INS-PT-15 backfill put
  3,609 groups into a real pre-existing collision, and blocking every later edit
  of those plans would punish the repair.
- **INS-PT-20** `GET /insurance-plans/group-availability` answers the same
  question in one indexed lookup instead of a paginated list call per save.
  **INS-PT-13** the same shape for names: 409 on a quick-add repeating a carrier/
  employer name (`allow_duplicate_name`) + `…/name-availability` probes. Only
  *create* is guarded — a rename onto a taken name is usually a deliberate merge.
- **INS-PT-9/18** a 20-row plan grid cost up to 40 single-id GETs (each with a
  preflight) to paint two name columns. Fixed twice over: `InsurancePlanRead` is
  denormalised (`carrier_name`/`payer_id`/`employer_name`/`created_by_name`/
  `updated_by_name`/`is_dental`, batched via `enrich_insurance_plan`), **and**
  `?ids=1,2,3` batch lookup on `/insurance-carriers` + `/employers`. `is_dental`
  on the plan read is what lets the form preselect Dental/Medical without
  fetching the carrier.
- **INS-PT-12** `is_dental` is now **writable** and **filterable**, and the
  vocabulary lives once in `insurance_service.MEDICAL_TOKENS` — the read field,
  the `?is_dental=` filter and the write canonicalisation share it, so a
  `carrier_type` typo can no longer read as dental while matching neither filter.
  An unrecognised value is stored **as written** (the PROV-3 call: a 422 on save
  is worse than an unfamiliar string). **INS-PT-8** plans gain `updated_at`/
  `updated_by` + the four legacy free-text actors mirroring the carrier, so
  Modified stops rendering `—`; the legacy pair exists because `CREATEDBY` is a
  Denticon login with no `users` row to FK at. **INS-PT-10** `claim_type`
  definitions group seeded from the only two codes the export contains
  (`1` EClaim, `0` Paper).
- **INS-PT-7/14** per-field and partial plan search — `group_number_contains`/
  `_startswith`, and `carrier_name`/`payer_id` which used to issue the identical
  free-text query. Needed one engine addition: **`CrudConfig.extra_filters`**, a
  declared, OpenAPI-visible query param that is not a plain column and is
  resolved by the resource's `crud_class` in `_extra_list_clauses` (pairs with
  the existing `custom_filter_fields`), plus `CrudConfig.id_in_param`.
- **INS-PT-5 stays manual** (no clearinghouse contracted — the endpoint stamps
  and reports `method="manual"`); **INS-PT-17** is a frontend route
  (`GET /insurance-plans/{id}` always existed).

**Edit Insurance Plan from the patient screen** (Patient -> Insurance -> slot -> Edit
Plan, over the shared 4-tab wizard; EDIT-PLAN-1..9 of
[docs/patient-insurance/edit_insurance_plan_backend_devreport.md](docs/patient-insurance/edit_insurance_plan_backend_devreport.md)
/ [response](docs/patient-insurance/edit_insurance_plan_backend_response.md); Alembic
`7f483f6833a7`, **applied to the dev DB**). One plan row is shared by every patient on
it, so the safeguards a shared master-data edit needs are server-side:
- **EDIT-PLAN-1 is engine-wide**: [app/core/concurrency.py](app/core/concurrency.py) —
  `updated_at` is the row's *version* (`created_at` when never updated);
  `If-Match` (the `ETag` every generated GET now returns) / `If-Unmodified-Since` /
  body `expected_updated_at` (explicit `null` = "never updated", absent = no check)
  → **412 `precondition_failed`** carrying `current.{updated_at,version,updated_by_name}`.
  `CRUDBase.update/delete` check it after a `SELECT … FOR UPDATE`, and **stamp
  `updated_at` app-side with µs** (SQLite's `now()` is whole seconds, so two saves in
  one second read as one version). **The plan row is the version of the whole
  document**: every coverage-rule / frequency-group write (per-row CRUD, bulk PUT,
  copy) calls `touch_plan`, so one `updated_at` guards all four wizard tabs.
- **EDIT-PLAN-5**: [app/services/permission_service.py](app/services/permission_service.py)
  — effective codes = union of the user's active groups' rights; `admin`/`super_admin`
  hold everything; a non-admin in **no group is ungated** (`permissions_enforced=false`
  on `me-full` — refusing them would lock a migrated tenant out on deploy day).
  `CrudConfig.write_permissions` + `require_permission()` gate POST/PATCH/DELETE (403
  `permission_denied` naming `required_any_of`); reads never gated.
  `insurance_plans.is_locked` (+ stamped `locked_at/by`) needs
  `setup_insurance_plans_screen_edit_locked_plan` for *any* edit incl. toggling → 423
  `plan_locked`; an ungated user does **not** get the lock right for free.
- **EDIT-PLAN-4 decided by the data**: 22,335 of 65,314 migrated subscribers hold a
  group number that genuinely differs from their plan's (card suffixes) — so the plan
  is master and `cascade_subscriber_group_number` moves only subscribers still equal
  to the old value (or blank), keeps the rest, and reports both on the PATCH response
  (`group_number_cascade`, consumed by `enrich_insurance_plan` so it shows once).
  `InsuranceSubscriberRead.plan_group_number` / `group_number_matches_plan`.
- **EDIT-PLAN-2/3/6** in [app/services/insurance_plan_edit_service.py](app/services/insurance_plan_edit_service.py):
  `GET /insurance-plans/{id}/usage` (distinct patients vs raw `patient_links`, open
  claims — only **4** migrated claims carry an `ins_plan_id` at all), `…/affected-
  treatment-plans` + `GET /treatment-plans?ins_plan_id=` (one clause,
  `treatment_service.affected_by_insurance_plan_clause`: active slot **or** open item
  estimated against the plan), `POST …/re-estimate` (inline under `max_plans`,
  `dry_run`, per-plan failure isolation, open claims re-summed), `…/history`
  (plan + rule + group + bulk changes with names). Child-row writes stamp
  `audit_logs.details.scope.ins_plan_id`; the bulk PUT records `details.changes[]`;
  `AuditMiddleware._details_payload` copies both.
- **EDIT-PLAN-7 root cause**: nine `async def` upload handlers (documents, claim /
  note attachments, imaging capture, logos, watermark, avatars) ran sync DB + GCS work
  **on the event loop**, stalling every other request for the upload's duration —
  now `run_in_threadpool`. Plus 3 missing `ins_plan_id` indexes (claims count was a
  96k-row seq scan) + `audit_logs(resource_type, resource_id)`.
- **EDIT-PLAN-8** plan Create/Update `extra="forbid"`. **EDIT-PLAN-9** 31,334 NULL
  rows backfilled to the legacy defaults (model defaults match, published as
  `plan_field_defaults`); `lifetime_ortho_benefits` defaults **true** for new plans
  only — migrated rows untouched (no source column).

**Insurance Payment window** (Patient -> Ledger -> claim -> INSURANCE PAYMENT;
INS-PAY-1..8 of
[docs/patient-insurance/insurance_payment_backend_devreport.md](docs/patient-insurance/insurance_payment_backend_devreport.md)
/ [response](docs/patient-insurance/insurance_payment_backend_response.md); Alembic
`f5a6b7c8d9e0` + `a6b7c8d9e0f1`).
- **INS-PAY-2 is the critical one, and it hid a much bigger hazard.**
  `record_insurance_payment` did `claim.total_paid += paid` and nothing ever
  subtracted, while `recalculate` recomputed billed/estimate from the procedures
  but **echoed** `total_paid` — so deleting a mis-keyed remittance left the claim
  asserting money no row backed, fixable only by hand-PATCHing the claim.
  `total_paid` is now **derived**, `DELETE` is a **void** not a removal
  (`is_void`/`void_reason`/`voided_at`/`voided_by`, hidden from the default
  listing), and `POST /ledger-insurance-details/{id}/reverse` is the
  insurance counterpart to `/patient-payments/{id}/reverse` that never existed.
  `LedgerInsuranceDetailCRUD` re-derives the claim on **every** generic CRUD
  write too — `/reverse` fixes the intended path, but an import or an older
  client still uses the CRUD routes.
  **The hazard**: deriving `total_paid` from coverage rows is right for an
  app-posted claim and catastrophic for a migrated one — 96,314 claims, 79,038
  with a non-zero `total_paid`, and of 12,191 `ledger_insurance_details` rows
  only 216 are attached to a claim and **none** carry an `*_ins_paid` amount
  (the migrated total comes from the Denticon claim export). A naive derivation
  would have zeroed all 79,038 on the first Recalculate. `insurance_claims.opening_paid`
  holds that pre-existing carrier money and `total_paid = opening_paid + live
  rows` — the `patient_opening_balances` shape. The baseline is seeded **inside**
  the migration, not by a follow-up script, because a script leaves a window
  where `recalculate` is deployed and `opening_paid` is still NULL, and that
  window is the bug. Verified after applying: 79,038 seeded, 0 unprotected,
  derived == stored on every claim.
- **INS-PAY-3** `POST /ledger-insurance-details/payment-batch` — one remittance
  header + `lines[]` in a single transaction, so a four-procedure cheque stops
  being four POSTs that can half-fail ("posted N of M" with no rollback).
  Two rules move server-side: an optional `payment_amount` is reconciled against
  the lines **to the cent** before anything is written (422
  `remittance_not_reconciled`), and a line's `procedure_id` must be on the claim
  (422 `procedure_not_on_claim`). Negative amounts are refused everywhere —
  backing a payment out is `/reverse`, which keeps a trail.
- **INS-PAY-4** the claim-level "Enter Adjustment": the money stays
  per-procedure (that is what the ledger reconciles against, so the FE's
  distribution *is* the intended model) but the **intent** is now recorded —
  `insurance_claims.write_off_mode`/`write_off_value` (what was typed, e.g.
  percent/10) + `write_off_amount` (the distributed total). "A 10% claim
  write-off" survives becoming 7.70/7.00/7.70.
- **INS-PAY-5** the tier matrix is completed (`sec_deductible`, `ter_estimated`,
  `ter_deductible`, `ter_ins_adjust`, `ter_posted`), so a secondary remittance
  can carry a deductible and a tertiary one can be posted at all; all three tiers
  build through one function and count toward `total_paid`. **INS-PAY-1**
  `ledger_insurance_details.notes` (the note was being appended to the *claim's*
  notes with a synthetic prefix). **INS-PAY-6** `patient_payments.eft_trace_number`
  — `eob_number` already existed (AL-13), the FE client was stale.
- **INS-PAY-7** `GET /patients/{id}/outstanding-claims` — charges / est ins /
  deductible used / ins paid / ins adj / remaining per claim in three statements,
  where a client-side picker needed one `/detail` call per claim. Voided coverage
  is excluded; `remaining` is floored at zero (an over-payment is a credit, not a
  negative receivable). **INS-PAY-8** `attachment_type` seeded + normalised on
  upload from one list (`patient_extra_service.CLAIM_ATTACHMENT_TYPES`), with an
  unrecognised value stored as written — a 422 mid-upload would leave a claim
  that cannot be attached to.

**Insurance Plan Details wizard** (Setup -> Insurance -> Plans -> Add/Edit; the
4-tab INSURANCE DETAILS dialog + COPY FROM EXISTING; PLAN-DTL-1..9 of
[docs/patient-insurance/insurance_plan_details_backend_devreport.md](docs/patient-insurance/insurance_plan_details_backend_devreport.md)
/ [response](docs/patient-insurance/insurance_plan_details_backend_response.md); Alembic
`c8d9e0f1a2b3`). Logic in [app/services/insurance_plan_service.py](app/services/insurance_plan_service.py),
routes on `plans_router` in [app/api/v1/insurance.py](app/api/v1/insurance.py).
- **PLAN-DTL-1** nine PLAN/BENEFITS-tab columns on `insurance_plans` (`fees_to_print`,
  `claim_option`, `form_to_print`, `reporting_subtype`, `network_type`, `noa_only`,
  `per_visit_copay`, `lifetime_ortho_benefits`, `plan_notes`) — the wizard had been
  parking them in browser localStorage. Codes stored as written; vocabularies in
  `PLAN_FIELD_OPTIONS`, published at `GET /insurance-plans/metadata` and seeded as
  `definitions` groups.
- **PLAN-DTL-5 retyped `insurance_coverage_rules.freq_limit` to INTEGER in place**
  (checked first: all 876k live values were numeric strings). `age_min`/`age_max`/
  `wait_months` are canonical; `age_limit`/`wait_period` are **derived mirrors** the
  server rewrites on every save (`normalise_rule_limits`) and parses when only the
  string arrives. The backfill's one judgement call: a migrated lone `AGELIMIT` is
  Denticon's *maximum* (19/16/13/14/18/26 are child cut-offs) -> `age_max`; an
  app-written lone number is the wizard's *minimum* -> `age_min`.
- **PLAN-DTL-4** `freq_limit` is a 1-based ordinal into the legacy
  FREQUENCYLIMITATIONS list (`0`/NULL = none); the list lives once in
  `FREQUENCY_LIMITATIONS`, is published with `definition_id`s, and
  `definitions.sort_order` now carries the ordinal.
- **PLAN-DTL-2** the FE's reserved-shape coverage rows (`category='FREQGRP'`,
  `start_code='FQ01'`, whole-mouth as `age_limit='WM'`) became a real table,
  `insurance_plan_frequency_groups` (unique per plan + code group, `/insurance-plan-frequency-groups`),
  migrated in the Alembic revision; the coverage write path now **422s** the shape
  (`frequency_group_row_not_coverage`) so it cannot re-accumulate.
- **Tenancy hole closed**: `insurance_coverage_rules` has no `tenant_id`, and generic
  CRUD only scopes models that carry one, so any tenant could read/write any rule by
  id. `InsuranceCoverageRuleCRUD` overrides `_scope_tenant` through the owning plan.
- **PLAN-DTL-8** `GET/PUT /insurance-plans/{id}/coverage-rules` reconciles rules +
  frequency groups in one transaction (an item with `id` updates in place, without
  one inserts, unmentioned rows are deleted; any error rolls back) and
  `POST /insurance-plans/{id}/copy-from/{source}` is COPY FROM EXISTING server-side
  (`include_plan_fields` copies BENEFITS/PLAN fields, never carrier/employer/group).
- **PLAN-DTL-6** `definitions` had 1,144 exact duplicates (one insert per migration
  pass, identical on every column, no inbound FKs) — collapsed + unique on
  `(tenant_id, group_code, key1, description)`. The five wizard catalogues existed
  on **only the migrated tenant**; `scripts/seed_insurance_plan_definitions.py`
  seeds all 43 (account seeder delegates; PLANSUBTYPE matches on key+label because
  "Aetna" exists under PPO and HMO).
- **PLAN-DTL-3** `anniversary_month`/`anniversary_day` + `anniversary_date` kept in
  sync by `fold_anniversary` (month/day win; stored year, else current year).
- **PLAN-DTL-7 not reproducible**: the `(tenant_id, group_number)` index has
  existed since `e4f5a6b7c8d9`, the planner uses it (0.18 ms), warm CRUD path 0.10 s;
  `/group-availability` is the right call. **PLAN-DTL-9** on plans was a stale
  generated client; rules gained `updated_at`/`updated_by`/`created_by`.

**Account Ledger second pass** (AL-3/6/8/9/10/11/12 of
[docs/account-ledger/account_ledger_backend_devreport.md](docs/account-ledger/account_ledger_backend_devreport.md)
/ [response](docs/account-ledger/account_ledger_backend_response.md); Alembic
`b1c2d3e4f5a6` + `c2d3e4f5a6b7`). AL-1/2/4/5/7 shipped the denormalised
`GET /patients/{id}/account-ledger`; this pass fixes what it computed *with*.
- **AL-9 is the load-bearing fix**: `patient_payments.amount` carries **two** sign
  conventions — migrated Denticon `LEDGER` rows keep the legacy signed delta
  (a payment is **negative**: 185,885 rows), app-created rows store the positive
  magnitude — and every consumer assumed "positive = credit", so the migrated half
  double-negated. `/balance` returned `1093.00 − (−417.50) = 1510.50` where the
  answer is `675.50`, and a payment made the ledger's running balance go **up**.
  The rule now lives once in [app/services/ledger_sign.py](app/services/ledger_sign.py)
  — `delta = amount` verbatim for `payment_type='adjustment'` (genuinely two-way,
  so the stored sign *is* the intent), `-abs(amount)` otherwise (a payment always
  credits) — and `balance_service`, `ledger_service`, `transactions_service`,
  `report_service`, `statement_service`, `scheduler_service` and `refund_service`
  all route through it. Stored data is **not** rewritten: normalising the sign
  would destroy the only signal separating a credit adjustment from a debit one.
  `account-ledger.amount` is now genuinely signed (`+charge`/`−credit`) with
  `charge`/`credit` as non-negative magnitudes; `/balance` reports `total_paid`
  positive and adds `total_payment_debits`. Rides along: `/balance` and the feeds
  excluded archived *charges* but included archived *payments* (a no-op on current
  data — every archived row is `0.00` — but they could never reconcile); the feed
  takes `?include_archived=true`.
- **AL-11** `?scope=account` merges every patient sharing the anchor's
  `responsible_party_id` ([app/services/account_scope.py](app/services/account_scope.py),
  raw-string match so migrated guarantors resolve), recomputes the running balance
  across the merged feed and **server-pages** it; every row carries
  `patient_id`/`patient_name` in both scopes. `GET /patients/{id}/account-balance`
  is the legacy BALANCES table in one call (aggregate + `members[]`, each the
  `/balance` payload). 15 requests for a 5-member account become 2.
- **AL-8** `?include_claims=true` interleaves `source_type='claim'` rows — **one
  per dated status transition** (`submitted`/`paid`/`closed`), because the legacy
  row is the *event*, not the claim's current state. `transaction_kind='I'`;
  `charge`/`credit` are zero and the running balance does not move (the money
  already arrived as an insurance payment). Opt-in so `total` doesn't shift under
  existing callers.
- **AL-10/AL-6 were migration data loss**, not API gaps: `LEDGER.CREATEDBY`,
  `CREATEDON`, `DURATION` and `CLAIMID` were all dropped by `s28`/`s29`.
  New `created_by_legacy` (both tables) + `patient_procedures.duration_minutes`;
  `s28`/`s29` now carry them, and
  `scripts/backfill_ledger_source_fields.py` repairs migrated rows (NULL-only by
  default, `--dry-run`/`--overwrite`/`--only`). Dry-run over 2.79M ledger rows:
  297,671 procedures gain a `claim_id` (so `unbilled` stops being universally
  true), 1.46M gain `created_by_legacy` but only 359,687 resolve to a `users` row
  — **2.23M name a login that has none** (only providers were seeded as users),
  which is exactly why `user_label` falls back to the raw legacy login.
  `DURATION` is `0` on all but **7** rows, so the `Durati…` column will stay empty
  — the data was never captured upstream. `At`/attachment has **no source column**
  in the 66-column `LEDGER` export.
- **AL-13/14/15/16/17** (a later revision of the same report, in
  `docs/ledger/`): `hold_claim` on the feed, as a `/patient-procedures` filter,
  **and enforced server-side** (AL-17 — the grid was walking the whole list per
  account member to colour one column, and Create Claim is
  `POST /insurance-claims` + `PATCH /patient-procedures{claim_id}`, so one
  disabled checkbox in one screen was the *only* thing stopping a held charge
  being claimed; `PatientProcedureCRUD` now 422s
  `procedure_on_hold_claim` on the assignment, evaluating the hold against the
  merge of payload + stored row so un-hold-and-claim in one PATCH still works); `description` is plain text on every row, a `$`-amount
  baked into a migrated note stripped server-side (AL-14). **AL-15 had two root
  causes**: `payment_allocations` can never supply `paid_to_date` because the
  Denticon allocation export is **6,951 rows for 1.33M payments with `AMOUNT`
  `0.0000` on every one** (AL-16 — unrecoverable, the link was never exported),
  and `remaining_amount` subtracted from `patient_estimate`, which is `0.00` on
  1,372,558 of 1,372,574 migrated rows (Denticon has no patient-estimate column —
  the share is `fee − ESTINS`). Fixed with `patient_procedures.pat_paid`/
  `pat_adjust` from `LEDGER.PATPAID`/`PATADJUST` (the only surviving record of
  what was applied to a charge; a real allocation still wins), a `fee −
  insurance_estimate` fallback, and a new `outstanding_amount`. AL-13 adds the
  `updated_at`/`updated_by` audit pair to both ledger tables (`CRUDBase.update`
  stamps it), `patient_payments.eob_number` and
  `patient_procedures.fee_schedule_id`; ADVANCED / contract-plan /
  per-transaction referral / ICD-10 stay unmodelled pending a product call.
- **AL-12** `GET /patients/{id}/context` gains `responsible_party` (resolved by
  numeric FK then `legacy_id`), `responsible_party_id` and `primary_insurance`;
  `insurance[]` gains `group_number`/`plan_type`/`plan_name`. There is no
  plan-name column in the migrated schema — `plan_name` is composed as
  carrier + group number. **AL-3 needed no work** (`plan_type` +
  the insurance-plan financial fields shipped in Alembic `f8a9b0c1d2e3`); the FE
  was on a stale generated client.

**Patient Medical History module** (Medical Alerts · Dental/Medical Questionnaire ·
Signature · Copy Medical History; MH-1…16 of
[docs/medical-history/medical_history_backend_devreport.md](docs/medical-history/medical_history_backend_devreport.md)
/ [response](docs/medical-history/medical_history_backend_response.md); Alembic
`a2b3c4d5e6f7`). The screen had no backend of its own — it drove the three
generic answer resources one HTTP request per row.
- **MH-6 is the load-bearing fix**: `patient_signatures` recorded only *that*
  someone signed. A patient could sign, staff could then change any answer, and
  nothing recorded that the signature predated the change — on a legal clinical
  record. It needed no new tables: `medical_history_records` (Denticon's
  `PatMedicalHistoryH`, which already pointed at a signature) becomes the
  **version** row and the pre-existing `medical_history_details` holds its frozen
  answers (`answer_type` = `alert|dental|medical`), with `content_hash`
  (SHA-256 over the *values* sorted by code, so a no-op re-save doesn't
  invalidate a signature) stamped on both sides. The document reports
  `signature_status` = `signed|stale|unverifiable|unsigned`; a migrated signature
  with no hash is **`unverifiable`, never `signed`** — asserting it attests to
  today's answers would be the same bug with the API's authority behind it.
  Plus `signature_type` (a medical-history, consent and financial signature were
  indistinguishable rows), `signed_at`, `signed_by_user_id` (attester ≠ pad
  operator). **MH-7**: `is_active`/`superseded_by_id`/`voided_at`/`voided_by` +
  `POST /patient-signatures/{id}/void` — a *cleared* signature was previously
  not representable at all.
- **MH-2/3** one document. `GET /patients/{id}/medical-history`
  ([app/api/v1/medical_history.py](app/api/v1/medical_history.py) +
  [app/services/medical_history_service.py](app/services/medical_history_service.py))
  replaces the 9+ request open; `PUT` reconciles the whole thing in one
  transaction. Only codes **present** in the payload are touched (partial saves
  are safe); a null response/answer is a reset to Not Answered and deletes the
  row; `replace_*` is the full-section replace — legacy's **NO TO ALL ALERTS**
  goes from ~90 sequential POSTs through a 6-connection pool to one atomic call.
- **MH-8** `updated_by` + `answered_at` on both answer tables (`answered_at`
  moves only when the *answer* does), and new `patient_medical_history_events` —
  an append-only, field-level log written on every path including per-row CRUD
  and the copy. `audit_logs` records one row per request, which for the composite
  write is one entry for a whole document; a medical record has to answer "who
  changed *this answer*".
- **MH-13/16** new `patient_medical_history` 1:1 header: first-class `comments`
  (the Additional Comments box was a magic `ADDITIONAL_COMMENTS` alert row shared
  by two modules with nothing enforcing it — a legacy row is still *read*, then
  retired) and per-tab `*_completed_at`/`_by`. A completion is **asserted**
  (`mark_completed`, or signing), never inferred from `updated_at`.
- **MH-4** `POST /patients/{id}/medical-history/copy-from/{source}?scope=`
  replaces ~90 client reads + ~90 writes; provenance lands in three places
  (change log `action="copy"`, the version's `source_patient_id`/`copied_at`, the
  header's `copied_from_patient_id`).
- **MH-1 is fixed server-side, but seeding stays gated.** The document resolves
  each catalog from `definition_groups`/`definitions` and applies the FE's own
  `MIN_TENANT_CATALOG_ITEMS = 10` guard, falling back to a built-in legacy
  catalog and reporting `catalog_sources: {alerts: "builtin"|"tenant"}` — so the
  FE can delete `legacyCatalogs.ts` today. Seeding real rows is a **one-way
  door**: an answer is keyed by `to_code(label)`
  ([app/services/medical_history_catalog.py](app/services/medical_history_catalog.py),
  the FE's derivation, published at `/metadata/medical-history-rules`), so any
  label whose code differs orphans stored answers.
  `scripts/seed_medical_history_catalogs.py` is dry-run by default, takes
  `--from-json` (hand over the FE file — that is the safe route), and **refuses**
  to seed a catalog that would orphan an answered code without `--allow-orphans`.
- **MH-5 answered**: `unknown` is a real third answer; *absent* is Not Answered,
  and neither is ever collapsed into the other. **MH-12** enforced on the
  composite write *and* the generic `/patient-medical-alerts` resource (else a
  client stores the contradiction one row at a time), judged against the **merge**
  of payload + stored rows. These are **422s, not auto-corrections** unlike the
  patient checkbox *implications* — there is no way to know which of the two the
  user meant. `allow_contradictions` overrides and is logged. Both published at
  `GET /metadata/medical-history-rules`.
- **MH-14 both ways**: the catalog's `is_flash_alert`/`blocks_charges`/`section`
  are denormalised onto every answered row, **and** a flagged Yes propagates into
  `patient_alerts` (new `is_flash_alert` + `source_medical_alert_id`) — the link
  is what makes it reconcilable: un-answering deactivates exactly the row it
  created, a hand-typed banner alert is never touched. **MH-11** decided:
  `patient_emergency_contacts` is authoritative, the block is out of `MEDQUEST`,
  and the composite write targets that table.
- **MH-9/10 are API-wide**: `CRUDBase` gains `_search_order`/`_extra_search_clauses`
  (both empty by default, so only opted-in resources change) and `PatientCRUD`
  ranks exact chart/id → exact name → `"Last, First"` → prefix → substring, with
  the caller's `sort` deciding ties *within* a tier. `"Last, First"` is also
  *matched* (no single column contains the comma). **Breaking**: `?phone=` now
  spans `phone`/`cell_phone`/`work_phone` (was exact on one column), and
  `DELETE /patient-signatures/{id}` is now a soft delete.
- **MH-15** `GET /patients/{id}/medical-history/pdf` (reportlab, lazy) prints
  `signature_status` — a printed history that doesn't say the signature is stale
  is a misleading clinical document.

**Medical Alerts surfacing + Medical History round 2** (Prescriptions banner · Scheduler
block badge · Details pop-out; MA-1…8 of
[docs/medical-history/medical_alerts_surfacing_backend_devreport.md](docs/medical-history/medical_alerts_surfacing_backend_devreport.md)
and MH-17…22 of the Medical History report /
[response](docs/medical-history/medical_alerts_surfacing_backend_response.md); Alembic
`b08a4634a3e3`, **applied to the dev DB**).
- **MA-3 was the built-in catalog, not the rows**: every stored `alert_code` is derived by the
  frontend from *its* legacy list (`legacyCatalogs.ts` — "Cardiac Pacemaker" under "Check, if
  applicable"), while the backend's built-in list had been authored independently ("Heart
  Pacemaker" under "Medical Conditions"), so the codes the screen writes resolved to no
  section/label and the few overlaps (`aspirin`) worked. `medical_history_catalog.py` is now a
  **verbatim transcription** of the FE file (88/29/19 items, `to_code` capped at 60 chars like
  the FE). `alert_label` + new `patient_medical_alerts.section` are filled from the catalog at
  write time on every path (client value = override); read falls back stored → catalog →
  humanised code. `scripts/backfill_medical_alert_sections.py` stamped 374/384 rows.
- **MA-4**: `alert_flags()` = built-in catalog overlaid with **every** tenant MEDALERT
  definition, deliberately not gated by `MIN_TENANT_CATALOG_ITEMS` (the guard picks the *list*
  to render; it was also hiding the one flagged definition, so every row read `false/false`).
  `is_flash_alert`/`blocks_charges` are nullable per-answer overrides too; reads report the
  effective value via `effective_alert_meta`, set on the ORM row with `set_committed_value` so
  enrich never dirties a real column.
- **MA-1/2**: [app/services/medical_alert_summary_service.py](app/services/medical_alert_summary_service.py)
  answers "active alerts for these patients" in four statements (both tables, de-duplicated by
  `source_medical_alert_id`, allergies-first order, `summary_text`). Read by the scheduler feed
  (`has_alert` now = free-text OR Medical-History YES; + `alert_summary`/`alert_count`),
  `GET /patients/{id}/medical-alerts/summary`, bulk `GET /medical-alerts/summary?patient_ids=`,
  `PatientContext.medical_alerts`, and the prescription check. `?patient_ids=` (≤200) on
  `/patient-medical-alerts` + `/patient-alerts` (new `PatientAlertCRUD` scopes tenancy through
  the patient — the table has no `tenant_id`).
- **MA-5**: `PrescriptionCRUD` ([app/services/prescription_service.py](app/services/prescription_service.py))
  matches the drug against the summary two ways (`prescription_library.allergy_keys` slugs vs
  code/label; the alert label inside the drug name for **allergy sections only**) → 409
  `prescription_alert_conflict` unless `alerts_acknowledged`; persists
  `acknowledged_alert_ids` + `acknowledged_alerts` snapshot + `alert_warnings` + `_at/_by`;
  `POST /prescriptions/alert-check` is the same check as a read. Warning-and-override on
  purpose: the matcher is lexical.
- **MA-8 / MH-22 root cause**: redis-py ≥ 6 retries a failed *connect* 3× with exponential
  back-off by default, so with `REDIS_ENABLED=true` and no local Redis the 2 s connect timeout
  was a measured **19–22 s stall** paid by the first request after each cooldown (56 s login,
  25 s feed, 15 s PATCH). Both clients now pass `retry=Retry(NoBackoff(), 0)`; cooldown 60 s;
  cold cost 4 s (localhost → `::1` + `127.0.0.1`).
- **MH-17**: every hand-written schema in `app/schemas` uses `UtcDatetime` (22 files).
  **MH-18**: `GET …/medical-history/audit` (+ `audit` on the document) — overall/per-section
  Created/Modified from active **and** inactive rows plus the change log (the composite write
  hard-deletes a cleared answer, so the log is the only complete record). **MH-19**:
  [app/core/audit_context.py](app/core/audit_context.py) — `CRUDBase` records
  `{row_id, patient_id, before, after}` per request, `AuditMiddleware` writes it as
  `audit_logs.details`, reads a POST's id from the 201 body, fills new indexed
  `audit_logs.patient_id`; `GET /patients/{id}/audit-logs` is open to any tenant user.
  **MH-20**: `CRUDBase.update` diffs first — no change → no stamp, no UPDATE (a subclass that
  mutated the row before delegating still commits). Alembic revision ids are random hex now
  (`a7b8c9d0e1f2` collided with an existing revision and produced a cycle).

**Procedure entry — one path for four screens** (Transactions Entry · Account Ledger Add Proc ·
Restorative Chart · Treatment Plan; PROC-INT-1…9 of
[docs/procedures/procedure_entry_integration.md](docs/procedures/procedure_entry_integration.md)
/ [response](docs/procedures/procedure_entry_backend_response.md); Alembic `d9e0f1a2b3c4`).
- **PROC-INT-1/2** `patient_procedures.treatment_plan_item_id` is the canonical item↔charge
  link (the FE had been pairing by code+tooth+surface, and two identical open items collapsed
  to one key). The item's `procedure_id` on every read is **derived** from it. Setting the FK
  is what flips the item to `status='completed'` (a real enum value now, plus `scheduled`) —
  in the **same transaction** as the charge insert, via `PatientProcedureCRUD`
  ([app/services/patient_procedure_service.py](app/services/patient_procedure_service.py))
  + `bind_item_to_charge`/`release_item` in
  [app/services/treatment_service.py](app/services/treatment_service.py); voiding /
  re-pointing releases it back to `accepted` unless another live charge remains. A client
  writing `completed` by hand is 422 `status_requires_charge`; un-completing under a live
  charge is 422 `item_has_posted_charge`. `POST /treatment-plan-items/{id}/post` is Post to
  Ledger server-side (charge + close in one call; 409 `item_already_posted`). Migrated
  `Completed`/`Scheduled` casings were lower-cased in the migration.
- **PROC-INT-6/8** [app/services/procedure_rules_service.py](app/services/procedure_rules_service.py)
  is the one home for the surface vocabulary (`M O I D B F L`, order M·O/I·D·B/F·L, arch-aware
  spelling, **Class V as a `5` suffix qualifier on B/F/L counted once**), Universal tooth
  parsing (incl. supernumerary 51–82 / `AS`–`TS`) and the `requires_*` / surface-count /
  `valid_teeth` / `tooth_area` / `allowed_quadrants` enforcement — run on **every** write to
  `patient_procedures` and `treatment_plan_items` (422 with `details.code` + `details.field`),
  normalise-only on `code_bundle_items`/`explosion_code_items`. On PATCH the rules run only when
  the payload touches a clinical field, against the merge with the stored row — re-pricing one
  of 1.37 M migrated charges with no tooth must not fail. `requires_lab` is deliberately
  **advisory**. The migrated ledger keeps **quadrant codes in the `tooth` column** (`UR` 3,182
  rows; `quadrant` is empty on all charges), so a quadrant code is a valid tooth and is mirrored
  into `quadrant`. Published at `GET /metadata/procedure-entry-rules`.
- **PROC-INT-3** `procedures.changed` rides the **existing messaging WebSocket** on a new
  tenant-wide topic (`msg:{tenant}:tenant`, `messaging_events.publish_tenant`); every
  procedure/item write announces via [app/services/procedure_events.py](app/services/procedure_events.py).
  No per-patient subscription server-side — the client filters by `patient_id`.
- **PROC-INT-4** `GET /patients/{id}/treatment-plan-items` returns the paginated envelope
  (**breaking**, was a bare array ignoring `size`; default size 200) + `plan_id`/`status`/
  `include_completed` filters. **PROC-INT-5/9** `treatment_plan_items.quadrant`/`material_id`,
  `code_bundle_items.surface`/`quadrant`, `explosion_code_items.quadrant`.
- **PROC-INT-7 applied**: `seed_procedure_code_rules.py` now derives `min/max_surfaces` (36),
  `tooth_area` (12: anterior D2330–35/D2390/D2960–62, posterior D2391–94), `valid_teeth` (12),
  arch-correct `surface_rules.allowed` (21) and `anatomy_rules.allowed_quadrants` (21), and
  always clears junk `tooth_area` (3). `default_material_id` (tenant-scoped materials vs global
  codes) and `draw_as` (a preference) are not derivable and left alone.

**Patient SMS (Twilio) module** (Patient → Messages / SMS-Email log; SMS-1…10 + EMAIL-1 of
[docs/sms/SMS_BACKEND_DEVREPORT.md](docs/sms/SMS_BACKEND_DEVREPORT.md) /
[response](docs/sms/SMS_BACKEND_RESPONSE.md); Alembic `e0f1a2b3c4d5`). The app's
**second anonymous surface** (after AppointNow) and its first outbound carrier integration.
- **The table keeps its legacy shape on purpose**: one row per outbound text with the
  reply on the *same* row — the FE fans `sent_text`/`reply_text` into two inbox entries.
  A stand-alone inbound text is `sent_text IS NULL`, `direction='inbound'`. That is why
  `reply_twilio_sid` exists beside `twilio_sid` (the reply needs its own sid for webhook
  idempotency) and why an inbound within `SMS_REPLY_WINDOW_HOURS` of an unanswered
  outbound lands *on that row* rather than as a new one.
- **All Twilio traffic lives in [app/integrations/twilio_client.py](app/integrations/twilio_client.py)**
  (raw `httpx`, no SDK): one REST call + the `X-Twilio-Signature` HMAC. With
  `TWILIO_ACCOUNT_SID` unset the gateway is **log-only** — `POST /sms/send` still persists
  `queued` and returns 201, nothing reaches a carrier — so tests/dev need no creds. The FE
  probes `GET /sms/send` and treats **405** as Live; `GET /sms/gateway` is the honest
  answer. The **Auth Token is never in the DB** — `messaging_service_sid` on
  `account_communications` / `office_phone_assignments` is a selector, not a credential.
- **Persist-then-send** ([app/services/sms_service.py](app/services/sms_service.py)):
  the row is written before Twilio is called; a rejection is stored as `failed` **and**
  surfaced as 502 `twilio_error` with the row in `details.sms_message`. 409
  `duplicate_client_id` likewise returns the existing row in `details`. SMS-8 consent is
  `patient_opted_out` (automated) / `consent_override_required` (manual without
  `override_consent`); **quiet hours are office-local** (`account_communications.
  sms_quiet_hours_*`, default 8–21) and refuse automated types only — a manual text is a
  human's decision. `send(..., at=)` lets the reminder job judge quiet hours on *its*
  clock; without it the whole batch was evaluated against wall-clock (this also bit the
  test suite every evening — the seed fixture sets an always-open window).
- **Webhooks** (`/sms/webhooks/inbound`, `/status`; async handlers, `run_in_threadpool`
  into the sync service): signature is validated against several URL candidates
  (request URL, `PUBLIC_API_BASE_URL` + path, both schemes, ± trailing slash) because
  Cloud Run rewrites the scheme/host Twilio signed. Validation on + no token = **every
  webhook refused**, never accepted unsigned. A `To` that routes nowhere is **200**, not
  4xx (Twilio would retry forever). Inbound patient match expands E.164 into every legacy
  storage spelling ([app/services/sms_phone.py](app/services/sms_phone.py)) and matches
  with `IN` — no DB regex, so SQLite tests and Postgres behave alike. Confirmation
  keywords act on the appointment (`confirm` → `Confirmed`, `reschedule` →
  `add_to_call_list`); **`cancel` only flags `needs_attention`**, staff cancel. STOP is
  matched on the *whole* body; "yes" re-opts-in only an opted-out patient (Twilio's own
  rule), so "yes" to a reminder stays a confirmation. Status callbacks never regress
  (`status_rank`). Both publish `sms.inbound`/`sms.status` on the messaging WS tenant
  topic ([app/services/sms_events.py](app/services/sms_events.py), SMS-4).
- `SmsMessageCRUD` normalises the FE's log-only `POST /sms-messages` fallback (direction,
  `sent_at`, inferred `message_type`, `Success`→`delivered`) and resolves the SMS-6 inbox
  filters (`date_from/to` on the activity timestamp, `unmatched`, `unread_replies`).
  `infer_message_type` is the Python twin of the migration's SQL `CASE` backfill.
- **SMS-9** `run_reminders` de-dups on `(appointment_id, message_type,
  reminder_lead_hours)` three ways (query, deterministic `client_id`, partial unique
  index) and skips anything older than `SMS_REMINDER_CATCHUP_HOURS` rather than blasting
  after an outage; `scripts/run_sms_reminders.py` is the cron entry. **SMS-10**
  `scripts/purge_sms_messages.py` blanks bodies, keeps rows. **EMAIL-1** mirrors the whole
  shape over SendGrid ([app/services/email_service.py](app/services/email_service.py)).

**Topaz signature capture** (one shared FE `SignatureCapture` component → Medical
History, Progress Notes, Letters consents, Security → Users; SIG-1…10 of
[docs/signature/topaz_signature_backend_devreport.md](docs/signature/topaz_signature_backend_devreport.md)
/ [response](docs/signature/topaz_signature_backend_response.md); Alembic
`b6c7d8e9f0a1`). The pad's **SigString** (the vector stroke record — the actual
biometric record; `signature_data` is only its JPEG) plus point/stroke counts and
pad model/serial were captured by the FE and dropped by every store.
- **One home**: [app/services/signature_service.py](app/services/signature_service.py).
  `normalise_capture` is the single validation/defaulting pass on **every** write
  path (generic CRUD via `PatientSignatureCRUD`/`PatientConsentCRUD`,
  `/medical-history/sign`, `/patient-consents/{id}/sign`, `PUT /users/…/signature`):
  Fernet-encrypts `sig_string` at rest (SIG-4), defaults `sig_format`/`device_*`
  from what was sent, 422 `signature_empty` on `point_count < 2` (only when the
  count is sent — the on-screen pad reports none), unrecognised `device_source`
  **stored as written**. The three stores are `patient_signatures`,
  `patient_consents` and `users.signature_*` (prefixed — `user_column_for`).
- **`sig_string` is never on a read model** — `has_sig_string` is. The only exits
  are admin-only and each read is a `sig_string_exported` audit event:
  `GET /patient-signatures/{id}/sig-string`, `…/patient-consents/{id}/sig-string`,
  `GET /users/{id}/signature?include_sig_string=true`
  ([app/api/v1/signatures.py](app/api/v1/signatures.py)).
- **SIG-8** `signature_audit_events` (captured/superseded/voided/declined/replaced/
  sig_string_exported + ip/user-agent/pad identity), written **inside** the
  write's transaction; `client_ip_ctx`/`user_agent_ctx` in `app/core/logging.py`
  are set by `RequestContextMiddleware` so the CRUD engine can attribute the
  workstation. `GET /signature-audit-events`.
- **SIG-7** document binding: `patient_signatures.progress_note_id`/`consent_id`
  (same-patient enforced, 422 `signature_document_mismatch`) with a
  server-computed `content_hash`; `progress_notes.content_hash` (stamped by
  `/sign`) and `patient_consents.content_hash` (stamped on `status=signed`);
  `signature_status` = `signed|stale|unverifiable|…` on all three reads, **null**
  on an unbound signature row (the API does not guess). **SIG-6 decided**:
  `PUT /users/{id}/signature` is canonical; the user PATCH still takes
  `signature_data` but clears the Topaz block (it described the previous image).
- **SIG-9** `GET /patient-signatures?include_image=false` — rows are `expunge`d
  before `signature_data` is blanked so the strip can never flush as a NULL.
- **Legacy data, applied on the dev DB**: 3,760 migrated rows held a raw SigString
  in `signature_data` (`device_source="0"`; `"2"` = 98 real legacy images; 2 rows
  hold the literal `undefined`). `scripts/migrate_legacy_sigstrings.py` moved them
  into `sig_string` (encrypted), NULLing the image — **no server-side JPEG render**
  (needs Topaz SigPlus, a Windows COM component). Rides along: `patient_signatures`
  has no `tenant_id`, so before `PatientSignatureCRUD._scope_tenant` any tenant
  could read/void any signature by id.
- **Round 2 — ADA claim-form signatures** (SIG-11…16, §5 of the 2026-09-12 report;
  Alembic `6f5fd1cb5b52`, **applied**). `patient_signatures.claim_id` (FK to the
  `VARCHAR(50)` claim id; server `content_hash` over the claimed lines),
  `signer_name`/`signer_relationship` (also on the audit row) and
  **`signer_provider_id`** — the SIG-15 answer: Item 53 keys on the *provider*,
  because most migrated providers have no user account; `signed_by_user_id` stays
  the attesting user, `created_by` the pad operator. New `provider_signatures`
  (1:1, same block as the user store) behind `GET/PUT/DELETE /providers/{id}/signature`
  (GET resolves provider → linked user). `resolve_claim_signatures` is the one
  resolver (pinned-to-claim → latest-of-type on the patient → Item 53: provider
  store → user) used by `assemble` (`authorizations.signatures`), the PDF (images
  drawn on Items 36/37/53, "Signature on File" only when no image; a legacy
  SigString-only row warns `signature_not_printable`) and
  `GET /insurance-claims/{id}/signatures`. `claim_consent` (ADA-BE-7) and the FE's
  `claim_patient_consent` are **both** Item 36. List gains
  `signature_types=a,b` + `latest_per_type=true` (window function).

**Prescriptions Setup round 2** (Setup -> Prescriptions; RX-1/2/4 of
[docs/pick-list/pick_list_setup_backend_devreport.md](docs/pick-list/pick_list_setup_backend_devreport.md)
/ [response](docs/pick-list/pick_list_setup_backend_response.md); Alembic
`239077e738d5`, **applied to the dev DB**). Round 1 (`f1a2b3c4d5e6`) shipped the
Pick List / Macro / Medical / Toolbar pieces and `updated_by`.
- **RX-4 is the same importer defect as `chart_materials` / `code_bundles`**:
  `prescription_library` had no unique key, so `s16`'s `ON CONFLICT DO NOTHING`
  had nothing to conflict on and every migration re-run appended the whole
  Denticon library again — 85 drugs x 5 runs = 425 rows, all byte-identical per
  `legacy_id`, so the Rx Drug Name picker listed each drug five times. The
  migration collapses each `(tenant_id, legacy_id)` group to its lowest id,
  repoints `prescriptions.library_rx_id` + `office_prescription_library` (the only
  two inbound FKs) and adds `uq_prescription_library_tenant_legacy`. Applied
  after a rolled-back dry run: 427 -> 87 rows, 0 dangling refs. **`note_macros`
  has the identical defect (120 groups, 360 extra rows — NM-7) and is not yet
  fixed.**
- **The API-side guard is content-based and deliberately not a constraint**
  ([app/services/prescription_library_service.py](app/services/prescription_library_service.py),
  `PrescriptionLibraryCRUD`): an identical **active** `drug_name + dispense + sig`
  (trimmed, whitespace-collapsed, case-insensitive) is 409 `duplicate_prescription`
  with `allow_duplicate` as the override — the seed legitimately lists
  *Chlorhexidine* twice with different dispense/sig, so same-name/different-config
  (`same_name_matches`) and inactive twins (`inactive_matches`) are reported, never
  blocking. On PATCH it fires on a **move** (or a re-activation), never on stored
  state. `GET /prescription-library/availability` is the same function as a probe.
  The name prefilter is a `LIKE` with whitespace runs as `%` (escaped `%`/`_`) so it
  can over-match but never miss; the exact compare finishes in Python.
- **RX-2**: the schema factory does not propagate column lengths, so the 240-char
  sig rule was FE-only and a 501-char sig was a 500. `SIG_MAX_LENGTH` is enforced
  as 422 `sig_too_long` only when the payload carries `sig`, and published at
  `GET /prescription-library/limits`; the column stays `String(500)` (max live value
  177). **RX-1**: `created_by` + `created_by_name`/`updated_by_name` on the read via
  the shared `attach_actor_names` hook; `drug_name` joined the sortable set.

**Notes Macros Setup round 2** (NM-3/5/6/7 of the same report; Alembic
`3a8f2c41b7d9`, **applied to the dev DB**, re-parented onto `b08a4634a3e3` because
the medical-alert surfacing migration landed alongside). `note_macros` had the
**identical importer defect** (120 legacy macros x 4 runs = 480 identical rows,
every macro list in the app showed each entry four times): same dedupe shape,
inbound FKs `procedure_codes.default_notes_macro_id` (3 repointed) +
`office_note_macros`. Applied: 481 -> 121 rows, 0 dangling refs.
[app/services/note_macro_service.py](app/services/note_macro_service.py)
(`NoteMacroCRUD`) is the Rx guard's twin keyed on **name + category** — 409
`duplicate_note_macro` + `allow_duplicate`, same-name-other-category
(`other_category_matches`) reported never blocking, fires on a move only (the
migrated *Fixed/Detach Try-in* pair is two distinct legacy rows and must stay
editable); a blank category is stored NULL so `/note-macros/categories` never
grows an `""` bucket. `/note-macros/limits` + `/availability` sit on
`progress_notes.macro_router`. NM-6 was simply `name`/`category` missing from the
sortable set. **NM-2 is the remaining blocker**: `category` is still the numeric
Denticon group code and the label lookup was never exported — needs the
practice's code->label list, not code.

**Patient ID / Legacy ID search** (PT-SEARCH-1/2,
[docs/patients/patient_search_backend_response.md](docs/patients/patient_search_backend_response.md);
no migration). `GET /patients` gains `?legacy_id=` (exact, trimmed, resolved in
`PatientCRUD` so a blank matches *nothing* rather than un-filtering), `?id=`
(typed int) and `?ids=` (`id_in_param`), all composing with `home_office_id`/
`is_active`; free-text `search` resolves a legacy id **exact-only** in the top
relevance tier. The requested `(tenant_id, legacy_id)` index was **not** added:
`patients_legacy_id_key` (unique on `legacy_id`, baseline) already makes the
lookup a single-row index probe, and `idx_patients_legacy` is a redundant twin.

**Procedure Codes — supporting-records requirements** (Setup -> Procedure Codes ->
Charting tab, "Supporting Records Required"; PROC-7a…7d of
[docs/procedure_code/procedure_code_supporting_records_backend_devreport.md](docs/procedure_code/procedure_code_supporting_records_backend_devreport.md)
/ [response](docs/procedure_code/procedure_code_supporting_records_backend_response.md);
Alembic `aee911131850`, **applied to the dev DB**). Five per-code flags shaped exactly like
`requires_tooth` — `requires_attachment` / `requires_perio_chart` / `requires_photo` /
`requires_xray` / `requires_missing_tooth_info` (NOT NULL default false; the FE had been
parking them in localStorage because the PATCH silently dropped them). No legacy backfill:
`Codes.txt` has no such columns.
- **What "on file" means lives once** in
  [app/services/supporting_records_service.py](app/services/supporting_records_service.py)
  (`RULES`, published on `/metadata/procedure-entry-rules → supporting_records.rules`):
  attachment = a `patient_documents` row linked by the new `procedure_id`/`claim_id`
  (form fields + list filters on `/patient-documents`, same-patient-validated) or a
  `claim_attachments` row; perio = non-voided exam `≤ DOS` (optionally within
  `SUPPORTING_RECORDS_PERIO_MAX_AGE_MONTHS`); photo = `PH` document or `XC`/`ES` DICOM;
  x-ray = `XR` document or radiographic-modality DICOM study `≤ DOS` (`strict_tooth` →
  tagged instances); missing-tooth = a **dated** missing/extracted `chart_conditions` row
  or a posted extraction charge. Upload time is never treated as capture date, and the
  untyped legacy `image_details` are reported but never satisfy a rule.
- **Enforced at claim submit, advisory on posting** — the record is captured after the
  chair, so a 422 on `POST patient_procedures` would refuse the charge the record is
  about. `POST /insurance-claims/{id}/submit` → 422 `supporting_records_missing`
  (`details.missing[]`) unless `allow_missing_records` (result reports
  `missing_records_overridden`); claim *creation* is not gated because the FE builds a
  claim as POST + per-line PATCH. Readiness reads:
  `GET /patients/{id}/procedure-readiness` (attachment is **`deferred`** before the charge
  exists, never `missing`), `GET /patient-procedures/{id}/readiness`,
  `GET /insurance-claims/{id}/readiness` (+ the derived ADA **Enclosures** block, PROC-7d —
  not persisted, the fill-out has no columns yet). PROC-6 was already answered by
  `GET /fee-schedules/options`.

**Edit Treatment window + Tx Plan → New Appt** (Treatment Plan grid → double-click /
Diag Date → Edit Treatment; "New Appt"; PLAN-9/11/16/17…20/24…29 + PLAN-APPT-1…7 of
[docs/treatment plans/treatment_plan_backend_devreport.md](docs/treatment plans/treatment_plan_backend_devreport.md)
+ [tx_plan_new_appointment_backend_devreport.md](docs/treatment plans/tx_plan_new_appointment_backend_devreport.md)
/ [response](docs/treatment plans/treatment_plan_edit_backend_response.md); Alembic
`9de6ac649cba`, **applied to the dev DB**).
- **PLAN-3 was silently broken on migrated data**: `re_estimate` matched coverage bands
  lexically (`start_code <= code <= end_code`) while migrated plans band on Denticon
  coverage-category codes (`03A`), so every migrated plan estimated 0 %. It now uses
  `estimate_service.match_coverage_rule` (the FEE-1 ranked matcher) — plan and charge
  can never disagree on a band. `?use_new_fees=true` is "Use New Fees" server-side.
- **Item ↔ appointment link** (PLAN-APPT-1/2): `appointment_procedures.treatment_plan_item_id`
  is the FK; `schedule_item` / `release_scheduled_item` in
  [app/services/treatment_service.py](app/services/treatment_service.py) are the only
  two places that move an item into / out of `scheduled`, remembering
  `status_before_scheduled` so cancel / delete puts it back where it was. Every
  appointment write path calls them — `AppointmentCRUD` / `AppointmentProcedureCRUD` in
  [app/services/appointment_service.py](app/services/appointment_service.py) (generic PATCH
  / DELETE / restore) and `scheduler_service.update_status`. `TreatmentPlanItemRead.
  appointment_id`/`appointment_ids` are **derived** from the line FK (one source of truth,
  same shape as `procedure_id`). `POST /treatment-plans/{id}/book` (PLAN-APPT-5) is the
  atomic New Appt: appointment + linked lines + items scheduled, or nothing.
- **Edit Treatment columns** on `treatment_plan_items`: `notes` (PLAN-17 — moved off the
  insurance-detail row, which forced an empty insurance row on uninsured patients),
  `accepted_date` (stamped on first acceptance) / `scheduled_date` (follows the soonest
  live booking), `duration_minutes` (nullable: unset ≠ 0), `created_by`/`updated_by`
  (+ names), `referral_id`/`referral_type`, posting flags `update_end_date_at_posting` /
  `re_estimate_at_posting` (honoured by `/post`), `fee_schedule_id` (PLAN-29: `fee` is
  optional on create → priced via `pricing_service`; an explicit fee only records the
  schedule when it is the one that yields that exact amount), `counselor_user_id`.
  `treatment_plan_item_icd_codes` (PLAN-26) is written through `icd_code_ids` on the item
  (`[]` = clear). Statuses gain `internal_referral`/`external_referral`; vocabularies at
  `GET /metadata/treatment-plan-rules`.
- **PLAN-APPT-3**: `s27b` wrote the Denticon PROVIDERID into `diagnosed_by` (=
  `providers.legacy_id`) and never filled `provider_id`. New items default it (label →
  plan majority → preferred provider; stays nullable — a 422 would break the add panel);
  `scripts/backfill_treatment_plan_item_providers.py` **applied** 693/728. **PLAN-APPT-4**:
  `providers.default_operatory_id` (validated to an office the provider serves) +
  `scripts/backfill_operatory_providers.py` (share ≥ 60 % **and** ≥ 10 appointments;
  dry run only — a wrong default mis-columns every booking). **PLAN-16**:
  `GET /procedure-codes/eligibility?codes=` + `/{code}/providers`; empty = unrestricted;
  no legacy eligibility file exists, so seeding is a Setup task.
- **PLAN-24** `hide_soft_deleted` on items + insurance details. **PLAN-9**
  `preauth_status` (`sent|closed`, 422 otherwise) + stamped `preauth_status_at`. Rides
  along: both tables carry no `tenant_id` and were **unscoped** in the generic engine —
  `TreatmentPlanItemCRUD` / `TreatmentPlanInsuranceDetailCRUD` now scope through
  item → plan → patient. The migrated item ↔ line link is not reconstructable
  (`appointment_procedures` kept no legacy id).

**Patient print module** (Print buttons on Patient Overview · Transactions Entry ·
Account/Patient Ledger · Insurance Details; PRINT-1…10 of
`dentc-frontend/docs/print/patient_print_backend_devreport.md` /
[response](docs/print/patient_print_backend_response.md); **no migration**). The
Print buttons rebuilt each report in the browser with jsPDF from whatever the
screen had loaded, so a print could only contain what the browser held.
- **PRINT-1** `GET /patients/{id}/reports/{overview|ledger|transactions|insurance}`
  → `application/pdf` ([app/api/v1/patient_reports.py](app/api/v1/patient_reports.py)),
  taking the same query params the screens send (ledger: the full `/account-ledger`
  filter/sort set; insurance: `category=D|M` + `order=`, resolved with the FE's own
  slot rule, 404 `insurance_slot_not_found`). Composition in
  [app/services/print_service.py](app/services/print_service.py) through the same
  services the screens read; layout in [app/services/pdf_report.py](app/services/pdf_report.py),
  the reportlab (platypus) twin of the FE's `patientPdf.ts` — header, navy section
  bar, key/value table, blue-headed grid, paragraph, cards, `Page x of y` via a
  two-pass numbered canvas. **`_Section`** replaces `KeepTogether` for a heading +
  grid: stock `KeepTogether` pushes a page-long table to a fresh page and leaves
  the previous one blank. Every print writes an `audit_logs` row (`action='PRINT'`,
  `resource_type='patient_report'`, `details.params`) — `AuditMiddleware` only
  records mutations. `audit_logs.id` is `BigInteger().with_variant(Integer, "sqlite")`
  because a BIGINT PK never auto-increments on SQLite, so every exception-safe
  audit write in the test suite had been silently failing.
- **PRINT-2** `OfficeRead.logo_url` + `.letterhead` (`enrich_office`), resolved once
  in `print_service.resolve_letterhead` from the Statement tab's existing
  `logo_option` (office|custom|none) / `address_source` / `correspondence_name` +
  `account_settings.logo_url`, and used to head every PDF — no new columns.
- **PRINT-3** ledger feed `size` cap 500 → 5,000 (the feeds slice an in-memory
  window, so a larger page costs serialisation only); the PDF has no cap.
- **PRINT-6** `GET /patients/{id}/day-totals?date=` — the deductible is not stored
  on a charge; `day_totals` runs the estimate engine over the day's charges at their
  stored fees against the slot's remaining deductible. Office-local `date` default.
- **PRINT-4/5/7/8/9/10 were already closed** (AL-9 sign rule; PO-1 + the PDF walks
  the account uncapped; `marital_status`/`sub_phone`/`sec_sub_rel_to_prim_sub` —
  the FE binds `sec_rel_to_prim`, a name the API never had; subscriber
  `plan_effective_date`/`plan_term_date` per INS-PT-6, never on `insurance_plans`;
  `ortho_plans.pat_*`; `patients.photo_document_id`, embedded when local).

**Perio charting round 2** (Patient -> Perio Chart; PERIO-BE-9/14/15/16/17/18 of
[docs/Perio Chart/perio_charting_backend_devreport.md](docs/Perio%20Chart/perio_charting_backend_devreport.md)
/ [response](docs/Perio%20Chart/perio_charting_backend_response.md); Alembic
`47371579152e`, **applied to the dev DB**). Round 1 (PERIO-BE-1..13, `f2c3d4e5a6b7`)
shipped the unique tooth row, decimal mobility, CAL, audit columns, bulk upsert,
`/compare` and `/perio-chart-settings/me`.
- **BE-9 was a naming mismatch, not a gap**: the range filter existed as the engine's
  `exam_date_from`/`exam_date_to`; the FE probed `date_from` and read the ignored param
  as "no data". Both names work now (`extra_filters` resolved by `PerioExamCRUD`).
  Unknown query params are **not** rejected — that would be API-wide; the contract is
  "a filter exists iff it is in the route's OpenAPI parameter list".
- **BE-14** `perio_exams.provider_id` (FK `providers`, nullable — no legacy source;
  `created_by` is a *user*) + `provider_name` batched onto the read. 422
  `provider_not_found` (foreign tenant reads the same), `provider_inactive` only on a
  **move** — a retired provider's exam stays editable. Kills the FE's
  `perio:exam_provider` localStorage seam.
- **BE-15 both ways**: `/compare?include_details=true` embeds each exam's rows sorted
  by tooth (`tooth_sort_key`: numeric, then letters; one statement for all exams), and
  `/perio-exam-details?exam_ids=1,2,3` (comma list; empty/garbage matches nothing).
- **BE-16** every percentage divides by `probeable_sites` = 6 x `teeth_charted`,
  clamped 0-100 (was over PD-measured sites -> `200.0`); `sites_measured` keeps meaning
  "sites with a PD"; `sites_with_findings` + `suppuration_pct` added.
- **BE-17/18** `/compare` never drops an id: 404 `perio_exam_not_found` (also for
  another tenant's exam), 422 `exam_not_owned_by_patient`, 422 `perio_exam_voided`
  unless `include_voided=true` — then the voided entry is returned flagged, has no
  delta and is **never a delta baseline**; `delta_vs_exam_id` names the baseline.
- **Ride-along**: the perio tables have no `tenant_id` and the generic routes were
  unscoped (any tenant could read/void any exam by id). `PerioExamCRUD` /
  `PerioExamDetailCRUD` scope through patient -> tenant; creates 404 a foreign
  patient/exam.

**Progress Notes round 2** (PN-6/8/9/11/12 of
[docs/progress notes/progress_notes_backend_devreport.md](docs/progress%20notes/progress_notes_backend_devreport.md)
/ [response](docs/progress%20notes/progress_notes_backend_response.md); Alembic
`17559b3b70d4`, **applied to the dev DB**). PN-1…5/7/8/10 had already landed.
- **PN-12 is the load-bearing fix, and it is a migration bug**: `s35` stored
  `NOTESHTML` verbatim, and the export holds the markup entity-escaped once with
  every `&` replaced by `~^^~` — so 30,322 of 35,286 migrated notes rendered as
  `~^^~lt;p~^^~gt;…`; the plain `notes` export is lossy on its own (`?` for
  `&nbsp;`, collapsed line breaks). The decode is **one** entity level
  (`&amp;lt;` is a typed `<`; a double pass would corrupt it) and lives once in
  [app/services/progress_note_content.py](app/services/progress_note_content.py),
  shared by the importer (`s35` now decodes at source), the write path
  (`ProgressNoteCRUD` derives `notes` from `notes_html` when only the rich body
  is sent, so `search=` cannot drift) and `scripts/repair_progress_note_content.py`
  (dry-run default, JSONL backup + `--restore`, `updated_at` deliberately not
  stamped, signed rows re-hashed, the 4 rx-draw JSON rows moved into
  `drawing_strokes`). **Applied**: 30,322 bodies decoded, 23,305 `notes` regenerated.
- **PN-6 was not blocked** — `DEFINITIONS.txt` group `NOTESMACROS` names every
  `Macrocat` code (`179 → DIAGNOSTIC`) and was already in `definitions` under
  `legacy_id`; `s13` just never joined it. `s13` now resolves the label,
  `scripts/normalize_note_macro_categories.py` relabelled 121/121 macros on the
  dev DB (and filled the blank `key1`), and reads resolve a leftover code
  defensively (`NoteMacroRead.category_label`, `label` on `/note-macros/categories`).
  This also closes **NM-2**.
- **PN-9** the lock day is the *note's office's* day (`note_timezones`: note
  office → patient home office → default), never the UTC date; `ProgressNoteRead`
  reports `timezone` + `locks_at` (office-local midnight as a UTC instant). Storage
  stays UTC (PN-10 is the `UtcDatetime` serialiser). **PN-11** `updated_at`/
  `updated_by`(+`_name`) — `ProgressNoteCRUD.update` now delegates to
  `CRUDBase.update`, so a real change stamps the actor, a no-op PATCH stamps
  nothing (MH-20) and the before/after diff lands in `audit_logs` — which answers
  the **PN-8 open question**: a Date-of-Service correction is audited field-level
  (`GET /patients/{id}/audit-logs?resource_type=progress-notes`). Rides along:
  `progress_notes` has no `tenant_id` and the CRUD was **unscoped** — any tenant
  could read/patch/delete a note by id; now scoped through the patient, and a
  create on another tenant's patient is 404.

**ADA Dental Claim Form (2024)** (claim → DIRECT PRINT; ADA-BE-1…14 + CLM-FO-1…5 of
[docs/claims/ada_claim_form_2024_backend_devreport.md](docs/claims/ada_claim_form_2024_backend_devreport.md)
/ [response](docs/claims/ada_claim_form_2024_backend_response.md); Alembic `3cf1360c0100`,
**applied to the dev DB**). The browser had been assembling all 58 items from ~18 requests
and rendering with jsPDF; every item without a column printed from `localStorage`.
- **One assembler**, [app/services/claim_form_service.py](app/services/claim_form_service.py):
  `assemble` → the whole form as a dict (every derived value tagged `*_source`, plus
  `warnings[]` — a print that silently fell back to the wrong NPI is a rejected claim).
  `GET /insurance-claims/{id}/ada-claim-form` (JSON), `…/reports/ada-claim-form?mode=form|overlay
  &offset_x&offset_y` (PDF, [app/services/ada_claim_pdf.py](app/services/ada_claim_pdf.py) —
  reportlab canvas, **ten lines per form** (rule E) with per-form Item 32, other fees on the
  last), `POST /insurance-claims/reports/ada-claim-form` (batch, one PDF), all audited
  `PRINT`/`claim_report`. Routes in [app/api/v1/claim_forms.py](app/api/v1/claim_forms.py).
- **Columns**: `insurance_claims` gains the three 2024 boxes (`is_epsdt`, `is_locum_tenens`,
  `date_last_srp` — **NULL = derive** from the last D4341/D4342), `icd_qualifier`+`icd_1..4`
  (stored as typed, deliberately no FK), `other_fees`, `missing_teeth` (override of the
  chart-derived set), `other_ins_plan_id`/`has_other_coverage` (captured at creation so a slot
  change cannot re-point a printed claim), and the CLM-FO fill-out boxes (predetermination
  number, remarks, signature_on_file, place_of_treatment, ortho/prosthesis/accident);
  `patient_procedures.diagnosis_pointers`/`quantity`; `offices.npi`/`taxonomy_code` (the
  **Type 2 NPI** — Item 49 uses it when set, else the billing provider's Type 1 with warning
  `billing_entity_npi_missing` when the office has a corporate name) + `treatment_*` address
  (Item 56 physical location); `providers.taxonomy_code` (+ derived
  `effective_taxonomy_code` via [provider_taxonomy_service.py](app/services/provider_taxonomy_service.py));
  `suffix` on patients/responsible_parties, **`sub_suffix`** on subscribers.
- **`InsuranceClaimCRUD`** (ADA-BE-12): `POST /insurance-claims` takes `procedure_ids`
  (not a column) and defaults office / treating (majority of the lines → preferred
  provider) / billing (office's → treating) / plan / carrier / other plan / dates /
  totals in one transaction; the per-line `PATCH claim_id` path fills the same fields
  from the first attached charge. A provider mix is a 422 `claim_provider_mismatch`
  **only** when one provider has `print_separate_claim_form`. Fill-out vocabulary is
  validated on every write; `parse_tooth` errors are re-raised as `invalid_missing_tooth`.
- Item 36 = claim flag **OR** an active `claim_consent` signature (the signature wins;
  `PatientRead.has_claim_consent`). `GET /patients/{id}/tooth-status` is the uncapped
  Item 33 source. `AREA_OF_ORAL_CAVITY` (UR→10 … FM→00, legacy 1–4) lives in
  `procedure_rules_service` and is published on both metadata routes. Submit now freezes
  the assembled form on `claim_submissions.claim_text` and returns `form_warnings`.
- Gotchas met: a pydantic field named `date` shadows the `date` type under
  `from __future__ import annotations` (use `dt.date`); the schema factory's
  `max_length` fires **before** a CRUD normaliser, so a normalised column needs a looser
  wire cap on the write schema (`diagnosis_pointers` 4 → 16); `rules_metadata` is
  duck-typed, no schema.

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
