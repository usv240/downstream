# Downstream integration beta

The public judge workflow remains credential-free. The `/v1` API is a separate, key-protected
integration surface with server-derived tenant isolation.

## Get a key from the website

No invitation, no account, no payment details.

1. Open [https://downstream-109051079423.us-central1.run.app/developer](https://downstream-109051079423.us-central1.run.app/developer).
2. Give the key a label. Email, organisation, and what you are building are optional and are
   recorded as contact metadata only; none of it affects what the key can do.
3. Accept the project-specific safety contract.
4. Generate the key and save it immediately: the plaintext value is returned once.
5. Use the console on the same page to run any endpoint, or **Run the whole sequence** to execute
   all eight calls in order.

You do not choose a tenant. The server mints one per key.

Temporary keys expire after 168 hours. The plaintext value is returned once and remains only in
page memory. Firestore stores its SHA-256 digest, project, tenant, scope, issuance time, expiry, and
optional revocation time. The holder can revoke the key immediately with `DELETE /v1/key`.

This is invite-gated self-service, not anonymous public issuance. The invitation code protects the
project's model and infrastructure budget. Rotate it immediately if it is exposed.

### Tenant isolation

The tenant a key speaks for is **minted by the server**, never supplied by the caller. An earlier
version accepted `tenant_id` in the request body, which meant one holder of a shared invitation
code could mint a key naming another holder's tenant and then read their workspaces. Two
developers redeeming the same code now land in separate tenants, and a workspace ID belonging to
one is a 404 for the other even if it is guessed correctly. Any `tenant_id` sent in the body is
ignored.

### Limits

| Ceiling | Default | Keyed to |
|---|---|---|
| Authenticated `/v1` calls | **1,000** per UTC day | your API key |
| Key creations | **50** per UTC day | caller network |
| Public demo workspaces | **500** per UTC day | caller network |

Sized so that evaluating the API thoroughly never hits a wall. Every authenticated response
carries the three rate-limit headers, so the remaining budget is always visible.

A refusal is `429` and carries `X-RateLimit-Limit`, `X-RateLimit-Remaining` and
`X-RateLimit-Reset`. Counters are Firestore transactions, so the limit holds across Cloud Run
instances. The stored bucket key is an HMAC of the caller address under a server-held pepper; no
raw IP is written. `GET /v1` echoes the current published limits.

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


## Autonomy receipt

`GET /v1/workspaces/{id}/autonomy` returns what the agent did on its own, counted from the stored
run timeline rather than described:

```json
{
  "trigger": "approved_api_client_supplied_an_nid_identifier",
  "automatic_agent_steps": 6,
  "human_authority_steps": 0,
  "external_evidence_steps": 2,
  "continue_clicks_required": 0,
  "durable_wakes_registered": 2,
  "waiting_on": "owner knowledge for access_heavy_rain, ...",
  "authority_reserved": ["owner site knowledge", "..."],
  "system_decisions_over_reserved_authority": 0,
  "timeline": [{"at": "...", "actor": "agent", "step": "facts_grounded", "detail": "..."}]
}
```

`actor` is one of `agent`, `human_authority`, or `external_evidence`. The claim this supports is
narrow and checkable: every in-scope transition runs automatically, and the run pauses only for
owner knowledge or for evidence that has to come from outside.

## What the API will not do

It produces a reviewable draft. It does not create an inundation extent, certify a plan, make a
condition assessment, predict failure, contact an agency, or submit anything. There is no endpoint
whose path contains approve, certify, or submit, and `/downstream/proof` asserts that.
