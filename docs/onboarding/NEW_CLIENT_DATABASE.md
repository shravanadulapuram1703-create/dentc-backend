# Onboarding a new client organisation (dedicated database + deployment)

Follow this every time a new client organisation is brought on. Each client gets:
- its **own database**
- its **own buckets**
- its **own secrets**
- its **own Cloud Run service**

Every client runs the **same container image**. The clients share the Cloud SQL instance, the Memorystore Redis instance and the VPC, but are isolated inside each.

> **Why each piece must be separate:** every client DB starts numbering at
> `tenant_id = 1`, `user_id = 1`, `patient_id = 1`. Anything shared that is keyed
> by those ids would mix two clients' data:
> - Redis keys: `refresh_token:{user_id}:…`, `msg:{tenant}:{user}`, balance cache
> - Bucket paths: `documents/notes/{tenant_id}/{patient_id}/…`
> - JWTs: a token for user 1 of client A would be valid against client B
>
> So **buckets, `REDIS_DB`, `JWT_SECRET_KEY` and `ENCRYPTION_KEY` are not optional per client.**

Placeholders used below:

| Placeholder | Example | Meaning |
|---|---|---|
| `<client>` | `tdg` | short lowercase slug: letters, digits, `-` |
| `<CLIENT_DB>` | `tdg_db` | database name. **Keep it lowercase**: mixed case forces quoting everywhere |
| `<client_app>` | `tdg_app` | the client's own DB user |
| `<N>` | `1` | the client's Redis DB index, 1–15 (0 = the existing deployment) |
| `PROJECT` | `reckon-dental` | GCP project |
| `INSTANCE` | `reckon-dental:us-east1:recon-dental-db` | Cloud SQL connection name |
| `DB_IP` | `35.227.92.85` | Cloud SQL public IP, used for one-time setup from your machine |
| `REGION` | `us-central1` | Cloud Run region |

Run commands in `cmd`, from the repo root, with the venv activated. Shell commands **never end with `;`**.

```bash
set PATH=C:\Program Files\PostgreSQL\18\bin;%PATH%
```

---

## 0. Collect from the client before you start

- [ ] Practice / organisation name, and the slug `<client>`
- [ ] Admin user: name, e-mail, username
- [ ] Domains: frontend URL (e.g. `https://tdg.reckondental.com`) and, optionally, an API domain
- [ ] Which integrations they will use, and their own credentials for each:
  - [ ] SMS: their RingCentral account and number
  - [ ] E-mail sender: Graph / SMTP / SendGrid, and the from-address
  - [ ] Online booking payments: their own Stripe account
  - [ ] AppointNow Turnstile site
- [ ] A signed BAA if required (HIPAA). Their PHI goes into your GCP project.

Add a row to the **client registry** (§13) now, and pick the next free `<N>`.

---

## 1. Database

**1.1 Create the client's own DB user.** Don't reuse `dentc_dev_user`, which can reach every client's DB.
```bash
gcloud sql users create <client_app> --instance=recon-dental-db --project=reckon-dental --password=<strong password>
```

**1.2 Create the DB as that user, so it owns everything in it:**
```bash
createdb -h DB_IP -U <client_app> <CLIENT_DB>
```
```bash
psql -h DB_IP -U <client_app> -d <CLIENT_DB> -c "REVOKE CONNECT ON DATABASE <CLIENT_DB> FROM PUBLIC"
```

**1.3 Copy the schema** from the source DB (structure only, no data):
```bash
pg_dump -h DB_IP -U dentc_dev_user --schema-only --no-owner --no-privileges -f schema.sql recondental_migrated
```
```bash
psql -h DB_IP -U <client_app> -d <CLIENT_DB> -f schema.sql
```
- One error is expected and harmless: `unrecognized configuration parameter "transaction_timeout"` (pg_dump 18 against a Postgres 15 server).
- Any other `ERROR:` line means stop and investigate.
- Delete `schema.sql` afterwards.

> Do **not** build the schema with `alembic upgrade head` on an empty DB. Several
> early revisions create tables from today's models, and later revisions then fail
> on a duplicate column.

**1.4 Stamp the Alembic revision.** All later steps in this window target the new DB:
```bash
psql -h DB_IP -U dentc_dev_user -d recondental_migrated -t -c "select version_num from alembic_version"
```
```bash
set DATABASE_URL=postgresql+psycopg2://<client_app>:<url-encoded password>@DB_IP:5432/<CLIENT_DB>
```
```bash
python -c "from alembic.config import main; main(['stamp','<version from above>'])"
```
```bash
python -c "from alembic.config import main; main(['upgrade','head'])"
```
```bash
python -c "from alembic.config import main; main(['current'])"
```
`current` must print `<rev> (head)`.

**URL-encoding the password:** in a URL, `@` becomes `%40`, `#` becomes `%23` and `%` becomes `%25`.

---

## 2. Tenant + first admin

Start the API locally against the new DB (`DATABASE_URL` is still set in this window):
```bash
uvicorn app.main:app --port 8001
```
1. Open http://localhost:8001/docs and use `POST /api/v1/auth/signup`. Send:
   - `practice_name`
   - `practice_code` (= `<client>`)
   - `email`, `username`, `password`
   - `first_name`, `last_name`
2. The tenant in a fresh DB is id **1**. Confirm with:
   ```bash
   psql -h DB_IP -U <client_app> -d <CLIENT_DB> -c "select id, code from tenants"
   ```
3. Stop the server with Ctrl+C.

---

## 3. Shared reference data (procedure codes, fees, letters, macros, Rx)

The first command is a dry run with exact counts. The second, with `--apply`, writes.
```bash
python -m scripts.clone_reference_data --source-url postgresql+psycopg2://dentc_dev_user:<pw>@DB_IP:5432/recondental_migrated --target-url %DATABASE_URL% --source-tenant 1 --target-tenant 1
```
```bash
python -m scripts.clone_reference_data --source-url postgresql+psycopg2://dentc_dev_user:<pw>@DB_IP:5432/recondental_migrated --target-url %DATABASE_URL% --source-tenant 1 --target-tenant 1 --apply
```
Expected counts (Oct 2026):

| Table | Rows |
|---|---|
| procedure_codes | 1,122 |
| permissions | 363 |
| icd_codes | 266 |
| fee_schedules | 51 |
| fee_schedule_entries | 13,494 |
| letter_templates | 153 |
| note_macros | 121 |
| prescription_library | 87 |

Options:
- `--active-only` leaves inactive rows behind.
- A re-run refuses if the tables are already filled. `--skip-existing` skips those tables instead.

The clone does **not** copy fee-schedule assignments or office default schedules. The client sets those up in the Fee Schedule Wizard once their offices and providers exist.

---

## 4. Per-tenant defaults (existing seeders)

```bash
python -m scripts.seed_permissions --tenant 1
python -m scripts.seed_account_definitions --tenant 1
python -m scripts.seed_transaction_definitions --tenant 1 --apply
python -m scripts.seed_insurance_plan_definitions --tenant 1 --apply
python -m scripts.seed_chart_defaults --tenant 1
python -m scripts.seed_aux_codes --tenant 1
python -m scripts.seed_restorative --tenant 1
```
Skip `seed_medical_history_catalogs`. The built-in catalogs serve the screen, and seeding them can't safely be undone.

---

## 5. Buckets (yes, new ones per client)

Bucket object paths are `{prefix}/{tenant_id}/{patient_id}/…`, and every client is tenant 1. **A shared bucket would put two clients' patient files in the same folders.** Create:

| Bucket | Used by | Setting |
|---|---|---|
| `rd-<client>-documents` | patient documents, notes, consents | `GCS_BUCKET_DOCUMENTS` |
| `rd-<client>-imaging` | DICOM originals + derived renders | `GCS_BUCKET_ORIGINALS`, `GCS_BUCKET_DERIVED` (prefixes keep them apart) |

```bash
gcloud storage buckets create gs://rd-<client>-documents --project=reckon-dental --location=us-central1 --uniform-bucket-level-access --public-access-prevention
```
```bash
gcloud storage buckets create gs://rd-<client>-imaging --project=reckon-dental --location=us-central1 --uniform-bucket-level-access --public-access-prevention
```
Optional but recommended for PHI: turn on versioning or soft-delete retention, and set a lifecycle policy that matches the client's record-retention contract.

---

## 6. Runtime service account (one per client)

A dedicated identity means a bug or leak in one client's service can't read another client's buckets.
```bash
gcloud iam service-accounts create dentc-<client>-run --project=reckon-dental --display-name="DentC <client> runtime"
```
Let `SA` = `dentc-<client>-run@reckon-dental.iam.gserviceaccount.com`. Grant it:
```bash
gcloud projects add-iam-policy-binding reckon-dental --member=serviceAccount:SA --role=roles/cloudsql.client
```
```bash
gcloud storage buckets add-iam-policy-binding gs://rd-<client>-documents --member=serviceAccount:SA --role=roles/storage.objectAdmin
```
```bash
gcloud storage buckets add-iam-policy-binding gs://rd-<client>-imaging --member=serviceAccount:SA --role=roles/storage.objectAdmin
```
Signed download URLs are created by the service account signing as itself, so it needs:
```bash
gcloud iam service-accounts add-iam-policy-binding SA --member=serviceAccount:SA --role=roles/iam.serviceAccountTokenCreator
```

---

## 7. Secrets (Secret Manager, one set per client)

Generate fresh values. **Never copy another client's values.**
```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
The first prints a `JWT_SECRET_KEY`, the second an `ENCRYPTION_KEY`.

> **Back up `ENCRYPTION_KEY` securely.** It encrypts the client's EIN, AI-assist
> secret and signature SigStrings. Lose it and that data is unrecoverable. If it
> is left unset, it falls back to a hash of `JWT_SECRET_KEY`, which ties the two
> together: rotating the JWT key would then break decryption. Always set it.

Secret names are `<client>-<KEY>`. In each create command below, replace `-` with the value; Windows `cmd` has no `echo -n`, so the command reads it from a file.

| Secret | Value |
|---|---|
| `<client>-DATABASE_URL` | **Unix-socket form:** `postgresql+psycopg2://<client_app>:<pw>@/<CLIENT_DB>?host=/cloudsql/reckon-dental:us-east1:recon-dental-db` |
| `<client>-JWT_SECRET_KEY` | generated above |
| `<client>-ENCRYPTION_KEY` | generated above |
| `<client>-RC_APP_CLIENT_SECRET`, `<client>-RC_USER_JWT`, `<client>-RC_WEBHOOK_SECRET` | if SMS is used |
| `<client>-SMTP_PASSWORD` / `<client>-GRAPH_CLIENT_SECRET` / `<client>-SENDGRID_API_KEY` | whichever e-mail sender they use |
| `<client>-STRIPE_SECRET_KEY`, `<client>-STRIPE_WEBHOOK_SECRET` | if AppointNow payments are used |
| `<client>-APPOINTNOW_TURNSTILE_SECRET` | if Turnstile is used |

The easiest way to create each one: write the value to a temporary file, then run
```bash
gcloud secrets create <client>-JWT_SECRET_KEY --project=reckon-dental --data-file=value.txt
```
Delete the file afterwards. Then let the client's service account read its secrets, and nobody else's:
```bash
gcloud secrets add-iam-policy-binding <client>-JWT_SECRET_KEY --project=reckon-dental --member=serviceAccount:SA --role=roles/secretmanager.secretAccessor
```
(Run this for each `<client>-*` secret.)

---

## 8. Non-secret config file

Create `deploy/clients/<client>.env.yaml`. Commit it: it holds no secrets.
```yaml
ENV: prod
REDIS_ENABLED: "true"
REDIS_HOST: 10.48.189.19
REDIS_PORT: "6379"
REDIS_DB: "<N>"                      # unique per client, see registry
GCS_BUCKET_DOCUMENTS: rd-<client>-documents
GCS_BUCKET_ORIGINALS: rd-<client>-imaging
GCS_BUCKET_DERIVED: rd-<client>-imaging
CORS_ORIGINS: https://<client>.reckondental.com
CORS_ORIGIN_REGEX: ""                # the default regex trusts every *.run.app / reckondental.com origin
PUBLIC_API_BASE_URL: https://<api url for this client>
PASSWORD_RESET_URL_BASE: https://<client>.reckondental.com/reset-password
APPOINTNOW_PAYMENT_RETURN_URL: https://<client>.reckondental.com/book/return
EMAIL_FROM: noreply@<client domain>
EMAIL_FROM_NAME: <Practice name>
# RC_APP_CLIENT_ID / RC_DEFAULT_FROM / SENDGRID_FROM_EMAIL / JIRA_PROJECT_KEY ... as applicable
```
- The two defaults to watch: the `CORS_ORIGIN_REGEX` default would let any other client's frontend call this API.
- `PASSWORD_RESET_URL_BASE` defaults to the shared frontend, so reset e-mails would link to the wrong site.

---

## 9. Cloud Run service

Use the **same image** the main service runs:
```bash
gcloud run services describe dentc-backend --region us-central1 --project reckon-dental --format="value(spec.template.spec.containers[0].image)"
```
Deploy the client service. Replace `IMAGE` with the output above.
```bash
gcloud run deploy dentc-backend-<client> --image IMAGE --region us-central1 --project reckon-dental --service-account SA --add-cloudsql-instances reckon-dental:us-east1:recon-dental-db --network default --subnet default --vpc-egress private-ranges-only --allow-unauthenticated --env-vars-file deploy/clients/<client>.env.yaml --set-secrets DATABASE_URL=<client>-DATABASE_URL:latest,JWT_SECRET_KEY=<client>-JWT_SECRET_KEY:latest,ENCRYPTION_KEY=<client>-ENCRYPTION_KEY:latest
```
- Add the other secrets to `--set-secrets` the same way.
- `--allow-unauthenticated` is required: the app does its own JWT auth, and the AppointNow and webhook routes are public by design.

**Optional custom domain:** map one with `gcloud beta run domain-mappings create`, or put the service behind the existing load balancer, then point DNS at it.

---

## 10. Frontend

Deploy the frontend for this client with its API base URL set to the new service URL, at the domain listed in `CORS_ORIGINS`. Either a separate frontend deployment per client, or one build with per-domain config. Whichever you use, the frontend domain and `CORS_ORIGINS` must match exactly.

---

## 11. Integrations (only the ones the client uses)

- **SMS (RingCentral):** set the client's own app credentials and `RC_DEFAULT_FROM`. Point the webhook / subscription URL at the **client service URL**.
- **E-mail:** the client's sender and domain (verify SPF/DKIM for `EMAIL_FROM`).
- **Stripe:** the client's own account. Create a webhook endpoint pointing at the client service's AppointNow webhook route, and store its signing secret.
- **AppointNow:** their public booking page resolves from `office_code`, which they set when creating offices in Setup.
- **Scheduled jobs:** create one Cloud Scheduler job per client per script, running against the client's own DB/config. Run these scripts per client only if they use the matching feature:
  - `scripts/run_sms_reminders.py`
  - `scripts/expire_booking_requests.py`
  - `scripts/auto_close_time_clock.py`
  - `scripts/purge_sms_messages.py`
- **Jira support tickets:** can be shared. Set `JIRA_PROJECT_KEY`, or a label per client, so you can tell tickets apart.

---

## 12. Verify, then hand over

- [ ] `GET <service url>/health` returns 200.
- [ ] `GET /health/redis` returns `"connected": true`.
- [ ] Log in as the client admin from the client's frontend domain (no CORS error).
- [ ] `GET /fee-schedules` returns 51 rows, `GET /procedure-codes` returns the full set, and `GET /definitions?group_code=payment_method` is populated.
- [ ] Upload a test document. It lands in `gs://rd-<client>-documents/documents/…` and opens through the app. Then delete it.
- [ ] A token from another deployment is **rejected** (401) by this service.

Then the **client admin configures in Setup**:
1. Account Info
2. Offices: hours, operatories, default fee schedule
3. Providers: specialty / taxonomy codes, office assignments
4. Users + groups / access rights
5. Insurance carriers + plans
6. Fee schedule assignments (Fee Schedule Wizard)
7. Letters assigned to offices
8. Integrations settings

> **Known gap:** `POST /auth/signup` is open and unauthenticated, so anyone who
> finds the client's API URL can create another tenant in their DB. Disable it in
> client deployments (needs a small `ALLOW_SIGNUP` setting; not built yet).

---

## 13. Client registry (keep it current)

Record every client here, or in an internal sheet. Each `REDIS_DB` index must be unique.

| Client | Database | DB user | REDIS_DB | Buckets | Cloud Run service | Service account | Frontend domain | Onboarded |
|---|---|---|---|---|---|---|---|---|
| (main) | recondental_migrated | dentc_dev_user | 0 | rd-phi-dicom-originals | dentc-backend | default | reckondental.com | — |

---

## 14. Every release, for every client (ongoing)

A separate DB per client means every release must reach every client:
1. **Migrate every client DB:** `alembic upgrade head` against each client's `DATABASE_URL`. A service running new code against an unmigrated DB will 500.
2. **Deploy the same image to every client service.**

`.github/workflows/deploy-cloud-run.yml` currently migrates and deploys **only** `dentc-backend` / `recondental_migrated`. Until it loops over the registry (a matrix job per client), run both steps by hand for each client after every deploy.

**Reference-data updates** (e.g. the yearly CDT code release) also go to every DB: run `scripts/seed_ada_codes.py` / `seed_procedure_code_rules.py` with each client's `DATABASE_URL`.

## 15. Offboarding (for completeness)

1. Export the client's data per contract.
2. Delete the Cloud Run service and scheduler jobs.
3. Delete the secrets, buckets (after the retention period), DB, DB user and service account.
4. Free the `REDIS_DB` index (flush it first).
5. Update the registry.
