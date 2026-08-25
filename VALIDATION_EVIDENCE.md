# Validation evidence

Every number below was produced by running the command named beside it. Where a capability is
partly off in the deployed configuration, that is stated rather than rounded up.

## Measured on August 23, 2026

| Check | Command | Result |
|---|---|---|
| Test suite | `python -m pytest -q` | 345 passed |
| Lint | `python -m ruff check .` | clean |
| Accessibility, both themes | `python scripts/check_a11y.py` | all checks passed |
| Executable judge flow | `python scripts/downstream_demo_flow.py --url <base>` | 63/63 |
| Executable safety proof | `GET /downstream/proof` | 18/18 |
| Gemini drawing recording | `python -m scripts.record_drawing` | 5/5 against adjacent truth |
| Gemma name-span recording | `python -m scripts.record_gemma` | 4/4 recall, 0 false positives, 0 leaked |

## Autonomy, measured from the stored run timeline

One request to `POST /downstream/demo/run`:

| Measure | Value |
|---|---|
| Automatic agent steps | 15 |
| Owner authority steps | 7 |
| External trigger events | 1 |
| Continue clicks required | 0 |
| Durable wakes registered | 2 |
| Scheduled actions actually fired | 2 (`reopen_held_questions`, `unanswered_question_nudge`) |
| System decisions over reserved authority | 0 |

The rehearsal moves a simulated clock forward so a wake that is genuinely due in three days can
fire inside one request. The wake row, the compare-and-swap claim, the handler and the completion
are the production ones; the response says the clock was simulated and that the owner answers were
synthetic.

## Context, measured rather than asserted

The context meter previously computed `410 + min(260, …)` against a bound of 670, so
`within_bound` could not be false. It now measures the assembled turn payload:

| State | Structured context | Naive transcript replay |
|---|---|---|
| Empty workspace | 361 tokens | 945 tokens |
| Six answers recorded | 496 tokens | 1,112 tokens |
| Twelve further empty sessions | 496 tokens | 1,415 tokens |

Budget is 900 tokens. `/downstream/proof` includes a check that deliberately overloads one answer
and asserts the meter reports the breach, so the measurement is capable of failing.

## What is and is not running in the deployed configuration

- **Live Gemini inference is ON.** Opening a workspace makes a real Vertex AI Gemini 3.5 Flash
  multimodal call; the facts it returns carry `live_gemini_3_5_flash` provenance and `/health`
  reports `live_with_replay_fallback`. It is capped at 25 calls per day and falls back to the
  graded recording past the cap or on any Vertex error, so a model outage degrades the evidence
  rather than the product. The switch is `DOWNSTREAM_LIVE_MODEL`, which defaults to off so a
  fresh deployment cannot start spending before someone chooses to.
- **Gemma 4** is a graded recording in every configuration. `/stack` never reports it as live.
- **Cloud Trace** is exporting; `/health` reports `cloud_trace`. Without the exporter it degrades
  to no tracing and reports `inactive` rather than claiming otherwise.

`/stack` is derived from the running process, so the badge on every page cannot claim a service
the deployment does not have.

## Deployment

- Public standalone repository: https://github.com/usv240/downstream
- Cloud Run service: https://downstream-109051079423.us-central1.run.app
- Firestore holds workspaces, wakes, API key digests, and quota counters.
- `/internal/scan-due` is the Cloud Scheduler trigger. Without `INTERNAL_SCHEDULER_TOKEN` it
  returns 503 rather than running unauthenticated, and it is excluded from the public schema.

## Behavioural notes worth checking by hand

- Unknown-term feedback re-asks the same unresolved question in plain language with a gloss. It
  does not fabricate an answer or advance the workflow.
- The 28-versus-31-foot conflict is derived by comparing the drawing read against the registry
  row. A drawing that agrees with the registry produces no sixth question.
- An owner answer containing a phone number or an email address is stored verbatim in the
  workspace and pseudonymised before it reaches any model boundary.
- The guided workspace, shareable resume URL, held-question recovery, judge page, evidence
  dashboard, and autonomy receipt are public and return HTTP 200.
