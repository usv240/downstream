# Submission links

Everything a judge needs, in one place.

| What | Where |
|---|---|
| Live app | https://downstream-109051079423.us-central1.run.app |
| One-request demonstration | `POST /downstream/demo/run`, or the button on the home page |
| Judge evidence page | https://downstream-109051079423.us-central1.run.app/judges |
| Evidence dashboard | https://downstream-109051079423.us-central1.run.app/evidence |
| Executable safety proof | https://downstream-109051079423.us-central1.run.app/downstream/proof |
| What this deployment is running | https://downstream-109051079423.us-central1.run.app/stack |
| Developer API and console | https://downstream-109051079423.us-central1.run.app/developer |
| Interactive OpenAPI schema | https://downstream-109051079423.us-central1.run.app/docs |
| Repository | https://github.com/usv240/downstream |
| Architecture diagram | [docs/architecture.png](docs/architecture.png) |
| Public build story | https://dev.to/ujwal240/the-registry-said-28-feet-the-drawing-said-31-4dma |
| Demo video | *to be added before submission* |

## Category

**The Collaborative Partner.** The agent resolves what it can on its own, asks the owner only what
it is not permitted to invent, learns from corrections, and keeps working between sessions.

## Mandatory technology

| Requirement | How it is met | Check it |
|---|---|---|
| Gemini 3.5 or newer via Gemini API or Vertex AI | Live Vertex AI call on workspace open | `/health` reports `live_with_replay_fallback` |
| A Google agent framework | Google Gen AI SDK (`google-genai`) | `app/downstream/live_model.py` |
| A Google Cloud infrastructure service | Cloud Run, Firestore, Cloud Scheduler, Secret Manager, Cloud Trace | `/stack` |

## Verify without installing anything

```bash
curl -X POST -H "Content-Type: application/json" -d '{}'   https://downstream-109051079423.us-central1.run.app/downstream/demo/run
```
