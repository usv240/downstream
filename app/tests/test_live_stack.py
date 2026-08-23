"""The badge on every page must describe the process, not a wish list.

The version this replaces held a literal array headed "Live request path" naming Gemini 3.5 Flash
and Cloud Trace. Neither was reachable from a request: the only Vertex call lived in an offline
recorder and `setup_tracing` had no callers. A page cannot be allowed to assert that on its own,
so the list now comes from `/stack` and these tests check both halves.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from service.runtime import local_runtime
from spine.quota import QuotaPolicy

WEB = Path(__file__).resolve().parents[1] / "web"
SCRIPT = (WEB / "live-stack.js").read_text(encoding="utf-8")
# Comments explain why the names are absent, so the name check reads code only.
CODE = "".join(
    line.split("//")[0] if line.strip().startswith("//") else line
    for line in SCRIPT.splitlines(keepends=True)
)


def test_live_stack_is_available_on_every_custom_public_page() -> None:
    for name in (
        "downstream.html",
        "developer.html",
        "downstream-evidence.html",
        "downstream-judges-v2.html",
    ):
        html = (WEB / name).read_text(encoding="utf-8")
        assert "/static/live-stack.js" in html, name


def test_the_badge_hardcodes_no_service_names_at_all() -> None:
    """Whatever it says has to have come from the server."""
    for service in (
        "Gemini",
        "Cloud Run",
        "Firestore",
        "Cloud Trace",
        "Secret Manager",
        "Gemma",
        "Vertex",
    ):
        assert service not in CODE, f"{service} is asserted by the page instead of reported"
    assert '"/stack"' in CODE


def test_the_badge_still_carries_its_disclaimers() -> None:
    css = (WEB / "styles.css").read_text(encoding="utf-8")
    assert "Technology used; no endorsement implied." in SCRIPT
    assert "sponsor" not in SCRIPT.lower()
    assert ".live-stack:focus-within" in css


def test_the_badge_can_say_a_service_is_not_in_the_request_path() -> None:
    assert "not in the request path" in SCRIPT
    assert "in the request path" in SCRIPT


def stack(**overrides) -> dict:
    app = FastAPI()
    runtime = local_runtime(**overrides)

    @app.get("/stack")
    def _stack() -> dict:
        return runtime.stack()

    return TestClient(app).get("/stack").json()


def entry(payload: dict, service: str) -> dict:
    return next(row for row in payload["request_path"] if service in row["service"])


def test_the_report_marks_a_replay_only_deployment_as_not_running_gemini() -> None:
    payload = stack()
    assert entry(payload, "Gemini")["active"] is False
    assert "replay" in entry(payload, "Gemini")["detail"].lower()


def test_the_report_marks_tracing_inactive_when_the_exporter_is_not_wired() -> None:
    assert entry(stack(), "Cloud Trace")["active"] is False


def test_the_report_marks_memory_persistence_as_not_firestore() -> None:
    assert entry(stack(), "Firestore")["active"] is False


def test_a_live_deployment_reports_gemini_as_active() -> None:
    runtime = local_runtime()
    runtime.drawing.live_enabled = True
    runtime.tracing_active = True
    runtime.persistence = "firestore"
    payload = runtime.stack()
    for service in ("Gemini", "Cloud Trace", "Firestore"):
        assert next(row for row in payload["request_path"] if service in row["service"])["active"]


def test_gemma_is_never_claimed_as_live() -> None:
    """It is a graded recording. Saying otherwise would be the exact error being fixed here."""
    gemma = stack()["additional_google_ai"][0]
    assert gemma["active"] is False
    assert "replayed" in gemma["detail"].lower()


def test_the_report_publishes_the_same_limits_the_service_enforces() -> None:
    payload = stack(policy=QuotaPolicy(public_workspaces_per_day=9))
    assert payload["quotas"]["public_workspaces_per_network_per_day"] == 9


def test_cloud_run_is_the_one_thing_that_is_always_true() -> None:
    assert entry(stack(), "Cloud Run")["active"] is True
