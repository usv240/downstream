# Research traceability

| Public claim | Source | Implementation use | Boundary |
|---|---|---|---|
| The official public inventory exposed 92,606 records on Aug 11, 2026 | [USACE NID](https://nid.sec.usace.army.mil/nid/) public FeatureServer count query | Landing-page measured snapshot and research API | Time-stamped measurement, not a permanent count |
| 16,972 public records carried `HAZARD_POTENTIAL='High'` on that date | Same official count query | Scale indicator | Consequence classification, not condition or failure probability |
| The public NID service exposes Web GIS services and searchable record fields | [USACE NID](https://nid.sec.usace.army.mil/nid/) | Live read-only registry route | External availability is not guaranteed; fallback is explicit and empty |
| EAPs identify potential emergency conditions and actions to minimize loss of life and property damage | [FEMA P-64](https://www.fema.gov/sites/default/files/2020-08/fema_dam-safety_emergency-action-planning_P-64.pdf), page I-1 | Purpose section and Verifier fixture | Guidance does not establish state approval |
| Dam owners and emergency managers work together, and a notification flowchart identifies who calls whom | [ASDSO Emergency Action Planning](https://damsafety.org/dam-owners/emergency-action-planning) | Contact question and notification section | Contact values come from structured owner facts, never generated guesses |
| Simplified mapping is most applicable in limited settings and does not remove regulatory or engineering duties | [SIMS methodology](https://www.damsafety.org/sites/default/files/files/EAPWG%20Final%20SIMS.pdf) | Three-part mapping gate | Current demo fails closed and renders no extent |

## Measured product evidence

| Claim | Regenerable artifact |
|---|---|
| Gemini drawing extraction scored 5/5 | `app/fixtures/drawing_accuracy_report.json` |
| 164 tests pass | `cd app && python -m pytest -q` |
| 19/19 end-to-end checks pass | `app/scripts/downstream_demo_flow.py` |
| Both themes pass the accessibility gate | `app/scripts/check_a11y.py` |

## Corrections made during implementation

The archived design translated an unreported public EAP field into an estimate of dams without an
EAP. A live field audit showed that this inference is not defensible. The implementation now says
only that the selected public field is unreported and uses a synthetic dam for authoring.
