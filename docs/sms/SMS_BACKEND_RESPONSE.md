# Patient SMS (Twilio) — Backend Response

**In reply to:** [`SMS_BACKEND_DEVREPORT.md`](./SMS_BACKEND_DEVREPORT.md)
**Alembic:** `e0f1a2b3c4d5` (revises `d9e0f1a2b3c4`)
**Code:** [`app/api/v1/sms.py`](../../app/api/v1/sms.py) · [`app/services/sms_service.py`](../../app/services/sms_service.py) ·
[`app/integrations/twilio_client.py`](../../app/integrations/twilio_client.py) · [`app/services/sms_phone.py`](../../app/services/sms_phone.py) ·
[`app/services/sms_events.py`](../../app/services/sms_events.py) · [`app/api/v1/email.py`](../../app/api/v1/email.py) ·
[`app/services/email_service.py`](../../app/services/email_service.py) · [`app/integrations/sendgrid_client.py`](../../app/integrations/sendgrid_client.py)
**Tests:** [`tests/test_sms_module.py`](../../tests/test_sms_module.py) (25)

Every gap in the report is implemented. Nothing in the frontend's §1 contract changed: the table
keeps its one-row-per-outbound-text shape, `GET /sms-messages` still pages by `patient_id`, and
`PATCH /sms-messages/{id}` still toggles `is_read`. The FE's `GET /sms/send` probe now receives
**405** (route exists, POST-only), which is the signal it uses for *Live* mode — so read §"Going live"
before deploying with `TWILIO_*` unset, because the gateway then runs in **log-only** mode and the FE
would label the screen Live while nothing reaches a carrier. `GET /sms/gateway` says which mode
the server is actually in; please switch the probe to it.

---

## Status by gap

| Gap | Status | Where |
|---|---|---|
| SMS-1 outbound gateway | **Done** | `POST /sms/send` |
| SMS-2 inbound + status webhooks | **Done** | `POST /sms/webhooks/inbound`, `POST /sms/webhooks/status` |
| SMS-3 schema | **Done + backfilled** | `sms_messages` columns, migration `e0f1a2b3c4d5` |
| SMS-4 real-time push | **Done** | `sms.inbound` / `sms.status` on the messaging WebSocket |
| SMS-5 templates | **Done** | `/sms-templates` CRUD + `POST /sms/render` |
| SMS-6 practice-wide inbox | **Done** | `/sms-messages` filters + denormalised names, `GET /sms/inbox/summary` |
| SMS-7 office → sender mapping | **Done** | `office_phone_assignments` / `account_communications`, `GET /sms/sender` |
| SMS-8 consent / quiet hours / rate limit | **Done** | enforced in `sms_service.send` |
| SMS-9 automated reminders | **Done** | `POST /sms/reminders/run`, `scripts/run_sms_reminders.py` |
| SMS-10 audit + retention | **Done** | `created_by`, payload hashes, `scripts/purge_sms_messages.py` |
| EMAIL-1 e-mail log/send | **Done** | `/email-messages` CRUD, `POST /email/send`, SendGrid webhook |

---

## SMS-1 — `POST /api/v1/sms/send`

Request is exactly the report's shape plus two optional fields:

```jsonc
{
  "patient_id": 2357, "office_id": 3, "appointment_id": "APPT-…" | null,
  "to_phone": "+12107936174", "body": "…", "message_type": "appointment_reminder",
  "client_id": "sms_lx4…",
  "template_id": 12,            // optional — records which template produced it (SMS-5)
  "override_consent": false     // SMS-8 — see below
}
```

Responses (the error body is the app-wide `{"error": {"code", "message", "details"}}` contract,
so the report's `detail:` strings appear as `error.code`):

| Status | `error.code` | When |
|---|---|---|
| **201** `SmsMessageRead` | | the persisted row (`send_status` = Twilio's initial status, or `queued` in log-only mode) |
| 400 | `patient_opted_out` | `patients.no_auto_sms` and `message_type != manual` |
| 400 | `consent_override_required` | `no_auto_sms` and `manual` without `override_consent: true` |
| 404 | `not_found` | patient / office / appointment / template not in the caller's tenant |
| 409 | `duplicate_client_id` | same `client_id` seen before — **`details.sms_message` is the existing row** |
| 422 | `invalid_phone` / `sms_body_too_long` / `sms_invalid_message_type` / `sms_quiet_hours` | validation; quiet hours carries `details.next_allowed_at` |
| 429 | `sms_rate_limited` | per-tenant throttle (`SMS_RATE_LIMIT_PER_MINUTE`, default 60; needs Redis) |
| 502 | `twilio_error` | Twilio rejected the request — `details.code` (e.g. `21211`), `details.message`, and **`details.sms_message` is the row, already persisted as `failed`** with `error_code`/`error_message` |

Behaviour, as specified: the row is written **before** Twilio is called (`queued`, `direction=outbound`,
`sent_at=now`, `from_phone`, `created_by` from the JWT), then updated with `twilio_sid` + Twilio's
initial status + `segments`. A Messaging Service SID is passed as `MessagingServiceSid` when one
resolves (SMS-7), else `From`. `StatusCallback` is `TWILIO_STATUS_CALLBACK_URL`, or derived from
`PUBLIC_API_BASE_URL`, or omitted (the Messaging Service's own setting then applies).

**Log-only mode.** With `TWILIO_ACCOUNT_SID` (+ a credential) unset, `POST /sms/send` still
persists and returns 201 with `send_status="queued"` and no `twilio_sid`, and nothing is sent. The
FE's existing `POST /sms-messages` fallback keeps working too — `SmsMessageCRUD` now stamps
`direction`, `sent_at`, infers a missing `message_type`, normalises `send_status` (`Success` →
`delivered`) and E.164-normalises phones on a hand-posted row.

`GET /sms/gateway` → `{configured, mode: "live"|"log_only", webhook_validation,
webhook_signing_ready, status_callback_url, messaging_service_configured, quiet_hours,
reminders_enabled}`. `GET /sms/sender?office_id=` → which number / service an office sends from
and why (`source`). `GET /sms/metadata` → every vocabulary (message types, statuses, reply
intents, merge fields, STOP/START keyword lists).

## SMS-2 — Webhooks

Both routes are **unauthenticated** and **signed**: `X-Twilio-Signature` is validated with
`TWILIO_AUTH_TOKEN` (HMAC-SHA1 over URL + sorted params, per Twilio's scheme) before the form is
read. Behind Cloud Run the app sees a different scheme/host than Twilio signed, so the check tries
the request URL, `PUBLIC_API_BASE_URL` + path, both schemes and with/without a trailing slash.
`TWILIO_WEBHOOK_VALIDATE=false` disables the check for tunnel testing only; with validation on and
no Auth Token configured **every** webhook is refused (403 `twilio_signature_invalid`) — accepting
unsigned "patient replies" is worse than a dead webhook.

**Inbound** (`POST /sms/webhooks/inbound`, form-encoded):

1. `To` → tenant/office: `office_phone_assignments.phone_number` (office-specific first, then
   shared) → `account_communications.sms_from_phone` → the last office that sent from that number.
   `From` → patient by `cell_phone`/`phone`/`work_phone`. Legacy rows hold bare 10-digit or
   `(210) 793-6174` spellings, so the E.164 `From` is expanded to every storage spelling and matched
   with `IN` ([`sms_phone.phone_variants`](../../app/services/sms_phone.py)). A family sharing the
   number → the patient who most recently received a text (this office preferred); none →
   **unmatched** row (`patient_id=null`) with `candidate_patient_ids` so staff can still pick.
2. Most recent unanswered outbound to that number within `SMS_REPLY_WINDOW_HOURS` (72) → the
   reply lands **on that row** (`reply_text`/`reply_phone`/`reply_received_on`, `is_read=false`,
   `reply_twilio_sid`); otherwise a stand-alone row (`sent_text=null`, `direction=inbound`,
   `send_status=received`, `message_type=inbound_reply`).
3. When the matched outbound row has `appointment_id`: `^(yes|y|confirm|c)` → `confirmed_on=now`,
   `status="Confirmed"`; `^(reschedule|r)` → `add_to_call_list=true`; `^(cancel|no|n)` →
   **`needs_attention=true`, never auto-cancelled**. The classification is stored as
   `reply_intent` (`confirm|reschedule|cancel|stop|start|help|other`). Responds with an empty
   `<Response/>`, or `<Message>` = `SMS_CONFIRMATION_AUTO_REPLY` on a confirmation when set.
4. STOP/STOPALL/UNSUBSCRIBE/CANCEL/END/QUIT (whole body) → `patients.no_auto_sms=true`,
   `sms_opt_out_at=now`, and an `opt_out` row (kept as its own row even when the text also
   answered a reminder, so it shows in the log). START/UNSTOP → `no_auto_sms=false`,
   `sms_opt_in_at=now`, `opt_in` row. A plain "yes" only re-opts-in a currently opted-out patient
   (Twilio's own rule), so "yes" to a reminder stays a confirmation.

Idempotent by `MessageSid` (Twilio retries): a duplicate returns `<Response/>` and writes nothing.
A `To` that maps to no tenant is acknowledged with 200 and logged — a 4xx would make Twilio
retry a message we can never route.

**Status** (`POST /sms/webhooks/status`): row by `twilio_sid`; `delivered` stamps `delivered_on`;
`undelivered|failed|canceled` store `error_code`/`error_message`. Out-of-order callbacks never
regress (`sent` after `delivered` is ignored; terminal failures always win). Unknown sid → 204.

**SMS-4**: every inbound and every status *change* publishes `sms.inbound` / `sms.status` on the
tenant topic of the existing messaging WebSocket (`/api/v1/messaging/ws`) — same envelope style as
`procedures.changed`, string ids, best-effort. Drop the 15 s poll and filter by `patient_id`.

## SMS-3 — Schema

Added to `sms_messages` (all nullable, all on `SmsMessageRead`): `twilio_sid` (unique),
`reply_twilio_sid` (unique — the reply lives on the outbound row, so it needs its own sid for
idempotency), `from_phone`, `direction`, `sent_at`, `error_code`, `error_message`, `segments`,
`client_id` (unique per tenant), `template_id` → `sms_templates`, plus `reply_intent`,
`needs_attention`, `candidate_patient_ids`, `reminder_lead_hours`, `inbound_payload_hash`,
`status_payload_hash`, `updated_at`.

Backfill in the migration (portable SQL, so it ran on the 5,425 legacy rows): `direction` from
which text column is set; `sent_at = COALESCE(delivered_on, created_at)` (the real send time —
`created_at` is the migration date); `send_status 'Success'` → `delivered`; `message_type`
inferred with the **same heuristic the FE applied client-side** (`sms_service.infer_message_type`
is the Python twin, and the generic POST uses it too), so the FE inference can be deleted.

## SMS-5 — `sms_templates`

`GET/POST/PATCH/DELETE /sms-templates` — `{id, tenant_id, office_id|null, name, message_type,
body, is_active, created_by, updated_by, created_at, updated_at}`; filters `office_id`,
`message_type`, `is_active`; DELETE is a soft delete (`is_active=false`).
`POST /sms/render {patient_id, body|template_id, appointment_id?, office_id?}` renders the
`{{merge_fields}}` server-side (needed for SMS-9 anyway) and returns `body`, `unresolved_fields`
(rendered blank, never a literal `{{token}}`), the full `context`, and a GSM-7/UCS-2 `segments`
estimate. Fields: `patient_first_name`, `patient_last_name`, `patient_name`, `appointment_date`,
`appointment_time`, `appointment_datetime`, `provider_name`, `office_name`, `office_phone`.
Client-side rendering can stay; the vocabulary is at `GET /sms/metadata`.

## SMS-6 — Practice-wide inbox

`GET /sms-messages` gains filters `office_id`, `direction`, `send_status`, `needs_attention`,
`reply_intent`, `template_id`, `twilio_sid`, `client_id`, ranges `sent_at_from/to`,
`reply_received_on_from/to`, and `date_from`/`date_to` (inclusive dates on the activity timestamp
= `COALESCE(sent_at, reply_received_on, delivered_on, created_at)`), plus `unmatched=true`
(`patient_id IS NULL`), `has_reply`, `unread_replies=true`. `search=` now covers reply text and the
patient's name/chart. Sortable: `sent_at`, `delivered_on`, `reply_received_on`. Each row carries
`patient_first_name` / `patient_last_name` / `patient_name` / `patient_chart_no` /
`office_name` / `template_name` / `created_by_name` (batched, no N+1).
`GET /sms/inbox/summary?office_id=` → unread / needs-attention / unmatched / failed counts, total
and per office (tab badges). `POST /sms/inbox/mark-read {patient_id?, office_id?}`.

## SMS-7 — Sender mapping

`office_phone_assignments` gains `messaging_service_sid`; `account_communications` gains
`messaging_service_sid` + `sms_from_phone` (tenant default), both editable through the existing
`PATCH /tenants/{id}/communications` / `PUT …/phone-assignments`. Resolution:
office `office_specific` → office `multi_office_shared` → tenant `sms_from_phone` →
`TWILIO_DEFAULT_FROM`; service SID: assignment → tenant → `TWILIO_MESSAGING_SERVICE_SID`.
**No secret is stored in the DB** — the Auth Token / API key live only in the server environment,
the Messaging Service SID is a selector, not a credential.

## SMS-8 — Compliance

- Consent as specified (`patient_opted_out` / `consent_override_required`), STOP/START stamps.
- Quiet hours: `account_communications.sms_quiet_hours_start/end` (default 8–21, **office-local**
  — the patient's own timezone is unknown, and a local practice's patients are local). Automated
  types are refused with 422 `sms_quiet_hours` (+ `next_allowed_at`); `manual` is a human's call.
  The reminder job skips instead and retries on the next run inside its catch-up window.
- Rate limit: `SMS_RATE_LIMIT_PER_MINUTE` per tenant via Redis (`incr_counter`); disabled when
  Redis is off.

## SMS-9 — Automated reminders

`account_communications.sms_reminders_enabled`, `sms_reminder_lead_hours` (JSON, default
`[48, 2]`), `sms_reminder_template_id` (else a built-in body). `scripts/run_sms_reminders.py`
(cron every 10–15 min, `--tenant`, `--dry-run`) and `POST /sms/reminders/run` (admin, this tenant)
both call `sms_service.run_reminders`. A reminder for lead *L* is due when `appt_at − L h` has
passed but is newer than `SMS_REMINDER_CATCHUP_HOURS` (6) — an outage never blasts stale texts.
De-dup key `(appointment_id, 'appointment_reminder', reminder_lead_hours)` is checked, enforced by
the deterministic `client_id = rem_{appt}_{lead}`, **and** by a partial unique index. Skips are
counted by reason (`not_due`, `too_late`, `already_sent`, `opted_out`, `no_phone`, `quiet_hours`,
`no_patient`). Cancelled / completed / no-show / archived appointments are never reminded.

## SMS-10 — Audit + retention

`created_by` from the token on every app send (NULL = the reminder job); SHA-256 of the raw
inbound and last status webhook payloads on the row (disputes without retaining the payload);
`AuditMiddleware` already records the authenticated send. `SMS_RETENTION_DAYS` +
`scripts/purge_sms_messages.py` (dry-run by default) **blank the bodies** past the window and keep
the row — the ledger of *that a text was sent* survives. Twilio's own logs are a separate decision.

## EMAIL-1

`email_messages` (the report's suggested shape + `body_text`, `provider`, `client_id`, `is_read`),
`GET/POST/PATCH/DELETE /email-messages`, `POST /email/send` (same persist-then-send / 409 /
502 `sendgrid_error` / consent model as SMS; `to_email` defaults to the patient's e-mail),
`GET /email/gateway`, and `POST /email/webhooks/sendgrid` (SendGrid Event Webhook, ECDSA-signed
via `SENDGRID_WEBHOOK_PUBLIC_KEY`; matches rows by the `email_message_id` custom arg, then by
`sg_message_id`). Log-only without `SENDGRID_API_KEY` + `SENDGRID_FROM_EMAIL`.

---

## Going live (deploy checklist)

```
TWILIO_ACCOUNT_SID=AC…
TWILIO_API_KEY_SID=SK…            TWILIO_API_KEY_SECRET=…      # sending (preferred)
TWILIO_AUTH_TOKEN=…                                            # REQUIRED: webhook signatures
TWILIO_MESSAGING_SERVICE_SID=MG…                               # or per tenant/office in the DB
PUBLIC_API_BASE_URL=https://<backend-host>                     # derives the status callback + signature URL
TWILIO_WEBHOOK_VALIDATE=true
```

Then in the Twilio console (checklist D): inbound webhook → `https://<host>/api/v1/sms/webhooks/inbound`,
status callback → `https://<host>/api/v1/sms/webhooks/status`. Enter each office's number in
Setup → Account Info → Communications (phone assignments) — that is what routes an inbound `To`
to the office.

## Frontend follow-ups

- Read `GET /sms/gateway` for the Live / Log-only banner instead of probing `GET /sms/send`.
- The 409 body carries the existing row in `error.details.sms_message`; the 502 body carries the
  failed row in `error.details.sms_message` (already persisted — a refetch shows it inline).
- Delete the client-side `message_type` inference and `send_status` normalisation
  (`Success` no longer exists after the migration).
- Subscribe to `sms.inbound` / `sms.status` on the messaging socket and drop the poll.
- Move templates from `localStorage` to `/sms-templates`.
- New inbox screen: `/sms-messages?unread_replies=true&office_id=` + `/sms/inbox/summary`;
  `needs_attention`/`reply_intent` colour the "N / cancel" replies; `candidate_patient_ids` on
  unmatched rows.
