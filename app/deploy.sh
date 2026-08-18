#!/usr/bin/env bash
set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
REGION="${GOOGLE_CLOUD_REGION:-us-central1}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-sa-reason@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com}"
BETA_API_SECRET="${BETA_API_SECRET:-}"
BETA_SECRET_ARGS=()
if [[ -n "${BETA_API_SECRET}" ]]; then
  BETA_SECRET_ARGS=(--set-secrets "BETA_API_KEY_HASHES=${BETA_API_SECRET}:latest")
fi

gcloud run deploy downstream \
  --source . \
  --project "$GOOGLE_CLOUD_PROJECT" \
  --region "$REGION" \
  --service-account "$SERVICE_ACCOUNT" \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 3 \
  --concurrency 20 \
  --update-env-vars "GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT,USE_FIRESTORE=true" \
  "${BETA_SECRET_ARGS[@]}" \
  --quiet
