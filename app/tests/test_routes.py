from fastapi import FastAPI
from fastapi.testclient import TestClient

from downstream.store import MemoryWorkspaceStore
from service.routes import build_router


def client():
    app = FastAPI()
    app.include_router(build_router(MemoryWorkspaceStore()))
    return TestClient(app)


def test_open_and_fetch_workspace():
    api = client()
    opened = api.post("/downstream/workspaces", json={}).json()
    fetched = api.get(f"/downstream/workspaces/{opened['workspace_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["dam"]["synthetic"] is True


def test_unknown_workspace_is_404():
    assert client().get("/downstream/workspaces/missing").status_code == 404


def test_end_to_end_partner_flow():
    api = client()
    workspace = api.post("/downstream/workspaces", json={}).json()
    workspace_id = workspace["workspace_id"]
    for index in range(5):
        question = workspace["next_question"]
        workspace = api.post(
            f"/downstream/workspaces/{workspace_id}/answer",
            json={
                "question_id": question["id"],
                "answer": f"Owner fact {index}",
                "did_not_understand": index == 0,
            },
        ).json()
    assert workspace["next_question"] is None
    assert workspace["progress"]["answered"] == 5
    assert workspace["context_meter"]["within_bound"] is True
    assert workspace["mapping"]["may_render_extent"] is False


def test_feedback_capture_is_visible_in_profile():
    api = client()
    workspace = api.post("/downstream/workspaces", json={}).json()
    updated = api.post(
        f"/downstream/workspaces/{workspace['workspace_id']}/feedback",
        json={"action": "not_right", "reason": "Too much detail"},
    ).json()
    assert updated["profile"]["detail_preference"] == "terse"
    assert updated["profile"]["feedback_events"][-1]["type"] == "not_right"


def test_invalid_feedback_returns_422():
    api = client()
    workspace = api.post("/downstream/workspaces", json={}).json()
    response = api.post(
        f"/downstream/workspaces/{workspace['workspace_id']}/feedback",
        json={"action": "not_right", "reason": ""},
    )
    assert response.status_code == 422


def test_resume_adds_session_without_losing_answers():
    api = client()
    workspace = api.post("/downstream/workspaces", json={}).json()
    workspace = api.post(
        f"/downstream/workspaces/{workspace['workspace_id']}/answer",
        json={"question_id": "access_heavy_rain", "answer": "The lane washes out"},
    ).json()
    resumed = api.post(
        f"/downstream/workspaces/{workspace['workspace_id']}/resume", json={}
    ).json()
    assert len(resumed["sessions"]) == 2
    assert resumed["answers"]["access_heavy_rain"]["answer"] == "The lane washes out"


def test_research_has_sources_and_honest_null_boundary():
    payload = client().get("/downstream/research").json()
    assert len(payload["sources"]) == 4
    assert "unreported" in payload["claim_boundary"]
    assert "never" in payload["claim_boundary"]


def test_proof_is_all_green_and_executable():
    proof = client().get("/downstream/proof").json()
    assert proof["passed"] == proof["total"]
    assert proof["total"] >= 7


def test_conformance_names_code_tests_and_limitations():
    payload = client().get("/downstream/conformance").json()
    assert payload["category"] == "The Collaborative Partner"
    assert all(row["implementation"] and row["test"] for row in payload["rules"])
    assert any("No inundation" in limitation for limitation in payload["limitations"])


def test_openapi_has_no_approval_certification_or_submission_route():
    paths = client().get("/openapi.json").json()["paths"]
    assert not any(
        forbidden in path
        for path in paths
        for forbidden in ("approve", "certify", "submit", "evacuate")
    )
