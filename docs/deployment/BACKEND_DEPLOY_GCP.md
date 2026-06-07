# Backend Deployment Runbook — DentC API on Google Cloud Run

> Audience: DentC engineering team.
> Scope: deploy the **FastAPI backend** (`dentc-backend`) to **Cloud Run**, reusing the
> existing Cloud SQL database `recondental_migrated`.
> Deploy the backend **before** the frontend (the frontend bakes the backend URL at build time).

---

## 0. Facts about this service (so the commands make sense)

| Thing | Value |
|---|---|
| App object | `app.main:app` (FastAPI) |
| Server | gunicorn + `uvicorn.workers.UvicornWorker`, binds `$PORT` |
| Container port | `8080` (Cloud Run standard) |
| Health check | `GET /health` → `{"status":"ok","service":"Dental PMS API"}` |
| API docs | `GET /docs` |
| Database | **existing** Cloud SQL Postgres, DB `recondental_migrated`, user `dentc_dev_user` |
| Redis | optional — code runs fine with `REDIS_ENABLED=false` (start here) |
| Config source | environment variables (see `app/core/config.py`) |

**Required runtime config**
| Var | Notes |
|---|---|
| `DATABASE_URL` | SQLAlchemy URL. **Local** = TCP form; **Cloud Run** = unix-socket form (below). Secret. |
| `JWT_SECRET_KEY` | Use a fresh strong value in prod. Secret. |
| `ENCRYPTION_KEY` | Fernet key for encrypted EIN/secrets. **Must match the key that encrypted existing data**, else it won't decrypt. Secret. |
| `ENV` | `prod` |
| `REDIS_ENABLED` | `false` for first deploy |
| `CORS_ORIGINS` | Comma-separated allowed origins = the frontend URL(s). **No `*`** (we send credentials). |

---

## 1. Prerequisites (one-time, each engineer)

- Docker Desktop installed and running.
- Google Cloud SDK (`gcloud`) installed: <https://cloud.google.com/sdk/docs/install>
- Access to the GCP project (ask the project owner). Set these once:

```powershell
gcloud auth login
gcloud config set project reckon-dental        # e.g. reckon-dental
gcloud auth application-default set-quota-project reckon-dental #include after
gcloud auth configure-docker us-central1-docker.pkg.dev
```

Pick the values for your environment and keep them handy:

| Placeholder | Where to find it |
|---|---|
| `<PROJECT_ID>` | GCP console top bar | -->  reckon-dental
| `<INSTANCE_CONNECTION_NAME>` | Cloud SQL → your instance → Overview → **Connection name** (`project:region:instance`) | --> reckon-dental:us-east1:recon-dental-db
| `<REGION>` | `us-central1` (use the same everywhere) |

---

## 2. Test locally FIRST

### 2a. Bare local run (fastest sanity check — no Docker)

```powershell
# from dentc-backend/
dentc-env\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Verify in a second terminal / browser:
- <http://localhost:8000/health> → `{"status":"ok","service":"Dental PMS API"}`
- <http://localhost:8000/docs> → Swagger UI loads
- Try logging in via `/docs` to confirm DB connectivity.

This uses your existing `.env` (which points at the DB over the public IP `35.227.92.85`).

### 2b. Local run **in the Docker image** (this is what Cloud Run actually runs)

Build the image:
```powershell
# from dentc-backend/
docker build -t dentc-backend:local .
```

Run it. We override a few vars so the container behaves like prod but still reaches the DB over TCP
(there's no Cloud SQL socket on your laptop):
```powershell
docker run --rm -p 8080:8080 `
  -e PORT=8080 `
  -e ENV=prod `
  -e REDIS_ENABLED=false `
  -e CORS_ORIGINS=http://localhost:5173 `
  -e JWT_SECRET_KEY=local-test-secret `
  -e "DATABASE_URL=postgresql+psycopg2://dentc_dev_user:Dental%40recon123@35.227.92.85:5432/recondental_migrated" `
  dentc-backend:local
```

Verify:
- <http://localhost:8080/health> → `{"status":"ok",...}`
- <http://localhost:8080/docs> → loads

> Notes
> - The `@` in the DB password is URL-encoded as `%40`.
> - If the DB refuses the connection, the instance's **Authorized networks** must allow your IP
>   (Cloud SQL → Connections → Networking). This is only a concern for *local TCP* testing;
>   Cloud Run connects via the socket and doesn't need an authorized network.
> - `ENCRYPTION_KEY` is only needed if you exercise endpoints that decrypt stored secrets (EIN, etc.).

If 2b passes, the image is good to ship.

---

## 3. Provision GCP resources (one-time)

### 3a. Enable APIs
```powershell
gcloud services enable `
  run.googleapis.com `
  cloudbuild.googleapis.com `
  artifactregistry.googleapis.com `
  sqladmin.googleapis.com `
  secretmanager.googleapis.com `
  iamcredentials.googleapis.com
```

### 3b. Create the Artifact Registry repo (skip if it already exists)
```powershell
gcloud artifacts repositories create dentc `
  --repository-format=docker `
  --location=us-central1
```

### 3c. Create secrets

> ⚠️ **Newline gotcha on Windows:** a trailing newline inside `DATABASE_URL` will break the
> connection. The snippet below writes the value with **no** trailing newline.

```powershell
# DATABASE_URL — unix-socket form for Cloud Run (replace <INSTANCE_CONNECTION_NAME>)
$dbUrl = "postgresql+psycopg2://dentc_dev_user:Dental%40recon123@/recondental_migrated?host=/cloudsql/reckon-dental:us-east1:recon-dental-db"
[System.IO.File]::WriteAllText("$PWD\_secret.txt", $dbUrl)
gcloud secrets create DATABASE_URL --data-file=_secret.txt
Remove-Item _secret.txt

# JWT_SECRET_KEY — generate fresh
$jwt = python -c "import secrets; print(secrets.token_hex(32))"
[System.IO.File]::WriteAllText("$PWD\_secret.txt", $jwt)
gcloud secrets create JWT_SECRET_KEY --data-file=_secret.txt
Remove-Item _secret.txt

# ENCRYPTION_KEY — REUSE the existing key if encrypted data already exists.
# Only generate a new one for a clean environment:
$enc = python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
[System.IO.File]::WriteAllText("$PWD\_secret.txt", $enc)
gcloud secrets create ENCRYPTION_KEY --data-file=_secret.txt
Remove-Item _secret.txt
```

To update a secret later: `gcloud secrets versions add name[DATABASE_URL,JWT_SECRET_KEY, ENCRYPTION_KEY] --data-file=_secret.txt`.
(You can also create/edit secrets in the **Secret Manager** console if you prefer the UI.)

### 3d. Grant the Cloud Run runtime service account access

Cloud Run uses the **compute default service account** by default. Give it secret-read and Cloud SQL access:
```powershell
$PROJNUM = gcloud projects describe <PROJECT_ID> --format="value(projectNumber)"
$SA = "$PROJNUM-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding <PROJECT_ID> `
  --member="serviceAccount:$SA" --role="roles/secretmanager.secretAccessor"
gcloud projects add-iam-policy-binding <PROJECT_ID> `
  --member="serviceAccount:$SA" --role="roles/cloudsql.client"
```

---

## 4. Build & push the image

Run from the **`dentc-backend/` repo root** (where the `Dockerfile` is). Cloud Build builds in the
cloud and pushes to Artifact Registry:

```powershell
gcloud builds submit `
  --tag us-central1-docker.pkg.dev/<PROJECT_ID>/dentc/dentc-backend:latest
```

---

## 5. Deploy to Cloud Run

```powershell
gcloud run deploy dentc-backend `
  --image us-central1-docker.pkg.dev/<PROJECT_ID>/dentc/dentc-backend:latest `
  --region us-central1 `
  --port 8080 `
  --allow-unauthenticated `
  --add-cloudsql-instances <INSTANCE_CONNECTION_NAME> `
  --set-secrets "DATABASE_URL=DATABASE_URL:latest,JWT_SECRET_KEY=JWT_SECRET_KEY:latest,ENCRYPTION_KEY=ENCRYPTION_KEY:latest" `
  --set-env-vars "ENV=prod,REDIS_ENABLED=false,CORS_ORIGINS=https://placeholder.example" `
  --cpu 2 --memory 2Gi `
  --min-instances 1 --max-instances 10 `
  --timeout 120
```

- `--add-cloudsql-instances` is what mounts the `/cloudsql/<INSTANCE_CONNECTION_NAME>` socket the
  `DATABASE_URL` secret refers to.
- `CORS_ORIGINS` is a placeholder for now; update it once the frontend is deployed (Step 7).
- `--min-instances 1` avoids cold starts (costs more). Set `0` to minimize cost.

On success, gcloud prints the **Service URL**: `https://dentc-backend-xxxxxxxx-uc.a.run.app`.

---

## 6. Verify the deployment

```powershell
$URL = "https://dentc-backend-xxxxxxxx-uc.a.run.app"   # paste your real URL
curl "$URL/health"     # -> {"status":"ok","service":"Dental PMS API"}
Start-Process "$URL/docs"
```

If `/health` fails, check logs:
```powershell
gcloud run services logs read dentc-backend --region us-central1 --limit 100
```
Common causes: DB socket/connection-name typo, missing IAM grant from Step 3d, or a stray newline in `DATABASE_URL`.

---

## 7. After the frontend is deployed — fix CORS

Once the frontend has a URL, point the backend at it and redeploy a revision:
```powershell
gcloud run services update dentc-backend `
  --region us-central1 `
  --update-env-vars "CORS_ORIGINS=https://dentc-frontend-xxxxxxxx-uc.a.run.app"
```
(Comma-separate multiple origins. With `allow_credentials=True`, a `*` origin is rejected by browsers — always list exact origins.)

---

## 8. Redeploying after code changes

```powershell
# rebuild + push
gcloud builds submit --tag us-central1-docker.pkg.dev/<PROJECT_ID>/dentc/dentc-backend:latest
# roll out
gcloud run deploy dentc-backend `
  --image us-central1-docker.pkg.dev/<PROJECT_ID>/dentc/dentc-backend:latest `
  --region us-central1
```
(Existing env vars, secrets, and the Cloud SQL connection are retained across redeploys.)

> Optional: wire **continuous deploy from GitHub** (Cloud Run → Edit & deploy → "Continuously deploy
> from a repository") so every push to `main` rebuilds via the committed `Dockerfile`. The manual
> `gcloud` flow above is the source of truth for what that automation does.

---

## 9. Known limitations / follow-ups

- **Uploaded files are ephemeral.** `app/core/filestore.py` writes logos / patient docs to the
  container's local disk, which is wiped on every new revision/instance. Move to a **GCS bucket**
  before production use.
- **Redis is off.** Token blacklist / refresh-token whitelist and cached balances degrade gracefully
  without it. To enable: create Memorystore + a **Serverless VPC Access** connector, attach the
  connector to the service, and set `REDIS_ENABLED=true`, `REDIS_HOST`, `REDIS_PORT`.
- **Migrations.** The reused DB is already migrated. If you add Alembic revisions later, apply them
  via the **Cloud SQL Auth Proxy** from a workstation (`alembic upgrade head`) or a one-off Cloud Run
  Job — do **not** run migrations on app startup.
- **Database connection.** This runbook assumes `recondental_migrated` lives on a **Cloud SQL**
  instance. If it's actually on a plain Compute VM, replace the `--add-cloudsql-instances` + socket
  approach with private-IP networking via a VPC connector.

---

### Quick reference — placeholders to fill in
```
<PROJECT_ID>                 = ____________________
<REGION>                     = us-central1
<INSTANCE_CONNECTION_NAME>   = ____________________   (project:region:instance)
Backend URL (after deploy)   = ____________________
```
