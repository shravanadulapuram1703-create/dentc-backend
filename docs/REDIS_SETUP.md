# Redis Setup & Deployment Guide (DentC Backend)

> How Redis is used here, how to run it locally, and how to provision/connect it
> on Google Cloud (Memorystore) for deployment. Written for the current code in
> `app/integrations/redis_store.py` + `app/core/config.py`.

---

## 1. What Redis is used for

`app/integrations/redis_store.py` uses Redis for three things:

| Use | Keys | Behaviour if Redis is down |
|---|---|---|
| **Refresh-token whitelist** | `refresh_token:{user_id}:{jti}` | accepted on JWT signature/expiry alone (degraded) |
| **Access-token blacklist** (logout/revoke) | `blacklist:access:{jti}` | treated as *not* blacklisted (fail-open) |
| **Short-lived cache** (e.g. computed balances) | arbitrary | cache miss (recomputed) |

**Graceful degradation is built in.** If `REDIS_ENABLED=False` or Redis is
unreachable, the app keeps working — it just loses server-side token revocation
and caching until Redis is back. After the hardening (see §7), a Redis outage at
*any* point degrades safely and never 500s a request.

---

## 2. The error you hit (and why)

```
redis.exceptions.TimeoutError: Timeout connecting to server
  └ is_access_token_blacklisted() → client.exists() → connect → timeout
```

**Cause:** `config.py` defaults to `REDIS_HOST=localhost`, `REDIS_ENABLED=True`,
and `.env` had no `REDIS_*` overrides — so the app tried `localhost:6379` with no
Redis running there. (A *timeout* rather than "connection refused" usually means
the host is a remote/firewalled IP — e.g. a Memorystore private IP that isn't
reachable from your laptop; see §6.4.)

Pick one of the immediate fixes in §3.

---

## 3. Immediate fix (local dev) — choose ONE

### Option A — Run without Redis (fastest; fine for pure-local dev)
Add to `.env`:
```dotenv
REDIS_ENABLED=false
```
The token store degrades safely. Auth/login/logout all work; token revocation is
simply not enforced locally. **Recommended while everything else is local.**

### Option B — Run a local Redis and point at it
Add to `.env`:
```dotenv
REDIS_ENABLED=true
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
# REDIS_PASSWORD=        # leave unset locally
```
Then start Redis (see §4) and verify `redis-cli ping` → `PONG`.

> Either way, the §7 hardening means a missing/slow Redis can no longer crash
> requests — it logs a warning and degrades.

---

## 4. Running Redis locally (Windows)

Redis has no official native Windows build. Use one of:

### 4a. Docker (recommended)
```powershell
docker run -d --name dentc-redis -p 6379:6379 redis:7-alpine
docker ps                      # confirm it's running
docker exec -it dentc-redis redis-cli ping   # -> PONG
```
Stop/start later: `docker stop dentc-redis` / `docker start dentc-redis`.

### 4b. Memurai (native Windows Redis-compatible service)
Install from memurai.com → runs as a Windows service on `localhost:6379`.
```powershell
redis-cli ping   # -> PONG  (Memurai ships redis-cli)
```

### 4c. WSL2
```bash
sudo apt-get update && sudo apt-get install -y redis-server
sudo service redis-server start
redis-cli ping   # -> PONG
```

### Verify connectivity from the host
```powershell
Test-NetConnection localhost -Port 6379    # TcpTestSucceeded : True
```

---

## 5. Configuration reference (`config.py` ↔ `.env`)

| Setting | Default | `.env` key | Notes |
|---|---|---|---|
| `REDIS_ENABLED` | `True` | `REDIS_ENABLED` | `false` → fully bypass Redis |
| `REDIS_HOST` | `localhost` | `REDIS_HOST` | hostname or IP |
| `REDIS_PORT` | `6379` | `REDIS_PORT` | |
| `REDIS_DB` | `0` | `REDIS_DB` | logical DB index |
| `REDIS_PASSWORD` | `None` | `REDIS_PASSWORD` | required if AUTH enabled (Memorystore) |

The client also sets `socket_connect_timeout=2`, `socket_timeout=2`,
`health_check_interval=30` (see §7) so failures are fast.

---

## 6. Google Cloud — Memorystore for Redis (deployment)

> Use Memorystore when the **backend runs on GCP** (Cloud Run / GCE / GKE).
> Like your Cloud SQL Postgres, it lives inside your VPC.

### 6.1 Enable APIs (once)
```bash
gcloud services enable redis.googleapis.com servicenetworking.googleapis.com
# For Cloud Run access you'll also need:
gcloud services enable vpcaccess.googleapis.com
```

### 6.2 Create the instance
```bash
gcloud redis instances create dentc-redis \
  --size=1 \
  --region=us-central1 \
  --redis-version=redis_7_2 \
  --tier=basic \
  --connect-mode=PRIVATE_SERVICE_ACCESS \
  --network=default
```
- `--tier=basic` = single node (dev/staging). Use `--tier=standard` (HA replica)
  for production.
- `--connect-mode=PRIVATE_SERVICE_ACCESS` keeps it on your VPC (no public IP).

### 6.3 Enable AUTH + (optionally) TLS — recommended for production
```bash
gcloud redis instances update dentc-redis --region=us-central1 \
  --enable-auth
# Retrieve the generated AUTH string (this becomes REDIS_PASSWORD):
gcloud redis instances get-auth-string dentc-redis --region=us-central1
```
Get the host/port the app should use:
```bash
gcloud redis instances describe dentc-redis --region=us-central1 \
  --format="value(host,port)"
# e.g. 10.123.0.3   6379
```
> If you also enable in-transit encryption (`--transport-encryption-mode=SERVER_AUTHENTICATION`),
> the client must use TLS (`rediss://` / `ssl=True` + the server CA). For
> simplicity, basic + AUTH on a private VPC is a common starting point.

### 6.4 ⚠️ You cannot reach Memorystore from your laptop
Memorystore has **no public IP** — it's only reachable from inside the VPC.
So **do not** put the Memorystore IP in your local `.env`; it will time out
(exactly the error above). For local dev keep §3 (local Redis or
`REDIS_ENABLED=false`). To test Memorystore from your machine, tunnel through a
Compute Engine VM in the same VPC:
```bash
gcloud compute ssh redis-jump --zone=us-central1-a \
  -- -N -L 6379:10.123.0.3:6379      # then REDIS_HOST=localhost locally
```

### 6.5 Connect from the backend on GCP

**Cloud Run** — needs a Serverless VPC Access connector to reach the private IP:
```bash
gcloud compute networks vpc-access connectors create dentc-connector \
  --region=us-central1 --network=default --range=10.8.0.0/28

gcloud run deploy dentc-backend \
  --image=REGION-docker.pkg.dev/PROJECT/REPO/dentc-backend:latest \
  --region=us-central1 \
  --vpc-connector=dentc-connector \
  --set-env-vars=REDIS_ENABLED=true,REDIS_HOST=10.123.0.3,REDIS_PORT=6379 \
  --set-secrets=REDIS_PASSWORD=dentc-redis-auth:latest
```
Store the AUTH string in Secret Manager:
```bash
printf '%s' "<AUTH_STRING>" | gcloud secrets create dentc-redis-auth --data-file=-
```

**GCE / GKE** in the same VPC: just set the env vars to the private host/port
(+ password) — no connector needed.

### 6.6 Production env vars
```dotenv
REDIS_ENABLED=true
REDIS_HOST=<memorystore-private-ip>
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=<auth-string>     # from Secret Manager, never committed
```

---

## 7. Code resilience (already applied)

`redis_store.py` was hardened so a Redis outage degrades instead of crashing:
- **Fast timeouts:** `socket_connect_timeout=2`, `socket_timeout=2`,
  `health_check_interval=30`.
- **Every runtime op** (`exists`/`setex`/`get`/`delete`), not just the initial
  `ping()`, is wrapped in `try/except RedisError` → logs a warning, drops the
  cached client (so it reconnects next time), and returns the safe default
  (blacklist→`False`, refresh→`True`, cache→miss).

> Security note: blacklist/refresh checks **fail-open** when Redis is down (chosen
> so an outage can't lock everyone out). If your threat model requires fail-closed,
> change `is_access_token_blacklisted` to raise a 503 instead — but then a Redis
> outage blocks all authenticated traffic. Keep fail-open unless you add HA
> (Standard tier + replica).

---

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Timeout connecting to server` | host is remote/firewalled (e.g. Memorystore IP from laptop) | use local Redis or `REDIS_ENABLED=false` locally; reach Memorystore only from inside the VPC (§6.4) |
| `Connection refused` on localhost:6379 | no local Redis running | start Redis (§4) or `REDIS_ENABLED=false` |
| Works in Docker, fails locally | `.env` has `REDIS_HOST=redis` (Docker service name) | set `REDIS_HOST=localhost` for non-Docker runs |
| Auth works but logout doesn't revoke tokens | Redis disabled/degraded | enable Redis; check logs for "token store degraded" |
| Cloud Run can't reach Memorystore | no VPC connector | attach `--vpc-connector` (§6.5) |

**Quick checks**
```powershell
redis-cli ping                              # PONG = up
Test-NetConnection <host> -Port 6379        # TcpTestSucceeded : True
docker ps                                   # is the redis container running?
```
```bash
gcloud redis instances describe dentc-redis --region=us-central1 --format="value(host,port,authEnabled)"
```

---

## 9. Summary checklist

- **Local now:** add `REDIS_ENABLED=false` to `.env` (or run local Redis per §4). ✔ unblocks the timeout immediately.
- **Local with Redis:** Docker `redis:7-alpine` on `localhost:6379`, `REDIS_ENABLED=true`.
- **GCP:** Memorystore (private), AUTH on, password in Secret Manager; Cloud Run via VPC connector; never point local at the private IP.
- **Resilience:** runtime ops guarded + fast timeouts (done in `redis_store.py`).
