# Downstream integration beta

The `/v1` API is the usable, key-protected counterpart to the public synthetic judge preset.

## Provision a key

```bash
cd app
python scripts/create_beta_key.py --tenant owner_one --label "Owner one"
```

Give the plaintext key to the intended caller. Save the hash-only JSON temporarily under the
ignored `.beta-keys/` directory as `keys.json`.

```bash
gcloud secrets create downstream-beta-api-keys --data-file=.beta-keys/keys.json
gcloud secrets add-iam-policy-binding downstream-beta-api-keys \
  --member=serviceAccount:sa-reason@agentic-fleet-2026.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor
BETA_API_SECRET=downstream-beta-api-keys bash deploy.sh
```

For an existing secret, add a new version containing the complete set of active hashes. Remove a
digest and deploy a new revision to revoke a key.

## Contract

- Header: `X-API-Key`
- Scope: `downstream:use`
- Input: a literal USACE NID identifier, followed by owner-provided answers
- Source control: dam attributes are fetched from the live public NID service, not request JSON
- Storage: tenant-owned Firestore workspace with answers, revisions, profile, and evidence ledger
- Safety: draft only; no inundation extent, certification, condition assessment, contact, or submit

The tenant is derived from the API key. Guessing a workspace identifier owned by another key returns
404. The deployment script caps Cloud Run at three instances. Use API Gateway quotas for a broader
external rollout.
