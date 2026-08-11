"""Record and grade one real Gemini 3.5 Flash multimodal call."""

from __future__ import annotations

import json
import os
from pathlib import Path

from downstream.reader import DrawingReader, DrawingVertexClient

ROOT = Path(__file__).resolve().parent.parent / "fixtures"


def main() -> int:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "agentic-fleet-2026")
    image = (ROOT / "cedar_hollow_drawing.png").read_bytes()
    raw_client = DrawingVertexClient(project=project)
    raw = raw_client.extract(image)
    recording = ROOT / "cedar_hollow_drawing.recording.json"
    recording.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    DrawingReader(raw_client.__class__.__new__(raw_client.__class__))
    # Grade the recorded output through replay, avoiding a second paid call.
    from downstream.reader import DrawingReplayClient

    parsed = DrawingReader(DrawingReplayClient(raw)).read(image)
    truth = json.loads((ROOT / "cedar_hollow_drawing.truth.json").read_text(encoding="utf-8"))
    got = {fact["key"]: fact["value"] for fact in parsed.facts}
    fields = {
        "crest_elevation": truth["facts"]["crest_elevation"] in got.get("crest_elevation", ""),
        "spillway_width": "18" in got.get("spillway", ""),
        "dam_height_ft": truth["facts"]["dam_height_ft"] in got.get("dam_height_ft", ""),
        "all_quotes_grounded": all(fact["quoted_text"] in parsed.transcription for fact in parsed.facts),
        "no_dropped_facts": not parsed.dropped,
    }
    report = {
        "model": raw_client.model,
        "location": raw_client.location,
        "project": project,
        "fields": fields,
        "correct": sum(fields.values()),
        "total": len(fields),
        "synthetic_fixture": True,
    }
    (ROOT / "drawing_accuracy_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if all(fields.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
