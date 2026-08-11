# Downstream submission kit

## Devpost fields

**Category:** The Collaborative Partner

**One sentence:** Downstream is a multi-session partner that combines public dam records,
source-grounded drawing facts, and owner knowledge into a reviewable Emergency Action Plan draft,
while refusing to invent an inundation boundary.

**Value:** It removes the coordination burden of resolving scattered facts, remembering prior
answers, adapting language, tracking incomplete sections, and assembling a traceable first draft.

**Technology:** Gemini 3.5 Flash through Vertex AI and the Google Gen AI SDK, Cloud Run, Firestore,
Cloud Trace primitives, USACE NID public FeatureServer, FastAPI, accessible HTML, SVG, and Python.

## Four-minute shot list

| Time | Screen | Narration goal |
|---|---|---|
| 0:00 to 0:25 | Landing page | State the owner problem, measured NID scale, and draft boundary |
| 0:25 to 0:50 | Live NID query | Show real federal data and explain null means unreported, not no plan |
| 0:50 to 1:20 | Synthetic drawing and evidence | Show the image, 5/5 recording, quotes, and surfaced height conflict |
| 1:20 to 2:05 | Partner preset | Answer one question, flag a term, and show later language simplify |
| 2:05 to 2:35 | Profile and context meter | Show inspectable adaptation and flat structured context after resume |
| 2:35 to 3:05 | Mapping gate | Show flow path, safe stop, and next qualified action |
| 3:05 to 3:30 | Draft and proof | Show source-bearing sections and executable proof |
| 3:30 to 4:00 | Google Cloud | Show Cloud Run URL, Firestore state, Vertex AI logs, and architecture |

## Preflight

- Public project URL returns 200.
- `/health`, `/downstream/proof`, and `/downstream/conformance` are public.
- 166 tests, accessibility, and 19/19 deployed flow pass.
- GitHub repository is public and README setup works.
- Architecture source and rendered SVG are visible.
- Demo video is public on YouTube or Vimeo and approximately four minutes.
- Correct category, teammates, Representative, repository, URL, and video are set on Devpost.
- Synthetic-data, AI-assistance, source, no-endorsement, and safety disclosures are visible.
