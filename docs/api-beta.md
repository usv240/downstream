# Downstream integration beta

The public judge workflow remains credential-free. The `/v1` API is a separate, key-protected
integration surface with server-derived tenant isolation.

## Get a temporary key from the website

1. Ask the project owner for a private invitation code.
2. Open [https://downstream-109051079423.us-central1.run.app/developer](https://downstream-109051079423.us-central1.run.app/developer).
3. Choose a lowercase workspace ID and a human-readable label.
4. Accept the project-specific safety contract.
5. Generate the key, save it immediately, and run the built-in connection test.
6. Open [the interactive API reference](https://downstream-109051079423.us-central1.run.app/docs) for schemas and operations.

Temporary keys expire after 168 hours. The plaintext value is returned once and remains only in
page memory. Firestore stores its SHA-256 digest, project, tenant, scope, issuance time, expiry, and
optional revocation time. The holder can revoke the key immediately with `DELETE /v1/key`.

This is invite-gated self-service, not anonymous public issuance. The invitation code protects the
project's model and infrastructure budget. Rotate it immediately if it is exposed.

## Configure website issuance

Generate a separate invitation code for this project:

```bash
cd app
python scripts/create_enrollment_code.py
```

Save the printed hash, never the plaintext invitation code, in an ignored local file such as
`.beta-keys/enrollment-hash.txt`. Create a regional Secret Manager secret and grant only the
Cloud Run service account access:

```bash
gcloud secrets create downstream-beta-enrollment \
  --replication-policy=user-managed \
  --locations=us-central1 \
  --data-file=.beta-keys/enrollment-hash.txt
gcloud secrets add-iam-policy-binding downstream-beta-enrollment \
  --member=serviceAccount:sa-reason@agentic-fleet-2026.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor
BETA_API_SECRET=downstream-beta-api-keys \
BETA_ENROLLMENT_SECRET=downstream-beta-enrollment \
bash deploy.sh
```

The deployment mounts the hash as `BETA_ENROLLMENT_CODE_HASH` and pins
`BETA_DEVELOPER_KEY_TTL_HOURS=168`. Neither plaintext API keys nor plaintext invitation codes
belong in Cloud Run configuration, source control, screenshots, or logs.

## Provision an operator-managed key

For a longer controlled beta, generate a key directly:

```bash
cd app
python scripts/create_beta_key.py --tenant owner_one --label "Owner one"
```

Store the printed hash-only JSON in the `downstream-beta-api-keys` Secret Manager secret. Give the
plaintext key only to its intended caller. For an existing secret, add a new version containing all
active digests. Revoke one of these operator-managed keys by removing its digest, adding a secret
version, and deploying a revision.



## API contract

- Header: `X-API-Key`
- Scope: `downstream:use`
- Input: an exact USACE National Inventory of Dams identifier
- Storage: a tenant-private collaboration workspace and its revision history
- Isolation: a workspace owned by another key returns 404 even when its identifier is known
- Safety: screening and drafting only; no inundation extent, certification, condition assessment, failure prediction, contact, or submission

The API starts from authoritative public inventory data rather than caller-supplied dam facts.
Every claim remains within the product's screening-level boundary.

## Security and rollout boundary

- Missing, invalid, expired, and revoked keys fail closed.
- A Firestore outage returns 503 rather than bypassing authentication.
- Invitation codes and API keys are compared through SHA-256 digests.
- API keys are never accepted from query strings.
- The browser does not place credentials in cookies, local storage, or session storage.
- Cloud Run is capped at three instances to bound infrastructure cost.
- Permanent and temporary keys use the same authorization and tenant boundary.

Before a broad external program, place API Gateway in front of `/v1` for per-consumer quotas,
rate limits, abuse controls, and formal onboarding. The invitation boundary and Cloud Run cap make
this suitable for an invited hackathon beta, not an unrestricted public service.
