# Fix — appointments 500 (phantom "CORS") + redirect scheme + CORS allow-list

Response to the frontend team's "Backend fix instructions" (2026-07-12). The
WebSocket item (AI-chat) is intentionally deferred for now.

---

## P0 — the "CORS error" on `/api/v1/appointments*` is a **500**, not CORS

**Diagnosis.** The frontend correctly identified this as a server 500 that reached the
browser without CORS headers, so the browser mislabelled it. Two independent fixes:

### P0a (code) — 500s now always carry CORS headers ✅
FastAPI binds the `Exception`/500 handler to Starlette's **`ServerErrorMiddleware`,
which sits *above* `CORSMiddleware`**, so a 500 response never passed back through CORS
(that's why 401 had headers but 500 didn't). Added
[`CatchAllMiddleware`](../../app/middleware/catch_all.py), wired one layer *inside*
CORS in [app/main.py](../../app/main.py). Any unhandled error is now converted to a
`{"error": {"code": "internal_error", …}}` 500 that bubbles back up through CORS with
the `Access-Control-*` headers. A backend fault now shows in the browser as an honest,
readable 500 instead of a phantom CORS error.

### P0b (deploy) — apply the pending DB migrations ✅ now automated in CI
> **Automated:** [.github/workflows/deploy-cloud-run.yml](../../.github/workflows/deploy-cloud-run.yml)
> now runs `alembic upgrade head` (via the Cloud SQL Auth Proxy, inside the freshly built
> image) **before** the Cloud Run deploy. It's idempotent and blocks the rollout on failure,
> so a push to `feature/phase_data_migration` applies the pending appointment columns and
> then deploys. The manual steps below remain valid for a one-off run or verification.

**Root cause of the actual 500:** the production `recondental_migrated` DB is stamped
**below** the current Alembic head (`b0c1d2e3f4a5`) and is missing the appointment
columns added by revision **`a9b0c1d2e3f4` (add scheduler gaps)**:
`appointments.posted_on, cancellation_note, cancellation_reason, add_to_call_list,
created_by, updated_by` and `appointment_procedures.est_patient`.

The scheduler feed runs `select(Appointment, …)`, which loads **every** appointment
column — so one missing column raises `UndefinedColumn` on **every** call, regardless of
params. That's the unconditional, ~300 ms failure. (Sibling routers like `/patients`
work because their migrations *were* applied — which is why the patient-column revision
`a7b8c9d0e1f2` is clearly present but the later appointment revision `a9b0c1d2e3f4` is
not.) The code path itself is correct — `pytest tests/test_scheduler_module.py` passes
against the full schema.

**Fix — bring production to head** (all pending revisions are additive/nullable, safe):

1. Confirm the drift. From a workstation with the **Cloud SQL Auth Proxy** running (or a
   one-off Cloud Run Job) pointed at `recondental_migrated`:
   ```bash
   python -c "from alembic.config import main; main(['current'])"   # prints prod's revision
   python -c "from alembic.config import main; main(['heads'])"     # -> b0c1d2e3f4a5 (head)
   ```
   Or check the columns directly:
   ```sql
   SELECT column_name FROM information_schema.columns
   WHERE table_name = 'appointments'
     AND column_name IN ('posted_on','cancellation_note','cancellation_reason',
                         'add_to_call_list','created_by','updated_by');
   -- 0 rows returned  ==> revision a9b0c1d2e3f4 not applied ==> this bug
   ```
2. Apply migrations:
   ```bash
   python -c "from alembic.config import main; main(['upgrade','head'])"
   ```
   Do **not** run migrations on app startup — apply them out-of-band via the proxy or a
   Cloud Run Job, then roll the service.

---

## P1 — redirects no longer downgrade `https` → `http` ✅ (code)

Cloud Run terminates TLS and forwards to the app as `http`; uvicorn ignored
`X-Forwarded-Proto` because its `forwarded_allow_ips` default (`127.0.0.1`) doesn't match
Cloud Run's front end, so a trailing-slash `307` emitted an `http://` `Location` that
preflighted cross-origin requests can't follow. Fixed by trusting the forwarded proto:

- [Dockerfile](../../Dockerfile) CMD now passes `--forwarded-allow-ips="*"` (the actual
  prod entrypoint).
- [gunicorn_config.py](../../gunicorn_config.py) sets
  `forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "*")` (the PM2 path).

Cloud Run has no direct ingress, so `*` is safe there. This takes effect on the next
image build + deploy.

---

## P2 — CORS tightened to an explicit allow-list ✅ (code + deploy)

Already landed (see [CORS_SW_INCIDENT_REPORT.md](../CORS_SW_INCIDENT_REPORT.md)): the
config strips any `*` from `CORS_ORIGINS` (so it can't reflect arbitrary origins under
`allow_credentials`), defaults to the explicit `reckondental.com` origins, and tightens
`CORS_ORIGIN_REGEX`. Deploy step:
```bash
gcloud run services update dentc-backend --region us-central1 \
  --update-env-vars "CORS_ORIGINS=https://reckondental.com,https://www.reckondental.com"
gcloud run services update-traffic dentc-backend --region us-central1 --to-latest
```

---

## Verification (after rebuild/redeploy + `upgrade head`)

```bash
# expect 200 with a valid token, no http:// redirect:
curl -i "https://dentc-backend-477406612596.us-central1.run.app/api/v1/appointments/scheduler?date_from=2026-07-12&date_to=2026-07-12" \
  -H "Origin: https://reckondental.com" -H "Authorization: Bearer <VALID_JWT>"

# and confirm a forced error now carries CORS headers (honest 500, not phantom CORS):
#   the response should include: access-control-allow-origin: https://reckondental.com
```
Then reload `https://reckondental.com/dashboard` — Today's Appointments / Today's
Schedule should populate.

## Deploy order
The CI workflow now does 1→2→3 automatically on push to `feature/phase_data_migration`:
1. Build + push the new image (P0a + P1 code).
2. `alembic upgrade head` against prod via the Cloud SQL Auth Proxy (P0b) — blocks deploy on failure.
3. `gcloud run deploy …` the new image.

Still do once, out-of-band: set `CORS_ORIGINS` to the explicit allow-list and
`update-traffic --to-latest` (P2) — the workflow doesn't manage env vars. (CORS already
works without it thanks to the code defaults + wildcard-strip, but an explicit list is best.)

**CI prerequisite:** the deploy service account (`WIF_SERVICE_ACCOUNT`) must have
`roles/cloudsql.client` and `roles/secretmanager.secretAccessor` (for the `DATABASE_URL`
secret). If the migration step fails on permissions, grant those and re-run.
