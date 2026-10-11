# AppointNow — Backend Response (round 3: AN-26 / AN-27)

> **Answers:** §AN-26 / §AN-27 of [appointnow_backend_devreport.md](appointnow_backend_devreport.md) (added 2026-10-11)
> **Alembic:** `7cbbcedd2691` (on `e4b31c406999`) — **applied on the dev DB** 2026-10-11 (1 existing request → `not_required`, `payment_terms_accepted` NULL)
> **Code:** [app/services/appointnow_payment_service.py](../../app/services/appointnow_payment_service.py) (new),
> [app/integrations/stripe_client.py](../../app/integrations/stripe_client.py) (new),
> [app/services/appointnow_service.py](../../app/services/appointnow_service.py),
> [app/services/appointnow_notification_service.py](../../app/services/appointnow_notification_service.py),
> [app/api/v1/appointnow.py](../../app/api/v1/appointnow.py), [app/schemas/appointnow.py](../../app/schemas/appointnow.py),
> [app/db/models/appointnow.py](../../app/db/models/appointnow.py), `offices` in [identity.py](../../app/db/models/identity.py),
> [tests/test_appointnow_module.py](../../tests/test_appointnow_module.py)
> **Date:** 2026-10-11

| # | Item | Status |
|---|------|--------|
| AN-26 | Persist the payment acknowledgement | ✅ Shipped |
| AN-27.1 | Per-office / per-reason payment config on the public info | ✅ Shipped |
| AN-27.2 | `awaiting_payment` status + payment block on reads | ✅ Shipped |
| AN-27.3 | `POST …/request-payment` (link + SMS/e-mail + hold extension) | ✅ Shipped (Stripe Checkout, or `manual` without Stripe) |
| AN-27.4 | Payment webhook → atomic booking + ledger posting | ✅ Shipped (`/appointnow/payments/webhooks/stripe`) |
| AN-27.5 | Unpaid link expiry | ✅ Shipped (webhook + sweep) |
| AN-27.6 | Patient-facing status | ✅ Shipped (`GET /appointnow/requests/{id}/status?token=`) |
| AN-27.7 | Refunds | ✅ Mechanism shipped (admin endpoint). **The cancellation / refund *policy* is still a product call** |
| AN-15 | Generic overlap guard on `POST /appointments` | ⏸ Still a product call (unchanged) |

### AN-26 — payment acknowledgement

- `ContactInput.payment_terms_accepted` → `booking_requests.payment_terms_accepted`. It is part of the **422 `acknowledgement_required`** check (`details.field = "payment_terms_accepted"`), alongside the other two. The interim marker `Payment terms accepted: Yes` in `notes` is still understood and removed from the stored note, so the FE can drop `MARK_PAYMENT` whenever it likes. Existing rows are **NULL** ("asked before this existed"), never `false`.
- **Proving the wording (all three acknowledgements):** send `contact.acknowledgement_texts = {disclaimer, consent, payment}` (the exact text shown) and optionally `contact.acknowledgement_version`. The server stores `acknowledgement_hashes = {kind: sha256}` + `acknowledged_at` (server time) on the row, and each distinct text **once** in `booking_acknowledgement_texts` (keyed by hash), so the office can show the exact wording even after the page copy has changed. A client that sends no texts still books; the hashes are just null.
- `APPOINTNOW_REQUIRE_PAYMENT_ACK` (default **true**) exists only so an old embed can keep booking while it is updated.

### AN-27 — payment-required flow

**Config (27.1).** `offices.appointnow_requires_payment` + `appointnow_payment_amount` (editable through the generic `PATCH /offices/{id}`); an `appointnow_reasons` row overrides with `requires_payment` (null = inherit) / `payment_amount`. `GET /appointnow/offices/{code}` now returns `payment: {requires_payment, amount, currency, online_payment_available}` and `requires_payment` / `payment_amount` on each reason. The requirement and amount are **snapshotted onto the request at intake**, so a later Setup change does not re-price a request the patient already saw.

**State machine (27.2).**
```
pending ──request-payment──▶ awaiting_payment ──paid (webhook / mark-paid)──▶ approved
                                    │
                                    └── link lapses ──▶ expired
```
`BookingRequestRead.payment` = `{requires_payment, status (not_required|required|link_sent|paid|expired|refunded), amount, currency, provider (stripe|manual), link_url, link_sent_at, link_sent_via, link_expires_at, note, requested_by_id/_name, paid_at, paid_amount, reference, method, ledger_payment_id, posted_to_ledger, booking_error, refunded_at, refund_amount, refund_reference, refund_reason}`. `counts.awaiting_payment` is new and `?status=awaiting_payment` filters the inbox. `required` is a sixth value beyond the report's list: the office config says payment is needed but no link has been sent yet.

**Request payment (27.3).** `POST /appointnow/requests/{id}/request-payment {amount?, note?, expires_in_minutes? (30–1440), booking?: {patient_id, create_patient, provider_id, operatory_id}}`. The gate is `appointnow_approve_booking`, because the payment leads to a booking.
- With `STRIPE_SECRET_KEY` set, the server creates a Stripe **Checkout Session**: `link_url` is the hosted page, and the request id is in the metadata. It sends the link by SMS (contact consented, not quiet hours) and falls back to e-mail.
- Without Stripe, the provider is **`manual`**: there is no link, and the patient is told the office will take the payment. Staff then record it with `mark-paid` (below).
- The slot soft-hold is **extended to the link's life**, and `awaiting_payment` holds count in availability.
- Calling it again re-sends a fresh link and **expires the old one**, so it can't also be paid.
- `booking` is validated now (bad provider / chair / patient → 422 immediately) and kept for the webhook.

**Paid (27.4).** `POST /api/v1/appointnow/payments/webhooks/stripe` is a public route.
- The `Stripe-Signature` is verified against `STRIPE_WEBHOOK_SECRET` (HMAC, 5-minute tolerance). A bad signature returns 400, and **with no secret set, every event is refused**.
- `checkout.session.completed` (when `payment_status=paid`) and `async_payment_succeeded` **commit the payment first**, then book through the same atomic core as approve (`book_request`, now shared). The booking runs inside a savepoint and is attributed to the staff member who requested the payment.
- If the booking can't complete (for example, the slot was taken meanwhile), the request stays `awaiting_payment` with `payment.status=paid` and `booking_error="slot_conflict: …"`. Staff then approve it by hand (approve accepts `awaiting_payment`), reschedule it, or refund it. **The money is never lost to a rollback.**
- Stripe retries with the same PaymentIntent are idempotent. A *second, different* payment (an old link paid in a race) is recorded on `booking_error` for refund, never dropped.
- Once a patient is linked (`booking.patient_id`, `create_patient`, or a later approve that picks one), the payment is posted as a `patient_payments` credit (`payment_type=patient`, positive magnitude per AL-9, `id AN-…`) and shows as `ledger_payment_id`. Until then it is **unapplied**, held on the request (`posted_to_ledger=false`).
- `POST …/mark-paid {amount?, reference?, method?, book=true, booking?}` records a phone or terminal payment the same way and closes any open link.
- **Approve** of an unpaid payment-required request returns **409 `payment_required`**. `ApproveInput.waive_payment=true` overrides it, and the appointment note records the waiver.

**Expiry (27.5).** A `checkout.session.expired` event for the **current** link (a superseded link's event is ignored), or the sweep (`expire_stale_requests` / `scripts/expire_booking_requests.py`) once `payment_link_expires_at` passes, moves the request to `expired`, releases the hold, sends `payment_expired` to the patient and emits the `expired` push event. **A paid request is never swept**, because money is held against it.

**Patient status (27.6).** The public submit response carries **`status_token`** exactly once. Only its sha256 is stored, and it never appears on staff reads. `GET /api/v1/appointnow/requests/{id}/status?token=` returns `{status, confirmed, slot, reason_label, payment_required, payment_status, payment_amount/currency, payment_link_url (only while payable), payment_link_expires_at, paid_at, office_name/phone}`. It returns no contact details, and an unknown id and a wrong token are both **404** (never 401, AN-12). Suggested FE use: put `request` + token in the confirmation link, and have the Stripe return URL land there.

**Refund (27.7).** `POST …/refund {amount?, reason?}` (admin):
- For a Stripe payment, it refunds at Stripe (idempotent key). For a manual one, it records the refund only.
- If the payment was posted to the ledger, the ledger side follows: a full refund **reverses** the ledger payment with a refund row (REF-2), and a partial refund writes a REF-1 refund against it. The REF-4 policy is checked **before** money moves at Stripe.
- An unbooked request becomes `declined` and its slot is freed. A booked appointment is **left alone** (cancel it in the scheduler).
- **Decline** of a paid request returns **409 `refund_required`**.
- *Who* qualifies for a refund (the 24-hour notice in the consent text) is still a product decision. The endpoint executes whatever staff decide.

**New config / env:** `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `APPOINTNOW_PAYMENT_RETURN_URL` (template: `{office_code}`, `{request_id}`, `{result}` = success|cancel; required when Stripe is on, else 503 `payment_return_url_missing`), `APPOINTNOW_PAYMENT_CURRENCY` (`usd`), `APPOINTNOW_PAYMENT_LINK_TTL_MINUTES` (1440), `APPOINTNOW_REQUIRE_PAYMENT_ACK` (true). In the Stripe dashboard, point a webhook at `/api/v1/appointnow/payments/webhooks/stripe` for `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.expired`, `checkout.session.async_payment_failed`.

**Breaking / behaviour changes:** intake now also 422s without `payment_terms_accepted` (the FE already sends the marker). Approve 409s `payment_required` only for offices / reasons that turn payment on (default off). Decline 409s `refund_required` on a paid request.

**Frontend to-do:**
- Send `payment_terms_accepted` + `acknowledgement_texts` / `acknowledgement_version` directly, and drop the marker.
- Read `payment` from the public office info and show the amount up front.
- Inbox: an "Awaiting payment" tab (`counts.awaiting_payment`), a **Request payment** action (with the "Book with" pick passed as `booking`), Mark paid, Refund (admin), and `booking_error` on the card.
- Keep the `status_token` from submit and add a status page.
- Push events cover every transition, so the card updates live.

---

# AppointNow — Backend Response (round 2)

> **Answers:** [appointnow_backend_devreport.md](appointnow_backend_devreport.md) (status date 2026-09-12)
> **Alembic:** `431b5da5630e` (**applied on the dev database** 2026-09-12 — `recondental_migrated`)
> **Code:** [app/services/appointnow_service.py](../../app/services/appointnow_service.py),
> [app/services/appointnow_notification_service.py](../../app/services/appointnow_notification_service.py) (new),
> [app/api/v1/appointnow.py](../../app/api/v1/appointnow.py), [app/schemas/appointnow.py](../../app/schemas/appointnow.py),
> [app/db/models/appointnow.py](../../app/db/models/appointnow.py),
> [scripts/expire_booking_requests.py](../../scripts/expire_booking_requests.py),
> [scripts/appointnow_visible_providers.py](../../scripts/appointnow_visible_providers.py),
> [tests/test_appointnow_module.py](../../tests/test_appointnow_module.py) (34 tests), [tests/conftest.py](../../tests/conftest.py)
> **Date:** 2026-09-12

## 1. Status by gap

| # | Item | Status | Where |
|---|------|--------|-------|
| **AN-BUG-1** | approve → 422 `foreign_key_violation` | ✅ **Fixed** + verified on Postgres | `db.flush()` before the request is pointed at the new appointment; the AppointNow tests now run SQLite with FKs enforced (`enforce_fks` marker) so the class of bug fails in CI |
| AN-14 | Reschedule a pending request | ✅ Shipped | `POST /appointnow/requests/{id}/reschedule`; `original_slot` on reads; 409 `slot_conflict` + `details.conflicts[]` |
| AN-16 | Persist `insurance_info` / `disclaimer_accepted` / `consent_accepted` | ✅ Shipped | three columns; **422 `acknowledgement_required`** unless both are `true`; the interim `notes` markers are still understood (and lifted into the columns) so deploy order cannot break booking |
| AN-17 | `office_code` + actor name on staff reads | ✅ Shipped | `office_code` on every `BookingRequestRead`; `actioned_by_id` / `actioned_by_name`; `rescheduled_by_*`; `original_slot` |
| AN-6 | Realtime push | ✅ Shipped | `appointnow.request` envelopes on the **existing messaging WebSocket** (tenant topic) — no new socket; see §5 for the subscribe contract |
| AN-18 | `visible_in_appointnow` default | ✅ Shipped + **applied** | opt-**in** (model + server default `false`); migration set every existing row to `false` (99 providers on the dev DB); bulk curation script |
| AN-19 | Availability to 22:00 | ✅ Verified — **data, not code** | MOON's own `office_schedule_days` Monday row ends at **23:04**; Tuesday caps at 16:00 as expected. Ride-along: the office lunch now also applies when a provider row has no lunch of its own |
| AN-20 | Anti-abuse in production | ⚙️ Config + hardening | rate limit no longer degrades *open* without Redis (in-process per-worker window); startup warning outside `ENV=dev` when the Turnstile secret / Redis are missing. Setting the secret + `REDIS_ENABLED` on Cloud Run is still DevOps |
| AN-21 | Notifications | ✅ Shipped (best-effort) | office e-mail on a new request; contact SMS → e-mail on approve / decline / reschedule; channel stamped on the row. Log-only until `SENDGRID_*` / `TWILIO_*` are set |
| AN-24 | Purge endpoint | ✅ Shipped | `DELETE /appointnow/requests/{id}` (admin); approved rows need `?force=true` |
| AN-25 | Lazy expiry sweep | ✅ Shipped (cron) + premise corrected | `scripts/expire_booking_requests.py`; the sweep already ran on every availability computation and a hold is TTL-bounded regardless, so public availability was never stale — only the inbox *status* flip was lazy |
| AN-22 / AN-23 | Patient-match UX / embedding | — | frontend follow-ups, unchanged |
| AN-15 (generic) | Overlap guard on `POST /appointments` | ⏸ Not in this pass | a generic guard changes scheduler semantics app-wide (deliberate double-booking — hygiene + exam — is legitimate); the AppointNow paths are guarded and now return `conflicts[]`. Needs a product call, not a code fix |

## 2. AN-BUG-1 — approve (P0)

Exactly the diagnosis in the report: `BookingRequest.appointment_id` is a bare FK column with no `relationship()`, so the unit of work had no dependency edge and emitted `UPDATE booking_requests` before `INSERT appointments`. `approve_request` now flushes the appointment before pointing the request at it; it is still one transaction.

The reason it was green in CI is closed for this module: `tests/conftest.py` can issue `PRAGMA foreign_keys=ON` on every SQLite connection (turning it off again for `drop_all`, because the schema has FK cycles that cannot be ordered), and `tests/test_appointnow_module.py` opts in with `pytestmark = pytest.mark.enforce_fks`. It is **opt-in rather than suite-wide** on purpose: enabling it everywhere broke at least five other modules (`lab_tracking`, `scheduler`, `reports`, `restorative`, `medical_alert_surfacing`) in two ways — fixtures that insert an operatory referencing a provider in the same flush with no relationship edge (the AppointNow fixture had the same defect and is fixed), and tests that post charges against provider/code ids nothing seeded. Those are real findings but a separate cleanup; once they are fixed the marker check in `conftest.py` can simply be removed to make enforcement the default.

Verified twice: the approve tests (`test_approve_books_appointment`, `test_approve_links_the_appointment_it_inserted`, `test_approve_with_create_patient`, `test_purge_request`) book under SQLite FK enforcement, **and** the full submit → reschedule → approve path was run against the Postgres dev DB (`recondental_migrated`, office MOON) inside a transaction that was rolled back — every statement flushed in order, the request row joined its appointment, nothing persisted.

## 3. AN-14 — reschedule

`POST /api/v1/appointnow/requests/{id}/reschedule`
```json
{ "slot": { "date": "2026-09-15", "start_time": "14:00", "end_time": "14:30",
            "duration_minutes": 30, "provider_id": "PRV-181" } }
```
- Only while `status == "pending"` → otherwise **409 `request_not_pending`**.
- `end_time` / `duration_minutes` optional: the duration is inherited from the current slot (which came from the reason catalog). `provider_id` optional = keep the request's provider; when given it must be an **active provider of the office** (422 `bad_provider` / `provider_inactive`) — it does **not** have to be AppointNow-visible, because that flag gates the public page, not the practice's own scheduling. 422 `slot_in_past` on a slot before office-local now.
- The contact block is never touched. On the **first** reschedule the patient's original slot is frozen into `original_slot_*` (returned as `original_slot`, same shape as `slot`); later reschedules keep it. `reschedule_count`, `rescheduled_by_id` / `rescheduled_by_name`, `rescheduled_at` are recorded; `updated_at` bumps.
- Same conflict check as approve, and both now return the list the red dialog needs:
  ```json
  { "error": { "code": "slot_conflict", "message": "…",
      "details": { "conflicts": [ { "appointment_id": "APT-1", "patient_name": "Sam Lee",
        "provider_id": "PRV-181", "provider_name": "Ahmed Meer", "operatory_id": "op-1-5",
        "operatory_name": "Op 5", "start_time": "15:00", "end_time": "16:00",
        "procedure_label": "Crown prep", "kind": "provider" } ] } } }
  ```
  `kind` is `provider` (reschedule checks the provider only — the request has no chair yet) or `operatory` (approve, when an explicit/derived operatory collides).
- The soft-hold is re-taken for the new time (`hold_expires_at = now + APPOINTNOW_HOLD_TTL_MINUTES`); the availability cache is invalidated for both the old and the new day. A `rescheduled` push event is emitted and the contact is notified (§7).

`RealBookingTransport.rescheduleRequest` + `supportsReschedule = true` can flip.

## 4. AN-16 — intake acknowledgements

`ContactInput` gains `insurance_info` (≤ 500), `disclaimer_accepted`, `consent_accepted`; `ContactOut` returns all three (`false` never `null` on read). Intake **refuses** a request unless both acknowledgements are `true`:
```json
{ "error": { "code": "acknowledgement_required",
             "message": "Both acknowledgements must be accepted to request an appointment.",
             "details": { "field": "disclaimer_accepted", "value": null } } }
```
Nothing is written before the check (the slot stays open).

**Transitional path, on purpose.** A field that is *absent* from the payload (`null`) is looked up in the frontend's interim `notes` markers (`Insurance:` / `Disclaimer accepted: Yes` / `Contact consent (calls/texts): Yes`, the exact `foldContactExtrasIntoNotes` format) before the refusal fires; the values land in the columns and the marker lines are stripped from the stored note. An explicit field always wins over a marker. That means the backend can be deployed before or after the frontend cut-over without a window in which every public booking 422s. Once the frontend sends the fields, the marker path is simply never hit — drop the fold and the parse.

The migration backfilled existing rows from the same markers.

## 5. AN-6 — realtime push (the subscribe contract)

There is no `/appointnow/ws`. AppointNow events ride the **messaging WebSocket the staff client already holds** (`wss://…/api/v1/messaging/ws?token=`) on the tenant-wide topic — the same mechanism as `procedures.changed` (PROC-INT-3) and `sms.inbound` (SMS-4). One socket per workstation, no per-office subscription to manage server-side: **the client filters by `office_id`**. Delivery is Redis Pub/Sub across gunicorn workers when Redis is up, in-process otherwise (the existing messaging caveat), always best-effort — keep the 30 s poll / tab-focus refetch as the reconciliation path, exactly as messaging does.

Envelope:
```json
{ "type": "appointnow.request",
  "event": "created" | "updated" | "rescheduled" | "expired" | "deleted",
  "office_id": 1, "request_id": "01a0960c-…", "status": "pending",
  "request": { …BookingRequestRead… }   // null for "deleted"
}
```
`request` is the full read shape (with `office_code`, actor names, `original_slot`), so the inbox can upsert the card without a refetch. `updated` is approve/decline; `expired` is emitted by the sweep (lazy or cron). `RealBookingTransport.subscribe()` can hook the messaging socket's message stream and set `supportsPush = true`.

## 6. AN-17 — staff read shape

Every `BookingRequestRead` (list, get, approve, decline, reschedule, submit) now carries `office_code` (batched from `offices` per page — one query, never per row) and:

| Field | Meaning |
|-------|---------|
| `actioned_by_id` / `actioned_by_name` | who approved / declined (display name from `users`) |
| `rescheduled_by_id` / `rescheduled_by_name` / `rescheduled_at` / `reschedule_count` | AN-14 |
| `original_slot` | the patient's first-requested slot; `null` until a reschedule |
| `contact.insurance_info` / `disclaimer_accepted` / `consent_accepted` | AN-16 |
| `contact_notified_at` / `contact_notified_via` | AN-21 (`sms` \| `email` \| `null`) |

The report offered `actioned_by_name` *or* an embedded object; the split id + name pair was chosen so the frontend's existing `actioned_by?: string` can bind to `actioned_by_name` unchanged.

## 7. AN-21 — notifications

New [appointnow_notification_service.py](../../app/services/appointnow_notification_service.py). Everything is **best-effort**: a transport failure is logged, never fails the transition that already committed, and with no transport configured the module is log-only (dev/tests need no credentials).

- **Office, on a new request** — one e-mail via SendGrid to `offices.email` → `account_communications.comm_contact_email` → `account_settings.email` (the first set). Body: name, reason, requested slot + provider, phone, e-mail, new-patient flag, insurance, notes, request id. The inbox / push event remains the primary channel.
- **Contact, on approve / decline / reschedule** — **SMS first** when the patient ticked the contact consent (that consent *is* "I consent to receive calls and text messages regarding my appointment"), Twilio is configured, the number normalises to E.164 and the office is outside its **quiet hours** (the same window the SMS module applies to automated texts); otherwise **e-mail** when the request has an address. The channel used is stamped on the row (`contact_notified_at` / `contact_notified_via`) so staff can see whether the patient was told; a request with no usable channel simply stays `null`. The sender is the office's resolved SMS sender (`sms_service.resolve_sender`). The text is sent through the Twilio client directly rather than `sms_service.send`, because the contact is an external person who usually has no `patients` row (that API is keyed on `patient_id` and writes the patient SMS log).

Wording (office name / phone are the office's):
- approved — `{Office}: your appointment request for Mon, Sep 14 at 9:00 AM with Dr. X has been confirmed. Call {phone} if you need to change it.`
- declined — `{Office}: we could not accommodate your appointment request for … ({reason}). Please call {phone} to find another time.`
- rescheduled — `{Office}: your appointment request has been moved to … . Call {phone} if this time does not work.`

## 8. AN-18 — provider exposure

`providers.visible_in_appointnow` is now **opt-in**: model default and server default `false`, and the migration set every existing row to `false` explicitly (dev DB: 99 → 0 visible). With none visible the public page offers "any provider" only (slots computed against active-chair capacity), and staff pick the provider on approve (`ApproveInput.provider_id`) — the alphabetical "Ahmed Meer" default is gone with the default. Curate per office from Provider Setup (the flag is a plain writable column on `PATCH /providers/{id}`) or in bulk:
```bash
python -m scripts.appointnow_visible_providers --office MOON --list
python -m scripts.appointnow_visible_providers --office MOON --set PRV-181,PRV-204
```
Staff reschedule deliberately accepts any *active* provider of the office, visible or not.

## 9. AN-19 — verified against MOON's data

The engine reads the office's own per-day row first and falls back to `schedule_start_hour`/`schedule_end_hour` (10 → 15 on MOON) only when no row exists; a provider with no `provider_schedule_days` inherits the **office** window, never 00:00–24:00. MOON's `office_schedule_days`:

| day | start | end | lunch |
|-----|-------|-----|-------|
| Mon | 08:00 | **23:04** | 12:00–12:30 |
| Tue–Thu | 08:00 | 17:00 | 11:00/12:00–12:30 |
| Fri–Sun | closed | | |

Live on the dev DB: Mon 2026-09-14 → 27 slots, last start **22:00** (the 23:04 cap); Tue 2026-09-15 → 13 slots, last start **16:00**. So the 22:00 tail is the office's Monday row (almost certainly a typo for 17:04 / 13:04) — fix it in Setup → Office Hours; no code change. One ride-along: a provider row that carried no lunch of its own used to re-open the office lunch; it now inherits it.

## 10. AN-20 — anti-abuse

- `_rate_limit` no longer degrades *open*: without Redis it falls back to an in-process sliding window (per worker, so N workers allow up to N× `APPOINTNOW_RATE_LIMIT_MAX` per window — weaker than the shared counter, no longer unlimited).
- Startup logs a **warning** when `ENV != dev` and `APPOINTNOW_TURNSTILE_SECRET` is unset, or Redis is unavailable (rate limit per worker, push events in-process).
- The Cloud Run values themselves (`APPOINTNOW_TURNSTILE_SECRET`, `REDIS_ENABLED` + host) remain a DevOps task; the frontend needs the matching site key for the widget.

## 11. AN-24 / AN-25

- `DELETE /api/v1/appointnow/requests/{id}` (**admin**): hard delete, `deleted` push event. An **approved** request is the audit link to a real appointment → 409 `request_approved` unless `?force=true`; the appointment is never touched either way.
- `python -m scripts.expire_booking_requests [--tenant N]` every 5–15 min flips passed slots to `expired` (and emits the `expired` event) without waiting for someone to open the inbox. Premise correction: the sweep already ran on every public availability computation, and `hold_expires_at` bounds a hold to 15 min regardless of status, so public availability was already truthful — only the inbox status/badge was lazy.

## 12. Breaking / behaviour changes

- **Intake 422s without both acknowledgements** (explicit fields or the interim markers). Any other client of the public intake must send them.
- **Every existing provider is now hidden from the public page** (AN-18, applied). Curate before the next demo.
- `slot_conflict` now carries `details.conflicts[]` (additive).
- The old `appointnow:{tenant}:{office}` Redis channel is gone; events are on the messaging tenant topic.

## 13. Deployment checklist (backend)

1. `alembic upgrade head` (`431b5da5630e`) — done on the dev DB.
2. Curate `visible_in_appointnow` per office (script or Provider Setup).
3. Cloud Run: `APPOINTNOW_TURNSTILE_SECRET`, `REDIS_ENABLED`, and for AN-21 `SENDGRID_API_KEY` + `SENDGRID_FROM_EMAIL`, `TWILIO_*` (already needed by patient SMS).
4. Cron: `scripts/expire_booking_requests.py`.
5. Frontend: send the AN-16 fields directly (drop the notes fold/parse), flip `supportsReschedule`, bind `actioned_by_name` / `original_slot` / `office_code`, subscribe to `appointnow.request` on the messaging socket and flip `supportsPush`.

## AN-28 / AN-29 — operatory pick + emergency requests (2026-10-11)

- **AN-28:** `PublicOfficeInfo.operatories[]` (`id, name, provider_id, provider_name`; active chairs in `display_order`); `GET …/availability?operatory_id=` only returns times that chair is free (appointments + live holds in it) and stamps `operatory_id/operatory_name` on each slot; `SlotInput.operatory_id` is re-checked at intake and stored on `booking_requests.operatory_id`; approve books into it unless overridden; reschedule accepts `slot.operatory_id` and checks operatory conflicts. Reads expose `slot.operatory_id/operatory_name`.
- **AN-29:** `SubmitRequestInput.is_emergency` skips the open-slot re-check (only `end > start` and not-in-the-past → 422 `slot_in_past`); `BookingRequestRead.is_emergency`.
- Migration `a28e9c1d0b7f` (after `7cbbcedd2691`): `booking_requests.operatory_id` (FK operatories, nullable), `booking_requests.is_emergency` (bool, default false).
- Tests: `tests/test_appointnow_module.py` (`test_public_info_lists_active_operatories`, `test_availability_by_operatory_skips_booked_chair_times`, `test_submit_with_operatory_holds_that_chair_and_approve_books_it`, `test_emergency_request_accepts_a_taken_time`, `test_emergency_request_in_the_past_is_refused`).
