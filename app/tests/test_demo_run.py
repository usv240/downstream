"""One request, trigger to reviewable draft.

The sibling products in this portfolio each expose a one-request server-side demonstration.
Downstream did not, so evaluating it meant performing eleven interactions by hand. This is that
endpoint, and these tests hold it to the same standard: no clicks, real wakes, and a receipt that
does not overstate what happened.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from downstream import autonomy
from service.routes import build_router
from service.runtime import local_runtime
from spine.quota import QuotaPolicy


@pytest.fixture
def api() -> TestClient:
    app = FastAPI()
    app.include_router(build_router(local_runtime()))
    return TestClient(app)


@pytest.fixture
def result(api) -> dict:
    response = api.post("/downstream/demo/run")
    assert response.status_code == 200
    return response.json()


def test_one_request_reaches_a_reviewable_draft(result):
    assert result["workspace_id"].startswith("eap_")
    assert result["autonomy_proof"]["continue_clicks_required"] == 0
    # The mapping gate leads. It is the one section that says what the agent declined to do, and
    # last of six it sat below the fold of a column that scrolls inside itself -- invisible to
    # anyone who did not scroll that pane.
    assert [section["key"] for section in result["plan"]] == [
        "mapping",
        "purpose",
        "notification",
        "preparedness",
        "affected_areas",
        "site_facts",
    ]


def test_the_agent_asks_the_questions_and_the_conflict_is_one_of_them(result):
    assert result["questions_asked_by_the_agent"][-1] == "resolve_dam_height_conflict"
    assert len(result["questions_asked_by_the_agent"]) == 6


def test_the_run_does_more_automatically_than_it_asks_of_a_person(result):
    proof = result["autonomy_proof"]
    assert proof["automatic_agent_steps"] > proof["human_authority_steps"]
    assert proof["automatic_agent_steps"] >= 10


def test_scheduled_actions_really_fire_through_the_production_claim_path(result):
    assert sorted(result["scheduled_actions_fired"]) == [
        autonomy.FOLLOW_UP_KIND,
        autonomy.NUDGE_KIND,
    ]
    assert result["autonomy_proof"]["durable_wakes_registered"] == 2


def test_the_response_admits_the_clock_was_moved(result):
    assert "simulated" in result["clock"]


def test_the_response_admits_the_owner_answers_are_synthetic(result):
    assert result["synthetic_owner_answers"] is True
    assert result["autonomy_proof"]["synthetic_demonstration"] is True


def test_no_inundation_extent_is_produced_however_complete_the_run(result):
    assert result["mapping"]["may_render_extent"] is False
    mapping = next(s for s in result["plan"] if s["key"] == "mapping")
    assert mapping["status"] == "blocked_for_qualified_review"
    assert any("No inundation" in line for line in result["disclosure"])


def test_every_rendered_section_still_publishes_its_evidence(result):
    assert all(row["rendered_from_evidence"] for row in result["evidence_ledger"])


def test_the_measured_context_stays_inside_its_budget(result):
    meter = result["context_meter"]
    assert meter["within_bound"] is True
    assert meter["structured_context_tokens"] < meter["estimated_transcript_replay_tokens"]


def test_the_run_is_resumable_afterwards(api, result):
    fetched = api.get(f"/downstream/workspaces/{result['workspace_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["progress"]["answered"] == 6


def test_the_receipt_is_also_available_on_its_own_route(api, result):
    receipt = api.get(f"/downstream/workspaces/{result['workspace_id']}/autonomy")
    assert receipt.status_code == 200
    assert receipt.json()["continue_clicks_required"] == 0


def test_the_public_route_is_capped_per_network():
    """Unauthenticated workspace creation used to be unbounded, and each one is a durable write."""
    app = FastAPI()
    app.include_router(build_router(local_runtime(policy=QuotaPolicy(public_workspaces_per_day=2))))
    api = TestClient(app)
    assert [api.post("/downstream/workspaces").status_code for _ in range(3)] == [200, 200, 429]


def test_a_capped_caller_is_told_when_the_allowance_returns():
    app = FastAPI()
    app.include_router(build_router(local_runtime(policy=QuotaPolicy(public_workspaces_per_day=1))))
    api = TestClient(app)
    api.post("/downstream/workspaces")
    refused = api.post("/downstream/workspaces")
    assert refused.status_code == 429
    assert refused.headers["X-RateLimit-Remaining"] == "0"
    assert "UTC midnight" in refused.json()["detail"]
