# Downstream: As-Built Plan

**Track:** The Collaborative Partner

**Status:** implemented, deployed, and published in a standalone repository on August 11, 2026;
autonomy, abuse control and truthful stack reporting added August 23, 2026. The public build story
is live. **The required public demo video remains the Stage One release gate.**

## Product promise

Help a resource-constrained dam owner turn scattered records and local knowledge into a reviewable
Emergency Action Plan draft over many short sessions. Resolve what data already knows. Ask only
what the owner must supply. Learn how they prefer to work. Stop when evidence or authority is
insufficient.

## As-built workflow

0. A trigger opens a run: the public console, an API client supplying an NID identifier, or Cloud
   Scheduler calling `/internal/scan-due`. Everything in steps 1 to 9 then happens without a
   click, and each step is written to an ordered timeline with the actor that performed it.
1. Query the official USACE NID public service with literal field names.
2. Keep the working demo synthetic and distinguish an unreported field from a missing plan.
3. Read a synthetic legacy drawing with Gemini 3.5 Flash, transcribe first, and retain only facts
   whose quotes occur in that transcription.
4. Derive the height conflict by comparing the drawing read against the registry row, and
   surface it instead of silently merging it. A drawing that agrees produces no extra question.
5. Create a durable Firestore workspace and register two durable wakes: a held-question review
   and an unanswered-question follow-up.
6. Ask five owner questions one at a time, then create a sixth targeted clarification when retrieved sources conflict.
7. Capture unknown terms, accept, edit, held-question recovery, and not-right feedback in an inspectable profile.
8. Compose plan sections from structured facts and source-bearing requirements.
9. Refuse to render an inundation boundary because applicability, jurisdiction, and reference-map
   comparison are unproven.
10. Preserve a shareable workspace URL across refreshes and present raw proof through a human-readable evidence dashboard.
11. Present the result as a draft for qualified review, never approval or submission.
12. Publish an autonomy receipt counted from the stored timeline, and a `/stack` report derived
    from the running process so no page can claim a service the deployment does not have.

## Acceptance gates

- 313 tests green.
- 63/63 executable demo checks green.
- WCAG 2.2 AA token checks green in light and dark themes.
- Gemini drawing record graded 5/5 against adjacent synthetic truth.
- No endpoint can approve, certify, submit, or order evacuation.
- No unvalidated inundation extent is rendered.
- All public-data and authority limitations appear on the product and judge pages.
- Separate Cloud Run service, repository, URL, README, architecture, and video.

## Remaining release work

These are the only open items, and the first two are the Stage One gate.

1. **Record and publish the roughly four-minute demo video** on YouTube or Vimeo, public, showing
   the app working and the Google Cloud backend. Without it the submission does not reach judging.
2. **Enter the Devpost submission** under The Collaborative Partner, with the repository, live
   URL, video, and the public build-story URL.
3. Publish the prepared social post with `#AllThingsAgenticHackathon` and add its URL. Bonus only.
4. Redeploy so the live service carries the autonomy work, then create the Cloud Scheduler job
   against `/internal/scan-due`.
5. Complete a visual browser walkthrough on desktop and mobile when the browser connector ACL
   permits it.