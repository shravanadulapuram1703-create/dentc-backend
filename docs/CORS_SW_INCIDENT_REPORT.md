# Incident Report — "CORS error" on production (`reckondental.com`)

**Date:** 2026-07-12
**Reported symptom:** Browser console on `https://reckondental.com` shows, for backend calls
(e.g. `GET /api/v1/appointments/scheduler`):

```
Access to fetch at 'https://dentc-backend-477406612596.us-central1.run.app/api/v1/appointments/scheduler...'
from origin 'https://reckondental.com' has been blocked by CORS policy:
No 'Access-Control-Allow-Origin' header is present on the requested resource.
```
plus a WebSocket CSP violation and `sw.js ... no-response` network errors.

**Bottom line for the backend team: no backend change is required.** The backend CORS is
correctly configured. The real cause was a **stale service worker on the client**, fixed on the
frontend. This report documents what we verified so the backend side can be confidently ruled out,
plus two small items worth a look.

---

## 1. Backend CORS — verified OK (no action needed)

We tested the live backend directly against the exact failing URL and origin. It returns the correct
CORS headers on **both** the preflight and the actual request:

**Preflight (`OPTIONS`):**
```
HTTP/1.1 200 OK
access-control-allow-origin: https://reckondental.com
access-control-allow-credentials: true
access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT
access-control-allow-headers: authorization
vary: Origin
```

**Actual request (`GET`, no token):**
```
HTTP/1.1 401 Unauthorized
access-control-allow-origin: https://reckondental.com
access-control-allow-credentials: true
```
(The 401 is expected — we sent no bearer token. The CORS header is present, which is the point.)

Repeated 8× with no variance — no stale-revision intermittency.

## 2. Root cause — frontend "zombie" service worker (fixed on frontend)

An earlier PWA build of the SPA registered a Workbox service worker (`/sw.js`). The current build
ships no service worker, but the old one **remained installed in returning users' browsers**. It
intercepted every fetch — including the cross-origin backend API calls — and failed them
(`no-response`), which the browser surfaced as a CORS error even though the backend response was
fine. Because `/sw.js` now returned the SPA's `index.html` (not JS), the browser's service-worker
update check failed and the worker could never self-update or be removed.

**Frontend fix (shipped):** a self-destroying `/sw.js` served `no-cache`, so the browser's update
check evicts the old worker (clears caches, unregisters, reloads). Once every client has updated the
ghost is gone.

## 3. WebSocket — frontend CSP fix (please confirm endpoint behavior)

The console also showed:
```
Connecting to 'wss://dentc-backend-.../api/v1/ai-chat/ws?token=...'
violates the Content Security Policy directive: "connect-src 'self' https:"
```
This was a **frontend** CSP that omitted the `wss:` scheme; we added it (`connect-src 'self' https: wss:`).

**Ask for the backend team:** please confirm the AI-chat WebSocket endpoint
`wss://.../api/v1/ai-chat/ws` is reachable on the public Cloud Run URL and that token-in-query-string
auth (`?token=<jwt>`) is the intended/ supported scheme. Note: passing the JWT in the URL query
string means it can appear in access logs and proxy logs — consider a subprotocol header or a
short-lived ticket token instead if that's a concern.

## 4. Security note — CORS currently reflects *any* origin

While verifying, we observed the backend echoes back **whatever `Origin` is sent**, including
clearly invalid ones:

| Origin sent | `access-control-allow-origin` returned |
|---|---|
| `https://reckondental.com` | `https://reckondental.com` |
| `https://www.reckondental.com` | `https://www.reckondental.com` |
| `http://reckondental.com` (insecure) | `http://reckondental.com` |
| `https://reckondental.com/` (malformed, trailing slash) | `https://reckondental.com/` |

Combined with `access-control-allow-credentials: true`, reflecting arbitrary origins is effectively
"allow all origins with credentials," which is broader than intended and a CSRF/data-exposure risk.
**Recommendation:** set `CORS_ORIGINS` to an explicit allow-list and only echo an origin if it's a
member, e.g.:

```
CORS_ORIGINS=https://reckondental.com,https://www.reckondental.com
```
(add the `dentc-frontend` Cloud Run URL too if it's used directly). Then pin traffic to the latest
revision: `gcloud run services update-traffic dentc-backend --region us-central1 --to-latest`.

---

## Summary of asks for the backend team
1. **CORS:** nothing broken — but tighten `CORS_ORIGINS` from "reflect any origin" to an explicit
   allow-list (§4).
2. **WebSocket:** confirm `wss://.../api/v1/ai-chat/ws` is publicly reachable and confirm/advise on
   the `?token=` auth scheme (§3).
3. No other backend action required — the outage cause was a client-side service worker, fixed on
   the frontend.

---

# Backend team response (2026-07-12)

### 1. CORS — hardened ✅
The "reflect any origin" behaviour you observed came from the **deployed** service running with
`CORS_ORIGINS=*` as a Cloud Run env var. With `allow_credentials=True`, Starlette special-cases `*`
by echoing back whatever `Origin` was sent — exactly the insecure-scheme / trailing-slash reflection
in your table. We've addressed it three ways:

- **Explicit allow-list by default** — `CORS_ORIGINS` now defaults to the localhost dev ports plus
  `https://reckondental.com` and `https://www.reckondental.com`
  ([app/core/config.py](../../app/core/config.py)).
- **Wildcards are now stripped at startup** — even if a stale `CORS_ORIGINS=*` env var lingers, the
  config validator drops the `*` (and logs a warning), so the service can never fall back into
  reflect-any-origin. It relies on the explicit list + a tightened `CORS_ORIGIN_REGEX`
  (`https://([a-z0-9-]+\.)*(run\.app|reckondental\.com)`) which matches only `run.app` /
  `reckondental.com` subdomains over HTTPS.
- **Regression tests** — [tests/test_cors.py](../../tests/test_cors.py) now asserts that
  `http://reckondental.com`, `https://reckondental.com/` (trailing slash), and look-alike hostnames
  (`notreckondental.com`, `reckondental.com.evil.com`) are **not** reflected, and that `*` is stripped.

**Deployment action required (Cloud Run):** set the explicit list and pin traffic to the new revision:
```
gcloud run services update dentc-backend --region us-central1 \
  --update-env-vars "CORS_ORIGINS=https://reckondental.com,https://www.reckondental.com"
gcloud run services update-traffic dentc-backend --region us-central1 --to-latest
```

### 2. WebSocket `wss://.../api/v1/ai-chat/ws` — NOT implemented ⚠️
This endpoint **does not exist in the current backend.** AI chat (including the WebSocket transport)
is a deferred **Phase 4** feature — it only exists in the reference `legacy_app/` and is not wired
into the live `/api/v1` router. So `wss://.../api/v1/ai-chat/ws` currently returns 404 / fails to
upgrade; there is no public endpoint to reach.

- **Frontend action:** the AI-chat client should be feature-flagged off until Phase 4 ships, so it
  doesn't attempt the connection (which produces the console noise you saw).
- **On the `?token=<jwt>` scheme:** we agree it's not ideal — a JWT in the query string leaks into
  access/proxy logs. When we build this in Phase 4 we'll use a **short-lived single-use ticket** (a
  `POST /ai-chat/ws-ticket` that returns an opaque token the WS handshake exchanges), not the raw
  access token in the URL. Flagging here so the frontend can plan for that handshake.

### 3. Service worker — no backend involvement ✅
Confirmed client-side only; the self-destroying `/sw.js` is the right fix. Nothing to do on the API.
