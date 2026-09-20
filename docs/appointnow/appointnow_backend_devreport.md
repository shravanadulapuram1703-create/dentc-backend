# AppointNow — External Online Booking — Backend Dev Report

**Module:** AppointNow (public online booking `/book/:office_code` + staff inbox `/appointnow/requests`)
**Frontend:** `src/features/appointnow/**` · transport flag `VITE_APPOINTNOW_BACKEND` (`api` = real backend, **now the default** · `local` = single-browser demo simulation)
**Backend:** `app/api/v1/appointnow.py` · `app/services/appointnow_service.py` · tables `booking_requests`, `appointnow_reasons` (migration `b3c4d5e6f7a8`)
**Status date:** 2026-09-12
**Verified against:** local backend `127.0.0.1:8000` and the deployed Cloud Run backend used by `https://reckondental.com`

---

## 0. TL;DR for the backend team

| # | Item | Severity | Owner |
|---|------|----------|-------|
| **AN-BUG-1** | **`POST /appointnow/requests/{id}/approve` always fails with HTTP 422 `foreign_key_violation`** (`fk_booking_requests_appointment_id_appointments`). The service assigns `req.appointment_id = appt.id` before the new `Appointment` row is flushed, so Postgres rejects the UPDATE. Nothing is booked; the request stays `pending`. **Staff cannot approve any online booking until this ships.** One-line fix in §3. | **P0 — blocker** | Backend |
| AN-14 | No **reschedule** endpoint for a pending request. The frontend hides the Reschedule action in `api` mode. | P1 | Backend |
| AN-16 | `ContactInput` silently **drops** `insurance_info`, `disclaimer_accepted`, `consent_accepted` (pydantic ignores unknown keys). The frontend now folds them into `notes` as a workaround. Please persist them as real columns. | P1 | Backend |
| AN-6 | No WebSocket/SSE consumer for the Redis `appointnow:{tenant}:{office}` publish. Staff sessions **poll** every 30 s. | P2 | Backend |
| AN-17 | Staff reads (`GET /appointnow/requests`, `/approve`, `/decline`) return `office_code: null` and no actor name (`actioned_by`). Frontend resolves the code from `/offices` and shows no actor. | P2 | Backend |
| AN-18 | `providers.visible_in_appointnow` defaults to **true** → office MOON exposes **91 providers** on the public page, including rows like "Test Test", "TEST@ Tesy", "Hygiene History", "Dental Care McMurray". | P2 (data/config) | Backend + practice admin |
| AN-19 | Public availability for MOON on a weekday offers slots from 08:00 through **22:00** (last start 10:00 PM). Please confirm the office end-of-day cap is applied when the requested provider has no `provider_schedule_days`. | P2 (verify) | Backend |
| AN-20 | Production anti-abuse is effectively off: `APPOINTNOW_TURNSTILE_SECRET` unset (CAPTCHA skipped) and the per-IP rate limit "degrades open" without Redis. | P2 (config) | DevOps |
| AN-21 | No email/SMS to the office on a new request, nor to the patient on approve/decline. | P3 | Backend |
| AN-24 | No `DELETE`/purge for booking requests (spam/test rows can only be declined). | P3 | Backend |

Everything else in the original contract (AN-1/2/3/4/5/7/8/9/10/12/13/15) is **shipped and verified** — see §4.

---

## 1. Incident: external bookings never reached the office (root cause + fix)

**Symptom reported:** booking from `https://reckondental.com/book/MOON` on an external device (patient's phone) never showed up in the office's AppointNow inbox. Booking from a second tab of an already-logged-in browser *did* work.

**Root cause (frontend build configuration, now fixed):** the deployed bundle ran AppointNow in `local` mode. `VITE_APPOINTNOW_BACKEND` defaulted to `local` in `src/shared/config/env.ts`, `.env` set `local`, and neither the `Dockerfile`, `cloudbuild.yaml` nor the Cloud Run deploy workflow passed the variable — so production shipped the **client-side simulation** (localStorage + BroadcastChannel). A request was stored in the *visitor's own browser* and broadcast only to other tabs of that same browser profile. That is exactly why "same browser, new tab" worked and "another device" did not. The deployed backend had `0` rows in `booking_requests` when checked.

The backend had meanwhile shipped the whole `/api/v1/appointnow/*` surface (both the local dev server and Cloud Run answer `GET /api/v1/appointnow/offices/MOON` with the real office + 91 providers + reason catalog), but the frontend was never switched over.

**Frontend fix (this change set):**

- `VITE_APPOINTNOW_BACKEND` now **defaults to `api`**; `local` is opt-in for demos. A production build in `local` mode logs a loud console error.
- `Dockerfile`, `cloudbuild.yaml` and `.github/workflows/deploy-cloud-run.yml` pass `VITE_APPOINTNOW_BACKEND=api` explicitly.
- `RealBookingTransport` rewritten against the **shipped** contract (generated Orval client for the staff surface; a bare axios instance for the anonymous public surface so the shared 401→/login interceptor can never fire — AN-12).
- Staff context (`AppointNowContext`) now **scopes** the inbox / bell badge / toasts to the office selected in the top bar (`office_id` query param) and **polls every 30 s** (plus on tab focus) because there is no push channel (AN-6).
- Approve now lets the **server book atomically** (AN-5) instead of the client booking first — avoids double appointments. The client still runs its scheduler pre-check only to show the rich "Time slot already booked" dialog.
- Contract deltas are normalised in the transport (office_code from `/offices`, contact extras folded into `notes`, missing `actioned_by`/`original_slot`), and capability flags (`supportsReschedule`, `supportsPush`, `booksOnApprove`) drive the UI.
- Public page uses the office's server-side **reason catalog** (`PublicOfficeInfo.reasons`), enforces `requires_provider`, and shows the backend's human error message on submit (slot just taken / rate-limited / CAPTCHA).
- `server.js` no longer sends `X-Frame-Options: DENY` for `/book/*` (CSP `frame-ancestors *`), so practices can embed the page in an `<iframe>` on their own site.

**Deploy note:** the production frontend must be **rebuilt** for the fix to take effect (VITE_* values are baked at build time).

---

## 2. Shipped backend contract (as implemented) vs. the frontend

All routes live under `/api/v1/appointnow` (tag `Appointments`). Public routes have no auth dependency and never return 401.

| Route | Auth | Frontend use | Notes / deltas |
|-------|------|--------------|----------------|
| `GET /offices/{office_code}` → `PublicOfficeInfo` | none | public page header, providers, **reasons** | `reasons[]` served per office (defaults when none configured). `office_code` is globally unique (`offices.office_code UNIQUE`). |
| `GET /offices/{office_code}/availability?date&provider_id&duration_minutes` → `{slots, timezone}` | none | slot picker | Redis-cached 30 s; subtracts appointments + active soft-holds. See AN-19. |
| `POST /offices/{office_code}/requests` (`SubmitRequestInput`) → 201 `BookingRequestRead` | none | submit | Re-validates the slot (409 `slot_unavailable`), rate limit (429), Turnstile (403). **Drops** `insurance_info`/`disclaimer_accepted`/`consent_accepted` (AN-16). `office_code` in the response is set. |
| `GET /requests?status&office_id&q&reason_id&reason_label&is_new_patient&date_from&date_to&sort&page&size≤200` → `{items, counts, page, size, total}` | Bearer | inbox + badge (paged 200/page, `office_id` scope) | `office_code` is **null** on every row (AN-17). Runs the expiry sweep lazily. |
| `GET /requests/{id}` | Bearer | — | |
| `GET /requests/{id}/patient-matches` → `PatientMatch[]` | Bearer | not wired yet (frontend follow-up) | AN-9 delivered server-side. |
| `POST /requests/{id}/approve` (`ApproveInput{appointment_id?, patient_id?, create_patient?, provider_id?, operatory_id?}`) | Bearer | approve | **Books server-side** (ignores `appointment_id`). **Currently 422 — AN-BUG-1.** |
| `POST /requests/{id}/decline` (`{reason?}`) | Bearer | decline | Works (verified). |
| `POST /requests/{id}/reschedule` | — | hidden | **Does not exist** (AN-14). |
| `/appointnow-reasons` CRUD | Bearer | not wired (Setup screen is a frontend follow-up) | Per-office reason catalog. |

`BookingRequestRead` (server) vs `BookingRequest` (UI): server lacks `actioned_by` (name), `original_slot`, and the three contact extras; server adds `patient_id`, `actioned_at`. `contact.*` fields are nullable on read — the UI normalises to empty strings.

---

## 3. AN-BUG-1 — approve fails with a foreign-key violation (P0)

**Repro (local backend, Postgres, 2026-09-12):**

```
POST /api/v1/appointnow/requests/01a0960c-53e7-7000-bf6c-b7159ee8553d/approve
{"appointment_id":null,"patient_id":null,"provider_id":"PRV-181","operatory_id":"op-1-5"}
→ 422 {"error":{"code":"foreign_key_violation","message":"a referenced record does not exist.",
   "details":{"sqlstate":"23503","constraint":"fk_booking_requests_appointment_id_appointments",
   "columns":["appointment_id"],"values":["AN01a0960e10e970008621e3"]}}}
```

Same result with an empty body. Afterwards `GET /appointments/AN01a0960e10e970008621e3` → 404 (the whole transaction rolled back) and the request is still `pending`. Reproduced 3× in a row.

**Cause** (`app/services/appointnow_service.py::approve_request`): the code does `db.add(appt)` and then sets `req.appointment_id = appt.id` in the same unit of work. There is no `relationship()` between `BookingRequest.appointment_id` and `Appointment`, so SQLAlchemy has no dependency edge and emits the `UPDATE booking_requests` **before** the `INSERT INTO appointments` — Postgres rejects the FK.

**Fix (one line):**

```python
    db.add(appt)
    db.flush()  # INSERT the appointment first so booking_requests.appointment_id can reference it

    req.status = "approved"
    req.appointment_id = appt.id
```

(or declare `appointment = relationship("Appointment")` on `BookingRequest` and assign `req.appointment = appt`).

**Why the test suite is green:** `tests/conftest.py` runs on in-memory **SQLite**, which does not enforce foreign keys unless `PRAGMA foreign_keys=ON` is issued per connection. `test_approve_books_appointment` therefore passes while Postgres fails. Consider enabling the pragma in the test engine (`event.listen(engine, "connect", …)`) so FK ordering bugs surface in CI.

Please also apply the same pattern anywhere else a new row's id is assigned to an FK column in the same flush (e.g. `patient_id` from `_patient_crud.create` is already committed separately, so that path is fine).

---

## 4. Verification log (2026-09-12)

Environment: frontend dev server `:5173` in `api` mode, local backend `:8000`, office **MOON** (id 1). Cloud Run was probed read-only.

| # | Step | Result |
|---|------|--------|
| 1 | Anonymous visit `/book/MOON` (no token in localStorage) | `GET /appointnow/offices/MOON` 200 → real name "Excel Dental- Moon, PA", phone/address, 91 providers, server reason catalog (New Patient Exam, Cleaning / Hygiene, Checkup / Recall, …). No "Demo mode" footer. |
| 2 | Time step, Mon 2026-09-14, 60 min | `GET …/availability?date=2026-09-14&duration_minutes=60` 200 → 28 slots 08:00–22:00 (lunch 11:30/12:00 correctly excluded — see AN-19 for the late-evening tail). |
| 3 | Details + Yes/Yes acknowledgements + insurance, **Send request** | `POST …/MOON/requests` **201**, id `01a0960c-…`. Confirmation screen shows the code. Server row: `notes` = free text + `Insurance: …` + `Disclaimer accepted: Yes` + `Contact consent (calls/texts): Yes` (workaround for AN-16). |
| 4 | Staff session (admin), `/appointnow/requests`, no office selected | `GET /appointnow/requests?sort=created_desc&page=1&size=200` 200 → card rendered, **bell badge = 1**, "Office: MOON" resolved from `office_id`, insurance/disclaimer/consent parsed back out of notes. Reschedule button hidden (`supportsReschedule=false`). |
| 5 | Select office "Excel Dental- Moon, PA" in the top bar | List re-queried with `office_id=1`; banner "Showing requests for Excel Dental- Moon, PA"; public link switches to `/book/MOON`. |
| 6 | Second request submitted **via curl** (simulating another device) | `POST …/MOON/requests` 201 (`01a0960d-…`). On the next poll (tab focus) the app showed toast **"New booking request"**, badge 1 → **2**, Pending 2 — without any user action in that browser. |
| 7 | **Approve & book** on request 1 | Client pre-check passed (`/offices`, `/providers`, `/operatories?office_id=1`, `/appointments/scheduler`), then `POST …/approve` → **422 foreign_key_violation** (AN-BUG-1). UI toast "Could not book appointment — a referenced record does not exist."; request stays pending; no orphan appointment (GET → 404). |
| 8 | **Decline** request 2 with a reason | `POST …/decline` 200 → status `declined`, badge 2 → 1, Declined tab count 1, toast "Request declined". |
| 9 | Cloud Run read-only probes | `GET /appointnow/offices/MOON` 200 (same payload as local); `GET /appointnow/requests` 200 `total: 0` — confirms no external request ever reached production. |
| 10 | Cleanup | Both test rows deleted from the local `booking_requests` table (no appointment was ever linked). |

Frontend checks: `npx tsc -b` clean; `npx eslint src/features/appointnow src/shared/config/env.ts` 0 errors.

---

## 5. Open gaps — details and requested contract

### AN-14 — Reschedule a pending request (P1)
`POST /api/v1/appointnow/requests/{id}/reschedule` · body `{ slot: { date, start_time, end_time?, duration_minutes?, provider_id? } }`.
- Only while `status == "pending"` (409 otherwise). Replace the slot, keep the contact untouched, store the patient's first-requested slot in a new `original_slot` (returned on reads), bump `updated_at`, record the actor.
- Run the same conflict check as approve; on overlap return **409** with `details.conflicts[]` (`appointment_id, patient_name, provider_name, operatory_name, start_time, end_time, procedure_label, kind: "provider"|"operatory"`) so the red dialog can list them.
- Re-take the soft-hold for the new time.
Frontend: `RealBookingTransport.rescheduleRequest` + `supportsReschedule` are ready to flip; until then the inbox hides Reschedule and the conflict dialog tells staff to decline and book from the Scheduler.

### AN-16 — Persist the intake acknowledgements (P1)
Add to `ContactInput`/`ContactOut` and `booking_requests`:
`insurance_info: str | None (max 500)`, `disclaimer_accepted: bool`, `consent_accepted: bool`. Reject intake (422) when either acknowledgement is not `true` — these are the legal texts in `types.ts` (`BOOKING_DISCLAIMER_TEXT`, `BOOKING_CONSENT_TEXT`) and must be auditable. Until then the frontend writes them into `notes` with the markers `Insurance:`, `Disclaimer accepted:`, `Contact consent (calls/texts):` and parses them back on read; once the columns exist the frontend will send the fields directly (drop the markers).

### AN-17 — Staff read shape (P2)
- Return `office_code` on every `BookingRequestRead` (join `offices`), not only on the public submit response.
- Return `actioned_by_name` (or embed `{ id, name }`) so the inbox can show "Booked by Jane".
- Expose `original_slot` once AN-14 lands.

### AN-6 — Realtime push (P2)
The service publishes `request.created` / `request.updated` to Redis channel `appointnow:{tenant_id}:{office_id}` but nothing consumes it. Please add a staff WebSocket (e.g. `/api/v1/appointnow/ws?office_id=` reusing the messaging WS auth) or an SSE endpoint that relays those events. The frontend polls every 30 s and on tab focus meanwhile; `RealBookingTransport.subscribe()` is the seam.

### AN-18 — Provider exposure default (P2)
`Provider.visible_in_appointnow` defaults to `True`, so every active provider of an office is offered publicly (MOON: 91, including test/placeholder rows and many duplicates by name). Recommend default `False` + a migration that sets it explicitly, and a Provider Setup toggle (frontend follow-up) so practices curate the list. The engine also assigns the *first* visible provider (alphabetical) to "any provider" requests — with the default on, that is "Ahmed Meer" for every MOON request.

### AN-19 — Availability end-of-day cap (verify)
`GET …/MOON/availability?date=2026-09-15&duration_minutes=60` returns start times up to **22:00** (end 23:00). Lunch is honoured, so the office window is being read; please confirm the office `end_time` (or `schedule_end_hour`) caps the last slot when the provider has no `provider_schedule_days`, and that the provider fallback window is not 00:00–24:00.

### AN-20 — Anti-abuse in production (config, P2)
- Set `APPOINTNOW_TURNSTILE_SECRET` on Cloud Run and add the site key to the frontend (`turnstile_token` is already in `SubmitRequestInput`; the public page needs the widget — frontend follow-up once the key exists).
- `_rate_limit` returns silently when Redis is unavailable ("degrades open"). Confirm `REDIS_ENABLED` on Cloud Run.

### AN-21 — Notifications (P3)
Email/SMS the office on a new request and the patient on approve/decline/reschedule (Twilio is already integrated for patient SMS).

### AN-22 — Patient matching UX (frontend follow-up, server done)
`GET /requests/{id}/patient-matches` and `ApproveInput.patient_id / create_patient` are live. The inbox does not surface matches yet; the approve body sends `patient_id: null` so the appointment is booked with `patient_id = null` and the contact carried in the notes (unchanged behaviour).

### AN-23 — CORS / embedding
`CORS_ORIGIN_REGEX` allows `*.run.app` and `*.reckondental.com`. Embedding the page in an `<iframe>` on a practice's site works (the page itself is served from reckondental.com — frontend `server.js` now allows framing of `/book/*`). Calling the public API **directly** from another origin would need that origin allow-listed.

### AN-24 — Purge endpoint (P3)
`DELETE /api/v1/appointnow/requests/{id}` (admin) for spam/test rows; today rows can only be declined.

### AN-25 — Expiry sweep is lazy
`expire_stale_requests` runs only when a staff user lists requests. A pending request whose slot passed still holds its soft-hold in availability until someone opens the inbox. A periodic job (or running the sweep inside availability) would keep public availability truthful.

---

## 6. Status matrix (original contract)

| Gap | Title | Status 2026-09-12 |
|-----|-------|-------------------|
| AN-1 | Public office info | **Shipped** (+ per-office reasons) |
| AN-2 | Public availability | **Shipped** (Redis cache 30 s) — verify AN-19 |
| AN-3 | Public intake | **Shipped** (rate limit, Turnstile hook, slot re-check, soft-hold) — AN-16 fields missing |
| AN-4 / AN-13 | Staff list + server filters + counts | **Shipped** — AN-17 (office_code, actor) |
| AN-5 | Approve (atomic book) / Decline | Decline **shipped**; Approve **broken (AN-BUG-1)** |
| AN-6 | Realtime push | **Open** (Redis publish only) |
| AN-7 | `visible_in_appointnow` enforced | Shipped — default should flip (AN-18) |
| AN-8 | Slot hold/expiry | **Shipped** (15 min hold; lazy expiry, AN-25) |
| AN-9 | Duplicate-patient matching | **Shipped** (frontend not wired, AN-22) |
| AN-10 | Timezone | **Shipped** (office-local, `timezone` in responses) |
| AN-11 | Public CORS / embedding | Regex allow-list; frontend framing fixed (AN-23) |
| AN-12 | Never 401 on public routes | **Shipped** |
| AN-14 | Reschedule | **Open** |
| AN-15 | Server-side double-booking guard | **Shipped inside approve** (`slot_conflict` 409); generic `POST /appointments` overlap guard still open |

---

## 7. Deployment checklist

**Frontend (this change set):**
- Rebuild + redeploy (`cloudbuild.yaml` / deploy workflow now pass `VITE_APPOINTNOW_BACKEND=api`; the code default is `api` as well).
- Smoke test: open `https://reckondental.com/book/MOON` in a private window → the page must show the real office name and no "Demo mode" footer; submit → `POST /api/v1/appointnow/offices/MOON/requests` 201 in the network tab; the request appears in the inbox of a logged-in staff user with MOON selected within 30 s.

**Backend:**
- Ship AN-BUG-1 (approve) first — nothing can be booked until then.
- Set `APPOINTNOW_TURNSTILE_SECRET`, confirm `REDIS_ENABLED`, and curate `visible_in_appointnow`.
- Then AN-14, AN-16, AN-17, AN-6 in that order.

---

## Appendix — history

- **2026-07-31:** frontend shipped against a client-side simulation; original contract AN-1..AN-12 written here.
- **2026-09-09:** intake acknowledgements (`insurance_info`, `disclaimer_accepted`, `consent_accepted`), staff Reschedule, client-side double-booking guard; AN-13..AN-15 added. Backend `POST /appointments` verified to accept overlapping appointments (201).
- **2026-09-12:** backend surface found shipped; production incident traced to the `local` build flag; frontend cut over to `api`; approve blocker AN-BUG-1 found; this report rewritten as the current status.
