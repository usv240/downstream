# Downstream submission kit

## Devpost fields

**Category:** The Collaborative Partner

**One sentence:** Downstream is a multi-session partner that combines public dam records,
source-grounded drawing facts, and owner knowledge into a reviewable Emergency Action Plan draft,
while refusing to invent an inundation boundary.

**Value:** It removes the coordination burden of resolving scattered facts, remembering prior
answers, adapting language, tracking incomplete sections, and assembling a traceable first draft.
One trigger produces fifteen automatic agent steps and zero continue clicks; the agent pauses only
for owner knowledge, which is the one input it must not invent.

**Technology:** Gemini 3.5 Flash through Vertex AI and the Google Gen AI SDK, Gemma 4 MaaS
(recorded), Cloud Run, Firestore, Cloud Scheduler, Secret Manager, OpenTelemetry to Cloud Trace,
the USACE NID public FeatureServer, FastAPI, accessible HTML, SVG, and Python.

**Findings and learnings:** three worth stating. Deriving the source conflict instead of encoding
it in a fixture is what turned a scripted demo into an agent — a drawing that agrees with the
registry now correctly raises no question. A context meter whose arithmetic cannot exceed its own
bound proves nothing, so it was rewritten to measure the assembled payload and a check was added
that it can report a breach. And a capability that only tests import is worse than an absent one,
because the documentation describes it as real; a test now fails if any module is reachable only
from its own tests.

**Public build story:** [The Registry Said 28 Feet. The Drawing Said 31.](https://dev.to/ujwal240/the-registry-said-28-feet-the-drawing-said-31-4dma)

## Four-minute shot list

| Time | Screen | Narration goal |
|---|---|---|
| 0:00 to 0:20 | Landing page | State the owner problem, measured NID scale, and the draft boundary |
| 0:20 to 0:55 | **Run the whole thing in one request** | Press it once. Narrate the receipt as it lands: 15 automatic steps, 0 continue clicks, 2 scheduled actions fired. Say out loud that the owner answers are synthetic and the rehearsal clock was simulated |
| 0:55 to 1:20 | Autonomy timeline | Scroll the ordered timeline; point out the three actor colours and that the counts are read from stored state |
| 1:20 to 1:45 | Live NID query | Real federal data; null means unreported, not "no plan" |
| 1:45 to 2:10 | Drawing and conflict | The image, the 5/5 recording, and the 28-versus-31 conflict being *derived* rather than declared |
| 2:10 to 2:45 | Guided partner mode | Rephrase one question, hold and reopen a gap, save a correction, show both answer versions |
| 2:45 to 3:05 | Mapping gate | Flow path, safe stop, next qualified action. Nothing is certified or submitted |
| 3:05 to 3:25 | /stack and /evidence | The badge reports what the process has; the dashboard shows evidence classes and 18/18 proof |
| 3:25 to 4:00 | Google Cloud | Cloud Run dashboard, Firestore documents, Cloud Scheduler job, Vertex AI logs, architecture diagram |

## Preflight

- Redeploy so the live service carries the autonomy work, then create the Cloud Scheduler job
  against `/internal/scan-due`.
- Public project URL returns 200.
- `POST /downstream/demo/run` returns a receipt with 0 continue clicks.
- `/stack` reports the services this deployment actually has.
- `/developer` issues a key with no invitation and the console runs the full sequence.
- `/health`, `/downstream/proof`, and `/downstream/conformance` are public.
- 313 tests, accessibility, and 63/63 executable flow pass.
- GitHub repository is public and README setup works.
- Architecture source and rendered SVG are visible.
- Demo video is public on YouTube or Vimeo and approximately four minutes.
- Correct category, teammates, Representative, repository, URL, and video are set on Devpost.
- Synthetic-data, AI-assistance, source, no-endorsement, and safety disclosures are visible.
- Public build story URL is entered in Devpost.
- Public X post with `#AllThingsAgenticHackathon` is published and entered in Devpost.
