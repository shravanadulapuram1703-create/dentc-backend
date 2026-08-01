#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# One-time GCP setup for the DICOM migration. Run this ONCE (by the project
# admin, not the colleague) with an account that has project-admin rights.
# It creates the originals bucket + a least-privilege "ingest" service account,
# then prints a key file to hand to whoever runs the upload.
#
#   bash setup_gcp.sh
#
# Re-runnable: existing resources are left alone.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-reckon-dental}"
ORIGINALS_BUCKET="${ORIGINALS_BUCKET:-rd-phi-dicom-originals}"
OPS_BUCKET="${OPS_BUCKET:-rd-ops-migration}"
# nam4 = dual-region us-central1 + us-east1 (geo-redundant, per the plan)
ORIGINALS_LOCATION="${ORIGINALS_LOCATION:-nam4}"
OPS_LOCATION="${OPS_LOCATION:-us-central1}"
INGEST_SA="sa-dicom-ingest"
INGEST_SA_EMAIL="${INGEST_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
KEY_FILE="${KEY_FILE:-sa-dicom-ingest.json}"

echo "Project        : ${PROJECT_ID}"
echo "Originals bucket: gs://${ORIGINALS_BUCKET} (${ORIGINALS_LOCATION})"
echo "Ops bucket     : gs://${OPS_BUCKET} (${OPS_LOCATION})"
echo

gcloud config set project "${PROJECT_ID}"

echo "==> Creating buckets (uniform access, versioning, public access blocked)…"
create_bucket () {
  local name="$1" loc="$2" versioning="$3"
  if gcloud storage buckets describe "gs://${name}" >/dev/null 2>&1; then
    echo "    gs://${name} already exists — skipping."
  else
    gcloud storage buckets create "gs://${name}" \
      --location="${loc}" \
      --uniform-bucket-level-access \
      --public-access-prevention
    echo "    created gs://${name}"
  fi
  if [ "${versioning}" = "on" ]; then
    gcloud storage buckets update "gs://${name}" --versioning
  fi
}
create_bucket "${ORIGINALS_BUCKET}" "${ORIGINALS_LOCATION}" "on"
create_bucket "${OPS_BUCKET}" "${OPS_LOCATION}" "off"

echo "==> Lifecycle: originals Standard -> Nearline @30d…"
cat > /tmp/lifecycle-originals.json <<'JSON'
{ "rule": [
  { "action": {"type": "SetStorageClass", "storageClass": "NEARLINE"},
    "condition": {"age": 30} }
] }
JSON
gcloud storage buckets update "gs://${ORIGINALS_BUCKET}" \
  --lifecycle-file=/tmp/lifecycle-originals.json

echo "==> Ops bucket: delete objects after 180d…"
cat > /tmp/lifecycle-ops.json <<'JSON'
{ "rule": [ { "action": {"type": "Delete"}, "condition": {"age": 180} } ] }
JSON
gcloud storage buckets update "gs://${OPS_BUCKET}" \
  --lifecycle-file=/tmp/lifecycle-ops.json

echo "==> Creating ingest service account (create-only, no read/delete)…"
if ! gcloud iam service-accounts describe "${INGEST_SA_EMAIL}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${INGEST_SA}" \
    --display-name="DICOM migration ingest (upload only)"
fi

echo "==> Granting objectCreator on originals + ops…"
for B in "${ORIGINALS_BUCKET}" "${OPS_BUCKET}"; do
  gcloud storage buckets add-iam-policy-binding "gs://${B}" \
    --member="serviceAccount:${INGEST_SA_EMAIL}" \
    --role="roles/storage.objectCreator"
done

echo "==> Creating a key file for the uploader: ${KEY_FILE}"
if [ -f "${KEY_FILE}" ]; then
  echo "    ${KEY_FILE} already exists — NOT overwriting."
else
  gcloud iam service-accounts keys create "${KEY_FILE}" \
    --iam-account="${INGEST_SA_EMAIL}"
  echo "    wrote ${KEY_FILE}"
fi

echo
echo "DONE. Hand ${KEY_FILE} to whoever runs the upload and set in their .env:"
echo "    GOOGLE_APPLICATION_CREDENTIALS=./${KEY_FILE}"
echo "    GCS_BUCKET_ORIGINALS=${ORIGINALS_BUCKET}"
echo
echo "NOTE: This account can CREATE objects but cannot read or delete them —"
echo "      the least-privilege ingest role from the migration plan."
