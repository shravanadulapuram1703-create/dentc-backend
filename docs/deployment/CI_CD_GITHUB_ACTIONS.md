# CI/CD Runbook — Auto-deploy to Cloud Run via GitHub Actions

> Audience: DentC engineering team.
> What it does: when a PR is **merged into `dev`** (i.e. a push lands on `dev`), GitHub Actions
> builds the Docker image, pushes it to Artifact Registry, and rolls out a new Cloud Run revision —
> automatically, no manual `gcloud` needed.
> Auth is **keyless** via Workload Identity Federation (no service-account JSON key in GitHub).

This applies to **both** repos (`dentc-backend` and `dentc-frontend`). The workflow files are:
- `dentc-backend/.github/workflows/deploy-cloud-run.yml`
- `dentc-frontend/.github/workflows/deploy-cloud-run.yml`

---

## How triggering works

| You do | Result |
|---|---|
| Open a PR targeting `dev` | ❌ Does **not** deploy (deploy is on push, not PR open) |
| Merge the PR into `dev` | ✅ Push to `dev` → workflow runs → new Cloud Run revision live |
| Push a commit directly to `dev` | ✅ Same as above |

> Want CI checks (lint/tests) to run on the PR *before* merge? Add a second workflow with
> `on: pull_request` — see the optional section at the end.

---

## ⚠️ Prerequisite: the service must already exist

The deploy step updates **only the image**. All other config — env vars, secrets, the Cloud SQL
connection, CORS, scaling — is **retained from the previous revision**. So the **first** deploy of
each service must be the full manual one from the runbooks
(`BACKEND_DEPLOY_GCP.md` / `FRONTEND_DEPLOY_GCP.md`), which sets `--set-secrets`,
`--add-cloudsql-instances`, `--set-env-vars`, etc. After that, GitHub Actions takes over.

---

## One-time GCP setup (do this once for the whole project)

Run these in **Cloud Shell** or any shell with `gcloud` + owner access. (Bash shown; on Windows use
Git Bash or Cloud Shell — the `for` loops are bash.)

```bash
PROJECT_ID=reckon-dental
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')

# Your GitHub owner (org or username) and the two repo names:
GH_OWNER=<your-github-org-or-username>
BACKEND_REPO=dentc-backend
FRONTEND_REPO=dentc-frontend

# 0. Enable the APIs WIF needs
gcloud services enable iamcredentials.googleapis.com sts.googleapis.com

# 1. Create the deployer service account
gcloud iam service-accounts create github-deployer \
  --display-name="GitHub Actions deployer"
SA="github-deployer@${PROJECT_ID}.iam.gserviceaccount.com"

# 2. Grant it what it needs to build, push and deploy
for ROLE in roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA}" --role="$ROLE"
done

# 3. Create the Workload Identity pool + GitHub OIDC provider
gcloud iam workload-identity-pools create github-pool \
  --location=global --display-name="GitHub Actions pool"

gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location=global \
  --workload-identity-pool=github-pool \
  --display-name="GitHub provider" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
  --attribute-condition="assertion.repository_owner=='${GH_OWNER}'"

# 4. Let each repo impersonate the deployer SA (scoped to that exact repo)
POOL="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool"
for REPO in "$BACKEND_REPO" "$FRONTEND_REPO"; do
  gcloud iam service-accounts add-iam-policy-binding "$SA" \
    --role=roles/iam.workloadIdentityUser \
    --member="principalSet://iam.googleapis.com/${POOL}/attribute.repository/${GH_OWNER}/${REPO}"
done

# 5. Print the two values you'll paste into GitHub secrets
echo "WIF_PROVIDER        = ${POOL}/providers/github-provider"
echo "WIF_SERVICE_ACCOUNT = ${SA}"
```

The `attribute-condition` locks this down so **only repos under your GitHub owner** can use it, and
step 4 further scopes impersonation to exactly these two repos.

---

## Add the two GitHub secrets (in EACH repo)

For **both** `dentc-backend` and `dentc-frontend` on GitHub:

**Settings → Secrets and variables → Actions → New repository secret**, add:

| Secret name | Value (from step 5 above) |
|---|---|
| `WIF_PROVIDER` | `projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/github-pool/providers/github-provider` |
| `WIF_SERVICE_ACCOUNT` | `github-deployer@reckon-dental.iam.gserviceaccount.com` |

(Same two values in both repos.)

---

## Try it

1. Make sure the first manual deploy of the service is done (so it has its secrets/env/Cloud SQL).
2. Commit the workflow file + push it to `dev` (or merge a PR into `dev`).
3. Watch **GitHub → Actions tab** → the "Deploy … to Cloud Run" run.
4. On green, verify the live URL (`/health`). Each run tags the image with the commit SHA, so you
   get a clean history.

---

## Rollback

Every deploy is a new Cloud Run revision tagged with the commit SHA. To roll back instantly without
rebuilding:
```bash
gcloud run revisions list --service dentc-backend --region us-central1
gcloud run services update-traffic dentc-backend --region us-central1 --to-revisions <REVISION>=100
```

---

## Optional — run lint/tests on the PR before merge

Add `.github/workflows/ci.yml` in each repo:
```yaml
name: CI
on:
  pull_request:
    branches: [dev]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      # backend example:
      # - uses: actions/setup-python@v5
      #   with: { python-version: '3.12' }
      # - run: pip install -r requirements.txt && pytest
      # frontend example:
      # - uses: actions/setup-node@v4
      #   with: { node-version: '20' }
      # - run: npm ci && npm run lint && npm run build
```
This runs on the PR (no deploy). Combined with a branch-protection rule on `dev` that "requires
status checks to pass", a PR can't merge — and therefore can't deploy — until CI is green.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Permission 'iam.serviceAccounts.getAccessToken' denied` | Step 4 binding missing or `GH_OWNER`/repo name typo. |
| `failed to get token: ... attribute condition` | Push came from a repo outside `GH_OWNER`; check the provider condition. |
| Deploy succeeds but app misconfigured | The service lost its env/secrets — it was never given them via a full first deploy. Re-run the manual deploy once. |
| `denied: Permission artifactregistry.repositories.uploadArtifacts` | Deployer SA missing `roles/artifactregistry.writer`, or repo `dentc` doesn't exist. |
| Frontend points at wrong backend | `API_BASE_URL` in the frontend workflow `env:` is baked at build — update it and re-push. |
