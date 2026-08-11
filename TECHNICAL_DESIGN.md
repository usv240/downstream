# Downstream: As-Built Technical Design

This document describes running code. Future ideas are marked explicitly.

## Runtime

- FastAPI service on a standalone Cloud Run deployment.
- Firestore workspace persistence in deployment, memory storage for credential-free local tests.
- Google Gen AI SDK with Vertex AI Gemini 3.5 Flash at the global model endpoint.
- USACE NID public ArcGIS FeatureServer for live read-only inventory queries.
- Copied, tested shared spine for clocks, resumable runs, wakes, redaction, untrusted-input
  quarantine, quote verification, and observability primitives.

## Data and state

One `downstream_workspaces/{workspace_id}` document contains the synthetic dam record, drawing facts,
owner answers, skipped gaps, sessions, profile, plan sections, mapping decision, and draft status.
Only structured facts are reloaded. Full chat transcripts are not stored or replayed.

## Multimodal evidence path

`downstream/reader.py` sends the synthetic drawing to Gemini 3.5 Flash. The schema requires a full
transcription followed by facts with key, value, quote, and confidence. The reader rejects empty
quotes, quotes absent from the transcription, invalid confidence values, and absent transcripts.
The real response, ground truth, image, and 5/5 report ship in `app/fixtures/`.

## Partner loop

`downstream/partner.py` owns the bounded question bank and profile. The engine checks resolved facts
before returning the next question. `downstream/collaboration.py` adds a targeted question when
retrieved sources conflict, attaches both source fragments, and records the owner's context without
marking the technical discrepancy resolved. Answers are normalized into provenance-bearing facts.

Owner corrections create numbered answer versions, retain the initial answer and reason for change,
and immediately recompose the affected draft section. The public audit route exposes an adaptation
snapshot and a section-by-section evidence ledger.

The context meter models three bounded inputs: deduplicated facts, one current section, and fixed-k
requirement passages. Empty sessions increase the transcript-replay comparison but do not increase
the structured context value.

## Safety

`downstream/safety.py` implements the map gate. An approved source map can pass to review. A
simplified method requires all three facts: documented applicability, jurisdictional acceptance,
and reference-map comparison. If any fact is false or unknown, the decision is `safe_stop` and
`may_render_extent` is false.

The current demo intentionally fails all three gates. The UI draws one line labelled as a flow-path
input. It does not draw a polygon or make claims about flood extent, depth, velocity, arrival time,
population at risk, or evacuation boundaries.

## Claim verification

The shared Verifier accepts a source reference only when its nonempty quoted text is contained in
the registered source artifact. `/downstream/proof` executes both the empty-quote rejection and a
valid bounded claim, along with map and context checks.

## External boundaries

The live NID route is read-only. It returns an explicit empty fallback when the federal endpoint is
unavailable rather than presenting stale records as current. A null `EAP_PREPARED` field is labelled
unreported in that field, never translated into evidence that a plan is absent.

No route approves, certifies, submits, contacts an agency, sends a warning, orders evacuation, or
replaces state and engineering review.

## Future work, not built

- Jurisdiction-filtered requirement embeddings in Vertex AI Vector Search.
- A validated simplified inundation workflow for a regulator-approved test case.
- Approved-map upload and version comparison.
- Deterministic PDF draft export.

These are not public capability claims and are not needed for the current safe, complete demo.
