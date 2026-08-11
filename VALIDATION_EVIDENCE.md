# Validation evidence

Verified locally on August 11, 2026:

- `166 passed` from the standalone test suite.
- `19/19` from the executable end-to-end judge flow.
- WCAG 2.2 AA token checks pass in light and dark themes.
- One real Vertex AI Gemini 3.5 Flash drawing call scored `5/5` against adjacent truth.
- The executable safety proof passes every check.
- The OpenAPI surface contains no approve, certify, submit, or evacuation endpoint.

Deployed as Cloud Run revision `downstream-00002-qsz` at https://downstream-109051079423.us-central1.run.app. All six public judge routes return 200 and the deployed end-to-end flow passes 19/19.

- Public standalone repository: https://github.com/usv240/downstream
- Unknown-term feedback re-asks the same unresolved question in plain language with a gloss; it does not fabricate an answer or advance the workflow.
