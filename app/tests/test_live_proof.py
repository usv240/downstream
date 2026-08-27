"""The one clock the visitor does not control.

Everything else on the public page runs on a simulated clock the page advances, which is honest
and labelled but leaves a fair objection standing: a button was pressed, so how is that
autonomous? These tests pin the property that answers it -- the page can arm the wake and can
watch for it, and cannot under any circumstance execute it.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from downstream.live_proof import LEAD_SECONDS, WAKE_KIND, revision
from service.internal_routes import build_internal_router
from service.routes import build_router
from service.runtime import local_runtime
from spine.clock import ClockState, MemoryClockStateStore, SimulatedClock
from spine.wake import WakeScheduler

TOKEN = "scheduler-secret"


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setenv("INTERNAL_SCHEDULER_TOKEN", TOKEN)
    monkeypatch.setenv("K_REVISION", "downstream-00042-test")
    return local_runtime()


@pytest.fixture
def api(runtime) -> TestClient:
    app = FastAPI()
    app.include_router(build_router(runtime))
    app.include_router(build_internal_router(runtime))
    return TestClient(app)


def arm(api: TestClient) -> tuple[str, str]:
    workspace_id = api.post("/downstream/workspaces").json()["workspace_id"]
    armed = api.post(f"/downstream/workspaces/{workspace_id}/live-proof")
    assert armed.status_code == 200, armed.text
    return workspace_id, armed.json()["wake_id"]


def move_clock_forward(runtime, seconds: float) -> None:
    store = MemoryClockStateStore(ClockState(offset_seconds=seconds))
    runtime.scheduler = WakeScheduler(runtime.wake_store, SimulatedClock(store))


# --------------------------------------------------------------------------- arming

def test_arming_registers_a_wake_on_the_real_clock(api):
    workspace_id = api.post("/downstream/workspaces").json()["workspace_id"]
    body = api.post(f"/downstream/workspaces/{workspace_id}/live-proof").json()
    assert body["seconds_until_due"] == LEAD_SECONDS
    assert body["workspace_id"] == workspace_id
    assert "will run it" in body["note"]


def test_the_lead_is_short_because_the_wait_is_lead_plus_scheduler_drift(api):
    """Measured gaps between sweeps ran to 84 seconds on a once-a-minute job. A long lead buys
    nothing an observer sees and costs the whole margin."""
    assert LEAD_SECONDS <= 30


def test_arming_twice_produces_two_separate_proofs(api):
    workspace_id = api.post("/downstream/workspaces").json()["workspace_id"]
    first = api.post(f"/downstream/workspaces/{workspace_id}/live-proof").json()["wake_id"]
    second = api.post(f"/downstream/workspaces/{workspace_id}/live-proof").json()["wake_id"]
    assert first != second, "idempotent registration must not collapse two proofs into one"


def test_arming_an_unknown_workspace_is_refused(api):
    assert api.post("/downstream/workspaces/eap_nope/live-proof").status_code == 404


# --------------------------------------------------------------------------- the page cannot fire it

def test_the_page_cannot_execute_the_wake_however_often_it_polls(api):
    _, wake_id = arm(api)
    for _ in range(6):
        body = api.get(f"/downstream/live-proof/{wake_id}").json()
        assert body["fired"] is False
    assert body["found"] is True


def test_polling_an_unknown_proof_is_a_404_not_a_false_negative(api):
    assert api.get("/downstream/live-proof/wk_does_not_exist").status_code == 404


def test_the_scheduler_will_not_run_it_before_it_is_due(api):
    arm(api)
    body = api.post("/internal/scan-due", headers={"X-Scheduler-Token": TOKEN}).json()
    assert body["dispatched"] == 0


def test_an_unauthenticated_caller_cannot_drive_the_scheduler(api, runtime):
    arm(api)
    move_clock_forward(runtime, 60)
    assert api.post("/internal/scan-due").status_code == 401


# --------------------------------------------------------------------------- the scheduler can

def test_the_scheduler_runs_it_and_stamps_the_revision_that_did(api, runtime):
    workspace_id, wake_id = arm(api)
    move_clock_forward(runtime, 60)

    dispatched = api.post("/internal/scan-due", headers={"X-Scheduler-Token": TOKEN}).json()
    assert dispatched["dispatched"] == 1
    assert dispatched["wakes"][0]["kind"] == WAKE_KIND

    status = api.get(f"/downstream/live-proof/{wake_id}").json()
    assert status["fired"] is True
    assert status["revision"] == "downstream-00042-test"
    assert status["fired_at"]
    assert "nobody watching" in status["detail"]

    workspace = api.get(f"/downstream/workspaces/{workspace_id}").json()
    assert workspace["timeline"][-1]["step"] == "unattended_review_ran"
    assert workspace["timeline"][-1]["actor"] == "agent"


def test_the_step_is_attributed_to_the_agent_not_to_the_owner(api, runtime):
    workspace_id, _ = arm(api)
    move_clock_forward(runtime, 60)
    api.post("/internal/scan-due", headers={"X-Scheduler-Token": TOKEN})
    receipt = api.get(f"/downstream/workspaces/{workspace_id}/autonomy").json()
    assert receipt["human_authority_steps"] == 0
    assert any(step["step"] == "unattended_review_ran" for step in receipt["timeline"])


def test_it_fires_once_even_if_the_scheduler_calls_twice(api, runtime):
    workspace_id, _ = arm(api)
    move_clock_forward(runtime, 60)
    first = api.post("/internal/scan-due", headers={"X-Scheduler-Token": TOKEN}).json()
    second = api.post("/internal/scan-due", headers={"X-Scheduler-Token": TOKEN}).json()
    assert (first["dispatched"], second["dispatched"]) == (1, 0)

    workspace = api.get(f"/downstream/workspaces/{workspace_id}").json()
    ran = [s for s in workspace["timeline"] if s["step"] == "unattended_review_ran"]
    assert len(ran) == 1, "a wake fires once; a repeated sweep must not duplicate the step"


def test_the_unattended_step_sends_nothing_to_anyone(api, runtime):
    workspace_id, _ = arm(api)
    move_clock_forward(runtime, 60)
    api.post("/internal/scan-due", headers={"X-Scheduler-Token": TOKEN})
    workspace = api.get(f"/downstream/workspaces/{workspace_id}").json()
    step = workspace["timeline"][-1]
    assert "Nothing was sent" in step["detail"]
    assert workspace["mapping"]["may_render_extent"] is False


def test_the_internal_bookkeeping_never_reaches_the_public_view(api, runtime):
    workspace_id, _ = arm(api)
    move_clock_forward(runtime, 60)
    api.post("/internal/scan-due", headers={"X-Scheduler-Token": TOKEN})
    workspace = api.get(f"/downstream/workspaces/{workspace_id}").json()
    for key in ("_live_proof_wake_id", "_live_proof_revision", "_live_proof_armed_at"):
        assert key not in workspace


def test_revision_falls_back_to_local_off_platform(monkeypatch):
    monkeypatch.delenv("K_REVISION", raising=False)
    assert revision() == "local"
    monkeypatch.setenv("K_REVISION", "downstream-00007-abc")
    assert revision() == "downstream-00007-abc"


def test_the_page_offers_the_proof_and_never_claims_to_run_it():
    from pathlib import Path

    web = Path(__file__).resolve().parents[1] / "web"
    html = (web / "downstream.html").read_text(encoding="utf-8")
    js = (web / "downstream-v2.js").read_text(encoding="utf-8")
    assert 'id="arm-live-proof"' in html
    assert "Close the tab and it still fires" in html
    assert "/live-proof" in js
    assert "This page did not run it." in js



def test_firing_updates_the_receipt_without_re_rendering_the_console():
    """It fires while the user is mid-task, which is the point of it.

    A full re-render at an unpredictable moment would wipe a half-typed correction, live, in a
    recording that has to be one take.
    """
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "web" / "downstream-v2.js").read_text(
        encoding="utf-8"
    )
    start = js.index("async function armLiveProof")
    fired = js[start: js.index("armLiveProof);", start)]
    assert "renderAutonomy(refreshed)" in fired
    # `render(` on its own would redraw the question card and the correction card too.
    assert "\n          render(" not in fired


def test_the_fired_status_carries_the_job_record() -> None:
    """A page can show the wake itself -- id, armed, due, fired, revision -- not a paraphrase."""
    from downstream.live_proof import status

    armed = {"wake_id": "wk_1", "armed_at": "2026-08-27T00:00:00+00:00", "due_at": "2026-08-27T00:00:05+00:00"}
    workspace = {"timeline": [{
        "step": "unattended_review_ran", "at": "2026-08-27T00:00:50+00:00", "detail": "reviewed",
        "evidence": {"wake_id": "wk_1", "revision": "downstream-00056-d5b", "waited_seconds": 50},
    }]}
    body = status(armed, workspace)
    assert body["fired"] is True
    assert (body["wake_id"], body["armed_at"], body["due_at"]) == ("wk_1", armed["armed_at"], armed["due_at"])
    assert body["revision"] == "downstream-00056-d5b"


def test_the_unattended_review_reports_what_it_checked(api, runtime):
    """The step used to say "reviewed the draft" and nothing more. It states what it found now,
    and every number in the sentence is carried as evidence a reader can check."""
    workspace_id, _ = arm(api)
    move_clock_forward(runtime, 60)
    api.post("/internal/scan-due", headers={"X-Scheduler-Token": TOKEN})
    workspace = api.get(f"/downstream/workspaces/{workspace_id}").json()
    step = workspace["timeline"][-1]
    assert step["step"] == "unattended_review_ran"
    assert "sections ready for review" in step["detail"]
    assert "flood map stays blocked" in step["detail"]
    assert "Nothing was sent" in step["detail"]
    ev = step["evidence"]
    assert ev["sections_total"] == len(workspace["plan"])
    assert ev["sections_ready"] == sum(1 for s in workspace["plan"] if s["status"] == "ready_for_review")
    assert ev["mapping_blocked"] is True
    assert ev["conflict_open"] is True, "the 28-vs-31 conflict is unresolved in a fresh workspace"
    assert set(ev["waiting_on"]) == set(workspace["outstanding"])
