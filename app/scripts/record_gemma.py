"""Record and grade Gemma name-span review for synthetic dam-owner notes."""

from __future__ import annotations

import json
import os
from pathlib import Path

from spine.redact import GemmaReviewer, RedactionError, Redactor, ReplayReviewer

ROOT = Path(__file__).resolve().parent.parent / "fixtures"

CASES = [
    (
        "owner_note",
        "The gravel lane was checked yesterday with Taylor McNeil. Jordan Lee at the county desk "
        "asked us to call after hours if water reaches the white fence.",
        ["Taylor McNeil", "Jordan Lee"],
    ),
    (
        "inspection_note",
        "Morgan Alvarez walked the pond with Casey Osei before the storm. The overflow channel "
        "was clear and the access road was passable.",
        ["Morgan Alvarez", "Casey Osei"],
    ),
    (
        "clean_control",
        "The spillway was clear. Heavy rain is expected overnight. Check the access road at dawn.",
        [],
    ),
]


def main() -> int:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "agentic-fleet-2026")
    reviewer = GemmaReviewer(project=project, location="global")
    recordings = {}
    expected_total = found_total = false_positives = 0
    leaked = []
    for key, note, expected in CASES:
        try:
            names = reviewer.find_names(note)
        except RedactionError as exc:
            print(f"Gemma failed closed: {exc}")
            return 1
        recordings[key] = names
        hits = [name for name in expected if any(name in found or found in name for found in names)]
        extras = [name for name in names if not any(want in name or name in want for want in expected)]
        result = Redactor(ReplayReviewer(names)).redact(note)
        leaked.extend(name for name in expected if name in result.text)
        expected_total += len(expected)
        found_total += len(hits)
        false_positives += len(extras)
    report = {
        "model": reviewer.DEFAULT_MODEL,
        "location": "global",
        "project": project,
        "recall": {"found": found_total, "expected": expected_total},
        "false_positives": false_positives,
        "identifiers_leaked": len(leaked),
        "synthetic_fixtures": True,
    }
    (ROOT / "gemma_names.json").write_text(json.dumps(recordings, indent=2), encoding="utf-8")
    (ROOT / "gemma_accuracy_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if found_total == expected_total and not leaked else 1


if __name__ == "__main__":
    raise SystemExit(main())
