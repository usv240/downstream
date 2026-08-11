# Bonus evidence

## Additional Google AI model

| Model | Product job | Execution proof | Safety boundary |
|---|---|---|---|
| Gemma 4, `gemma-4-26b-a4b-it-maas` | Reviews already-pattern-cleaned owner notes for remaining person-name spans before any later model use | `app/scripts/record_gemma.py`, `app/fixtures/gemma_names.json`, `app/fixtures/gemma_accuracy_report.json`, and `/downstream/bonus` | Spans only, never prose; live failure blocks rather than continuing unredacted |

The cases are synthetic. The recording is graded for recall, false positives, and identifiers that
survive the complete replay gate. This is a real privacy job in the workflow, not a decorative
model call.

No Imagen, Veo, or Lyria bonus is claimed for Downstream at this point.
