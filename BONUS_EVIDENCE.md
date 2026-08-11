# Bonus evidence

## Additional Google AI model

| Model | Product job | Execution proof | Safety boundary |
|---|---|---|---|
| Gemma 4, `gemma-4-26b-a4b-it-maas` | Reviews already-pattern-cleaned owner notes for remaining person-name spans before any later model use | `app/scripts/record_gemma.py`, `app/fixtures/gemma_names.json`, `app/fixtures/gemma_accuracy_report.json`, and `/downstream/bonus` | Spans only, never prose; live failure blocks rather than continuing unredacted |

The cases are synthetic. The recording is graded for recall, false positives, and identifiers that
survive the complete replay gate. This is a real privacy job in the workflow, not a decorative
model call.

No Imagen, Veo, or Lyria bonus is claimed for Downstream at this point.

## Public build content: published evidence for up to 0.2

[The Registry Said 28 Feet. The Drawing Said 31.](https://dev.to/ujwal240/the-registry-said-28-feet-the-drawing-said-31-4dma)
is public on DEV Community and contains the required hackathon-purpose disclosure. Add this exact
URL to the Downstream Devpost submission. Judges determine whether the contribution earns the bonus.

## Social publication: pending, up to 0.2

Publish the prepared project-specific copy on X with the exact hashtag
`#AllThingsAgenticHackathon`, then add the public post URL to the Downstream Devpost submission.
