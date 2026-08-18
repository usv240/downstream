#!/usr/bin/env bash
set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
REGION="${GOOGLE_CLOUD_REGION:-us-central1}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-sa-reason@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com}"
BETA_API_SECRET="${BETA_API_SECRET:-}"
BETA_ENROLLMENT_SECRET="${BETA_ENROLLMENT_SECRET:-}"

GCLOUD_BIN="${GCLOUD_BIN:-gcloud}"
GCLOUD_VIA_WINDOWS_POWERSHELL=false
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GCLOUD_WINDOWS_WRAPPER=""
if grep -qi microsoft /proc/version 2>/dev/null && command -v powershell.exe >/dev/null 2>&1; then
  GCLOUD_VIA_WINDOWS_POWERSHELL=true
  GCLOUD_WINDOWS_WRAPPER="$(wslpath -w "${SCRIPT_DIR}/infra/gcloud-wrapper.ps1")"
fi

run_gcloud() {
  if [[ "${GCLOUD_VIA_WINDOWS_POWERSHELL}" == "true" ]]; then
    powershell.exe -NoProfile -NonInteractive -File "${GCLOUD_WINDOWS_WRAPPER}" "$@"
  else
    "${GCLOUD_BIN}" "$@"
  fi
}

BETA_SECRET_MAPPINGS=()
if [[ -n "${BETA_API_SECRET}" ]]; then
  BETA_SECRET_MAPPINGS+=("BETA_API_KEY_HASHES=${BETA_API_SECRET}:latest")
fi
if [[ -n "${BETA_ENROLLMENT_SECRET}" ]]; then
  BETA_SECRET_MAPPINGS+=("BETA_ENROLLMENT_CODE_HASH=${BETA_ENROLLMENT_SECRET}:latest")
fi
BETA_SECRET_ARGS=()
if (( ${#BETA_SECRET_MAPPINGS[@]} )); then
  BETA_SECRET_VALUE="$(IFS=,; echo "${BETA_SECRET_MAPPINGS[*]}")"
  BETA_SECRET_ARGS=(--set-secrets "${BETA_SECRET_VALUE}")
fi

if [[ "${REGION}" != "us-central1" ]]; then
  echo "REGION is ${REGION}; this build is pinned to us-central1." >&2
  exit 1
fi

run_gcloud run deploy downstream \
  --source . \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --region "${REGION}" \
  --service-account "${SERVICE_ACCOUNT}" \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 3 \
  --concurrency 20 \
  --update-env-vars "GOOGLE_CLOUD_PROJECT=${GOOGLE_CLOUD_PROJECT},USE_FIRESTORE=true,BETA_DEVELOPER_KEY_TTL_HOURS=168" \
  "${BETA_SECRET_ARGS[@]}" \
  --quiet
