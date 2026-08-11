# Validation evidence

Verified locally on August 11, 2026:

- `191 passed` from the standalone test suite.
- `26/26` from the executable end-to-end judge flow.
- WCAG 2.2 AA token checks pass in light and dark themes.
- One real Vertex AI Gemini 3.5 Flash drawing call scored `5/5` against adjacent truth.
- The executable safety proof passes every check.
- The OpenAPI surface contains no approve, certify, submit, or evacuation endpoint.

Deployed as Cloud Run revision `downstream-00007-f69` at https://downstream-109051079423.us-central1.run.app. The public adaptation workflow passes 26/26, the executable proof passes 10/10, and the judge page publishes the measured 191-test gate.

- Public standalone repository: https://github.com/usv240/downstream
- Unknown-term feedback re-asks the same unresolved question in plain language with a gloss; it does not fabricate an answer or advance the workflow.

- The guided workspace, shareable resume URL, held-question recovery, judge page, and human-readable evidence dashboard are public and return HTTP 200.
