# Downstream: As-Built Plan

**Track:** The Collaborative Partner

**Status:** implemented, deployed, and published in a standalone repository on August 11, 2026.
The public build story is live. The required public demo video remains the Stage One release gate.

## Product promise

Help a resource-constrained dam owner turn scattered records and local knowledge into a reviewable
Emergency Action Plan draft over many short sessions. Resolve what data already knows. Ask only
what the owner must supply. Learn how they prefer to work. Stop when evidence or authority is
insufficient.

## As-built workflow

1. Query the official USACE NID public service with literal field names.
2. Keep the working demo synthetic and distinguish an unreported field from a missing plan.
3. Read a synthetic legacy drawing with Gemini 3.5 Flash, transcribe first, and retain only facts
   whose quotes occur in that transcription.
4. Surface the drawing and registry height conflict instead of silently merging it.
5. Create a durable Firestore workspace.
6. Ask five owner questions one at a time, then create a sixth targeted clarification when retrieved sources conflict.
7. Capture unknown terms, accept, edit, held-question recovery, and not-right feedback in an inspectable profile.
8. Compose plan sections from structured facts and source-bearing requirements.
9. Refuse to render an inundation boundary because applicability, jurisdiction, and reference-map
   comparison are unproven.
10. Preserve a shareable workspace URL across refreshes and present raw proof through a human-readable evidence dashboard.
11. Present the result as a draft for qualified review, never approval or submission.

## Acceptance gates

- 208 tests green.
- 26/26 executable demo checks green.
- WCAG 2.2 AA token checks green in light and dark themes.
- Gemini drawing record graded 5/5 against adjacent synthetic truth.
- No endpoint can approve, certify, submit, or order evacuation.
- No unvalidated inundation extent is rendered.
- All public-data and authority limitations appear on the product and judge pages.
- Separate Cloud Run service, repository, URL, README, architecture, and video.

## Remaining release work

1. Complete a visual browser walkthrough on desktop and mobile when the browser connector ACL permits it.
2. Record and publish the required approximately four-minute demo.
3. Enter the separate Devpost submission under The Collaborative Partner.