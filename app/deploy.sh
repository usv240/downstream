#!/usr/bin/env bash
set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT}"
REGION="${GOOGLE_CLOUD_REGION:-us-central1}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-sa-reason@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com}"
BETA_API_SECRET="${BETA_API_SECRET:-}"
BETA_ENROLLMENT_SECRET="${BETA_ENROLLMENT_SECRET:-}"
# Secret Manager names for the scheduler trigger and the quota fingerprint pepper.
SCHEDULER_TOKEN_SECRET="${SCHEDULER_TOKEN_SECRET:-}"
QUOTA_PEPPER_SECRET="${QUOTA_PEPPER_SECRET:-}"
# Live Gemini inference in the request path. ON by default: Gemini 3.5 is mandatory for this
# submission, so a deployment must not be able to ship without it by omission. Spend is
# bounded by QUOTA_LIVE_MODEL_CALLS_PER_DAY, and every call past the cap or after a Vertex
# error falls back to the graded recording rather than failing.
LIVE_MODEL="${DOWNSTREAM_LIVE_MODEL:-true}"
# Key issuance. "open" lets a judge self-serve; "invite_only" requires BETA_ENROLLMENT_SECRET.
ISSUANCE_MODE="${DEVELOPER_ISSUANCE_MODE:-open}"

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
if [[ -n "${SCHEDULER_TOKEN_SECRET}" ]]; then
  BETA_SECRET_MAPPINGS+=("INTERNAL_SCHEDULER_TOKEN=${SCHEDULER_TOKEN_SECRET}:latest")
fi
if [[ -n "${QUOTA_PEPPER_SECRET}" ]]; then
  BETA_SECRET_MAPPINGS+=("QUOTA_FINGERPRINT_PEPPER=${QUOTA_PEPPER_SECRET}:latest")
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
  --update-env-vars "GOOGLE_CLOUD_PROJECT=${GOOGLE_CLOUD_PROJECT},USE_FIRESTORE=true,BETA_DEVELOPER_KEY_TTL_HOURS=168,DOWNSTREAM_LIVE_MODEL=${LIVE_MODEL},TRUSTED_PROXY_HOPS=1,DEVELOPER_ISSUANCE_MODE=${ISSUANCE_MODE}" \
  "${BETA_SECRET_ARGS[@]}" \
  --quiet

cat <<'NOTE'

Deployed. Two follow-ups if this is a fresh project.

1. Scheduled execution. The durable wake ladder only fires when something calls it. Create the
   cron once, pointing at /internal/scan-due and carrying the shared token:

     gcloud scheduler jobs create http downstream-scan-due
       --schedule "*/15 * * * *"
       --uri "<service-url>/internal/scan-due"
       --http-method POST
       --headers "X-Scheduler-Token=<value of the downstream-scheduler-token secret>"
       --location us-central1

   Without INTERNAL_SCHEDULER_TOKEN set, that route returns 503 rather than running open.

2. Live inference is ON. Gemini 3.5 Flash is called in the request path, capped by
   QUOTA_LIVE_MODEL_CALLS_PER_DAY (25 by default), falling back to the graded recording past
   the cap or on any Vertex error. Check /health: it must report live_with_replay_fallback.
NOTE
