"""Where Gemini actually enters the request path.

Before this module the only Vertex AI call in the project lived in `scripts/record_drawing.py`,
an offline recorder. The deployed service replayed its JSON and nothing else, so a judge opening
the live URL saw no model inference at all.

`DrawingService` puts the call back in the request path while keeping three promises:

* **Cost stays bounded.** Live inference is opt-in per deployment and capped by a shared daily
  quota. Past the cap the service replays instead of spending.
* **A failure never breaks the demo.** Any Vertex error falls back to the graded recording, and
  the fallback is reported rather than hidden.
* **The page never overstates what happened.** Every read carries `execution`, so the UI can say
  "live Vertex AI call" or "recorded replay" from what the process actually did.

The model's transcription is third-party text lifted off a scanned drawing, so it goes through
the untrusted-document gate before anything quotes it. An instruction-shaped span is removed
before the quote gate runs, which means an injected line cannot become a grounded fact.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from downstream.reader import DrawingReader, DrawingReplayClient, DrawingVertexClient
from spine import untrusted

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

LIVE = "live_vertex_call"
REPLAY = "recorded_replay"
REPLAY_AFTER_ERROR = "recorded_replay_after_live_error"
REPLAY_AT_QUOTA = "recorded_replay_at_daily_cap"


@dataclass(frozen=True)
class DrawingOutcome:
    """What one drawing read produced, and how it was produced."""

    transcription: str
    facts: list[dict[str, Any]]
    dropped: list[str]
    execution: str
    model: str
    elapsed_ms: float = 0.0
    quarantined: list[dict[str, str]] = field(default_factory=list)
    error: str | None = None

    @property
    def was_live(self) -> bool:
        return self.execution == LIVE

    def receipt(self) -> dict[str, Any]:
        return {
            "execution": self.execution,
            "model": self.model,
            "live_inference": self.was_live,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "facts_kept": len(self.facts),
            "facts_dropped": self.dropped,
            "quarantined_spans": self.quarantined,
            "error": self.error,
        }


class DrawingService:
    """Resolve a drawing read to a live call or a recorded replay, and say which."""

    def __init__(
        self,
        *,
        project: str,
        model: str = "gemini-3.5-flash",
        location: str = "global",
        live_enabled: bool = False,
        quota=None,
        fixtures: Path = FIXTURES,
    ) -> None:
        self.project = project
        self.model = model
        self.location = location
        self.live_enabled = live_enabled
        self._quota = quota
        self._fixtures = fixtures

    @classmethod
    def from_environment(cls, project: str, quota=None) -> DrawingService:
        """Live inference is ON unless someone explicitly turns it off.

        This defaulted to off once, as cost control, and the service shipped performing no
        inference at all while the rules require Gemini 3.5 in the product. A daily cap is the
        right way to bound spend; a default that silently removes the mandated model is not.
        Turning it off now takes a deliberate `DOWNSTREAM_LIVE_MODEL=false`.
        """
        setting = os.environ.get("DOWNSTREAM_LIVE_MODEL", "true").strip().lower()
        enabled = setting not in {"0", "false", "no", "off"}
        # Not a policy switch: without a real project id there is no Vertex endpoint to call.
        return cls(
            project=project,
            model=os.environ.get("DOWNSTREAM_MODEL", "gemini-3.5-flash"),
            live_enabled=enabled and project not in {"", "local"},
            quota=quota,
        )

    @property
    def mode(self) -> str:
        return "live_with_replay_fallback" if self.live_enabled else "recorded_replay_only"

    def _image(self) -> bytes:
        return (self._fixtures / "cedar_hollow_drawing.png").read_bytes()

    def _recording(self) -> dict[str, Any]:
        path = self._fixtures / "cedar_hollow_drawing.recording.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def read(self) -> DrawingOutcome:
        started = time.perf_counter()
        image = self._image()

        if not self.live_enabled:
            return self._replay(image, REPLAY, started=started)

        if self._quota is not None:
            verdict = self._quota.check("drawing_read")
            if not verdict.allowed:
                return self._replay(image, REPLAY_AT_QUOTA, started=started)

        try:
            client = DrawingVertexClient(
                project=self.project, location=self.location, model=self.model
            )
            return self._grade(DrawingReader(client), image, LIVE, started=started)
        except Exception as exc:  # a model outage falls back, it does not 500
            return self._replay(
                image, REPLAY_AFTER_ERROR, error=f"{type(exc).__name__}: {exc}", started=started
            )

    def _replay(
        self, image: bytes, execution: str, error: str | None = None, started: float | None = None
    ) -> DrawingOutcome:
        reader = DrawingReader(DrawingReplayClient(self._recording()))
        return self._grade(reader, image, execution, error=error, started=started)

    def _grade(
        self,
        reader: DrawingReader,
        image: bytes,
        execution: str,
        error: str | None = None,
        started: float | None = None,
    ) -> DrawingOutcome:
        read = reader.read(image)
        # The transcription is text produced by a third party and copied off a scan. Quarantine
        # instruction-shaped spans before the quote gate, so an injected line cannot ground a fact.
        cleaned, spans = untrusted.sanitise(read.transcription)
        kept = [fact for fact in read.facts if fact["quoted_text"] in cleaned]
        dropped = list(read.dropped) + [
            f"{fact['key']}: quote was quarantined as instruction-shaped"
            for fact in read.facts
            if fact["quoted_text"] not in cleaned
        ]
        for fact in kept:
            fact["provenance"] = "live_gemini_3_5_flash" if execution == LIVE else "recorded_gemini_3_5_flash"
        return DrawingOutcome(
            transcription=cleaned,
            facts=kept,
            dropped=dropped,
            execution=execution,
            model=self.model,
            quarantined=[
                {"threat": str(span.threat), "text": span.text, "why": span.explanation}
                for span in spans
            ],
            error=error,
            elapsed_ms=(time.perf_counter() - started) * 1000 if started else 0.0,
        )
