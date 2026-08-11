"""Recorded Gemma safety integration used before owner notes reach later model calls."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spine.redact import Redactor, ReplayReviewer

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
SYNTHETIC_NOTE = (
    "The gravel lane was checked yesterday with Taylor McNeil. Jordan Lee at the county desk "
    "asked us to call after hours if water reaches the white fence."
)


def gemma_redaction_proof() -> dict[str, Any]:
    recordings = json.loads((FIXTURES / "gemma_names.json").read_text(encoding="utf-8"))
    report = json.loads((FIXTURES / "gemma_accuracy_report.json").read_text(encoding="utf-8"))
    names = recordings["owner_note"]
    result = Redactor(ReplayReviewer(names)).redact(SYNTHETIC_NOTE)
    leaked = [name for name in names if name in result.text]
    return {
        "model": report["model"],
        "job": "review already-pattern-cleaned owner notes for remaining person-name spans",
        "input_is_synthetic": True,
        "recorded_spans": names,
        "redacted_text": result.text,
        "measured": report,
        "identifiers_leaked_in_replay": leaked,
        "boundary": (
            "Gemma returns spans only. Its prose is never used. A live reviewer failure blocks "
            "later model use rather than continuing with unredacted text."
        ),
    }
