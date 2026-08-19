#!/usr/bin/env bash
#
# Push local .env values to the Cloud Run service.
#
#   Secrets  -> Secret Manager, referenced by the service as env vars.
#   Config   -> plain env vars on the service.
#   Skipped  -> local-only values that would BREAK prod if copied (see SKIP below).
#
# Both gcloud calls use *merge* semantics (--update-env-vars / --update-secrets),
# never --set-*, so values already on the service (DATABASE_URL, JWT_SECRET_KEY
# from the console, the Redis keys the deploy workflow writes) are left alone.
#
# Usage:
#   gcloud auth login                       # must be a principal with run.admin
#   bash scripts/push_env_to_cloud_run.sh   # dry run — prints, changes nothing
#   DRY_RUN=0 bash scripts/push_env_to_cloud_run.sh
#
set -euo pipefail

PROJECT="${PROJECT:-reckon-dental}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-dentc-backend}"
ENV_FILE="${ENV_FILE:-.env}"
DRY_RUN="${DRY_RUN:-1}"

# Values that live in Secret Manager. The secret is named after the key.
SECRETS="SMTP_PASSWORD JIRA_API_TOKEN CLIENT_SECRET GRAPH_CLIENT_SECRET"

# Local-only values. Copying these to Cloud Run breaks the service:
#   DB_*/DATABASE_URL -> prod uses the Cloud SQL unix socket from Secret Manager,
#                        not the public IP in .env.
#   REDIS_*           -> the deploy workflow sets the Memorystore private IP.
#   GCS_CREDENTIALS_PATH -> a Windows key-file path; Cloud Run uses ADC from the
#                        runtime service account (object_storage.py falls back).
#   DATA_SOURCE_PATH / MIGRATION_* / DENTICON_* -> migration scripts, run locally.
#   JWT_SECRET_KEY    -> already live on the service as a plain env var, matching
#                        .env. The Secret Manager secret of the same name holds an
#                        OLDER value; repointing the service at it would rotate the
#                        signing key and invalidate every issued token. Leave it.
#                        To harden it into Secret Manager later, push a new version
#                        from the CURRENT live value first, then --update-secrets.
SKIP="JWT_SECRET_KEY
      DATABASE_URL DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD
      REDIS_ENABLED REDIS_HOST REDIS_PORT REDIS_DB
      GCS_CREDENTIALS_PATH DATA_SOURCE_PATH MIGRATION_MAX_ROWS
      DENTICON_PGID DENTICON_TENANT_NAME"

# Word-membership test. $2 is re-split on ALL whitespace first — SKIP spans several
# lines, so a plain " $2 " match would miss any word sitting at a line end.
in_list() {
  local needle="$1" word
  for word in $2; do [ "$word" = "$needle" ] && return 0; done
  return 1
}

[ -f "$ENV_FILE" ] || { echo "No $ENV_FILE here. Run from the repo root." >&2; exit 1; }

# Parse KEY=value. Ignores comments/blank lines, strips surrounding quotes and CR.
# A key repeated in .env keeps the LAST occurrence, matching dotenv semantics.
declare -A ENV_MAP
order=""
while IFS= read -r line || [ -n "$line" ]; do
  line="${line%$'\r'}"
  case "$line" in ''|'#'*) continue;; esac
  case "$line" in *=*) ;; *) continue;; esac
  key="${line%%=*}"
  val="${line#*=}"
  case "$key" in [A-Za-z_]*) ;; *) continue;; esac
  val="${val#\"}"; val="${val%\"}"; val="${val#\'}"; val="${val%\'}"
  [ -n "${ENV_MAP[$key]+x}" ] || order="$order $key"
  ENV_MAP["$key"]="$val"
done < "$ENV_FILE"

run() {
  if [ "$DRY_RUN" = "1" ]; then printf '  [dry-run] %s\n' "$*"; else "$@"; fi
}

echo "== Secrets -> Secret Manager (project $PROJECT) =="
secret_refs=""
for key in $SECRETS; do
  val="${ENV_MAP[$key]:-}"
  if [ -z "$val" ]; then echo "  ! $key not set in $ENV_FILE — skipping"; continue; fi
  if gcloud secrets describe "$key" --project="$PROJECT" >/dev/null 2>&1; then
    echo "  ~ $key exists, adding a new version"
    if [ "$DRY_RUN" = "1" ]; then
      echo "  [dry-run] gcloud secrets versions add $key --data-file=-"
    else
      printf '%s' "$val" | gcloud secrets versions add "$key" \
        --project="$PROJECT" --data-file=-
    fi
  else
    echo "  + $key creating"
    if [ "$DRY_RUN" = "1" ]; then
      echo "  [dry-run] gcloud secrets create $key --data-file=-"
    else
      printf '%s' "$val" | gcloud secrets create "$key" \
        --project="$PROJECT" --replication-policy=automatic --data-file=-
    fi
  fi
  secret_refs="${secret_refs:+$secret_refs,}$key=$key:latest"
done

echo
echo "== Grant the runtime service account read access =="
# Secret refs resolve as the *runtime* SA, not the deployer. Without this binding
# the revision fails to start with a secret-access error.
RUNTIME_SA="${RUNTIME_SA:-$(gcloud run services describe "$SERVICE" --region="$REGION" \
  --project="$PROJECT" --quiet --format='value(spec.template.spec.serviceAccountName)' 2>/dev/null || true)}"
if [ -z "$RUNTIME_SA" ]; then
  # Can't read the service (wrong identity, or it uses the Cloud Run default SA,
  # which describe reports as empty). Not fatal — keep going so the rest of the
  # plan still prints; pass RUNTIME_SA=... to grant explicitly.
  echo "  ! could not resolve the runtime service account — skipping IAM bindings."
  echo "    Re-run with RUNTIME_SA=<sa-email> once you know it, or grant in the console."
else
  echo "  runtime SA: $RUNTIME_SA"
  for key in $SECRETS; do
    [ -n "${ENV_MAP[$key]:-}" ] || continue
    run gcloud secrets add-iam-policy-binding "$key" --project="$PROJECT" --quiet \
      --member="serviceAccount:$RUNTIME_SA" --role=roles/secretmanager.secretAccessor
  done
fi

echo
echo "== Plain config -> env vars =="
# ^|^ is gcloud's escaped-list delimiter. Needed because values contain commas
# (JIRA_ISSUE_TYPE_MAP is JSON) and the default separator is a comma. No value
# may itself contain "|" — asserted below.
pairs=""
for key in $order; do
  in_list "$key" "$SKIP"    && { echo "  - $key (local only)";  continue; }
  in_list "$key" "$SECRETS" && continue
  val="${ENV_MAP[$key]}"
  case "$val" in *"|"*) echo "  ! $key contains '|', clashes with the delimiter" >&2; exit 1;; esac
  echo "  + $key"
  pairs="${pairs:+$pairs|}$key=$val"
done

echo
echo "== Applying to $SERVICE ($REGION) =="
run gcloud run services update "$SERVICE" \
  --region="$REGION" --project="$PROJECT" \
  ${secret_refs:+--update-secrets="$secret_refs"} \
  --update-env-vars="^|^$pairs"

if [ "$DRY_RUN" = "1" ]; then
  echo
  echo "Dry run only. Re-run with DRY_RUN=0 to apply."
fi
