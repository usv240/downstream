"""The scheduler surface that `spine/wake.py` always documented but never had.

Its module docstring says a Cloud Scheduler cron calls `/internal/scan-due`. Until this route
existed the durable wake ladder was a tested library with no way to fire, so the product had no
background execution at all.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from downstream import autonomy
from downstream.partner import create_workspace, skip_question
from service.internal_routes import build_internal_router
from service.runtime import local_runtime
from spine.clock import ClockState, MemoryClockStateStore, SimulatedClock
from spine.wake import WakeScheduler

TOKEN = "scheduler-secret"


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setenv("INTERNAL_SCHEDULER_TOKEN", TOKEN)
    return local_runtime()


@pytest.fixture
def api(runtime) -> TestClient:
    app = FastAPI()
    app.include_router(build_internal_router(runtime))
    return TestClient(app)


def seed(runtime, *, skip: str | None = None) -> dict:
    workspace = create_workspace(scheduler=runtime.scheduler)
    if skip:
        skip_question(workspace, skip)
    runtime.workspaces.put(workspace)
    return workspace


def move_clock_forward(runtime, seconds: float) -> None:
    """Advance the runtime's own scheduler, so the route under test sees due wakes."""
    store = MemoryClockStateStore(ClockState(offset_seconds=seconds))
    runtime.scheduler = WakeScheduler(runtime.wake_store, SimulatedClock(store))


def test_the_route_refuses_without_a_token(api):
    assert api.post("/internal/scan-due").status_code == 401


def test_the_route_refuses_a_wrong_token(api):
    assert api.post(
        "/internal/scan-due", headers={"X-Scheduler-Token": "guess"}
    ).status_code == 401


def test_the_route_refuses_entirely_when_no_token_is_configured(monkeypatch):
    monkeypatch.delenv("INTERNAL_SCHEDULER_TOKEN", raising=False)
    app = FastAPI()
    app.include_router(build_internal_router(local_runtime()))
    response = TestClient(app).post(
        "/internal/scan-due", headers={"X-Scheduler-Token": "anything"}
    )
    assert response.status_code == 503, "an unconfigured trigger must not default to open"


def test_nothing_is_dispatched_before_a_wake_is_due(api, runtime):
    seed(runtime)
    body = api.post("/internal/scan-due", headers={"X-Scheduler-Token": TOKEN}).json()
    assert body["dispatched"] == 0


def test_a_due_wake_is_dispatched_and_changes_the_stored_workspace(api, runtime):
    workspace = seed(runtime, skip="equipment")
    move_clock_forward(runtime, autonomy.NUDGE_AFTER.total_seconds() + 60)

    body = api.post("/internal/scan-due", headers={"X-Scheduler-Token": TOKEN}).json()
    assert body["dispatched"] == 2
    assert sorted(wake["kind"] for wake in body["wakes"]) == [
        autonomy.FOLLOW_UP_KIND,
        autonomy.NUDGE_KIND,
    ]

    stored = runtime.workspaces.get(workspace["workspace_id"])
    assert stored["skipped"] == [], "the held question should have been reopened for the owner"
    assert stored["follow_up_pending"] is True
    steps = [entry["step"] for entry in stored["timeline"]]
    assert "held_questions_reopened" in steps
    assert "follow_up_recorded" in steps


def test_a_wake_fires_once_even_if_the_scheduler_calls_twice(api, runtime):
    seed(runtime)
    move_clock_forward(runtime, autonomy.NUDGE_AFTER.total_seconds() + 60)
    first = api.post("/internal/scan-due", headers={"X-Scheduler-Token": TOKEN}).json()
    second = api.post("/internal/scan-due", headers={"X-Scheduler-Token": TOKEN}).json()
    assert first["dispatched"] == 2
    assert second["dispatched"] == 0


def test_a_wake_whose_workspace_is_gone_completes_rather_than_retrying_forever(api, runtime):
    seed(runtime)
    runtime.workspaces = local_runtime().workspaces  # the workspace no longer exists
    move_clock_forward(runtime, autonomy.NUDGE_AFTER.total_seconds() + 60)
    body = api.post("/internal/scan-due", headers={"X-Scheduler-Token": TOKEN}).json()
    assert body["dispatched"] == 2
    assert body["dead_lettered"] == 0


def test_one_wake_can_be_fired_by_id_for_an_acceptance_check(api, runtime):
    workspace = seed(runtime, skip="equipment")
    wake_id = workspace["wakes"][0]
    move_clock_forward(runtime, autonomy.NUDGE_AFTER.total_seconds() + 60)
    body = api.post(
        f"/internal/wakes/{wake_id}/dispatch", headers={"X-Scheduler-Token": TOKEN}
    ).json()
    assert body["dispatched"] == wake_id
    assert body["workspace"]["skipped"] == []


def test_dispatching_an_unclaimable_wake_is_a_conflict_not_a_silent_success(api, runtime):
    seed(runtime)
    response = api.post(
        "/internal/wakes/does-not-exist/dispatch", headers={"X-Scheduler-Token": TOKEN}
    )
    assert response.status_code == 409


def test_the_scheduler_surface_stays_out_of_the_public_schema(runtime):
    app = FastAPI()
    app.include_router(build_internal_router(runtime))
    assert not any(path.startswith("/internal") for path in app.openapi()["paths"])
