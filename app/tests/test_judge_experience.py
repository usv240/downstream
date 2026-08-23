from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from downstream.partner import (
    QUESTION_BANK,
    create_workspace,
    next_question,
    record_answer,
    resume,
    skip_question,
)
from service.main import app as public_app
from service.routes import build_router
from service.runtime import local_runtime


WEB = Path(__file__).resolve().parents[1] / "web"


def _reach_conflict(workspace):
    for question in QUESTION_BANK:
        record_answer(workspace, question["id"], "Synthetic owner answer")
    assert next_question(workspace)["id"] == "resolve_dam_height_conflict"


def test_dynamic_conflict_can_be_held_and_reopened_in_a_new_session():
    workspace = create_workspace()
    _reach_conflict(workspace)
    skip_question(workspace, "resolve_dam_height_conflict")

    assert next_question(workspace) is None
    assert len(workspace["answers"]) == 5

    resume(workspace)

    assert workspace["skipped"] == []
    assert next_question(workspace)["id"] == "resolve_dam_height_conflict"
    assert workspace["sessions"][-1]["reopened_questions"] == [
        "resolve_dam_height_conflict"
    ]
    assert len(workspace["answers"]) == 5


def test_http_skip_and_resume_return_the_dynamic_conflict():
    api_app = FastAPI()
    api_app.include_router(build_router(local_runtime()))
    api = TestClient(api_app)
    workspace = api.post("/downstream/workspaces", json={}).json()
    workspace_id = workspace["workspace_id"]

    for _ in range(5):
        question = workspace["next_question"]
        workspace = api.post(
            f"/downstream/workspaces/{workspace_id}/answer",
            json={"question_id": question["id"], "answer": "Synthetic owner answer"},
        ).json()

    held = api.post(
        f"/downstream/workspaces/{workspace_id}/skip",
        json={"question_id": "resolve_dam_height_conflict"},
    )
    assert held.status_code == 200
    assert held.json()["next_question"] is None

    reopened = api.post(f"/downstream/workspaces/{workspace_id}/resume", json={}).json()
    assert reopened["next_question"]["id"] == "resolve_dam_height_conflict"


def test_product_has_guided_entry_resume_identity_and_dedicated_status_region():
    html = (WEB / "downstream.html").read_text(encoding="utf-8")
    for marker in (
        "/?guided=1#workspace",
        'id="app-status"',
        'id="workspace-identity"',
        'id="resume-url"',
        'id="copy-resume"',
    ):
        assert marker in html
    assert 'class="partner-shell" aria-live=' not in html


def test_frontend_handles_actions_inline_and_manages_dynamic_focus():
    script = (WEB / "downstream-v2.js").read_text(encoding="utf-8")
    for behavior in (
        "Use synthetic example",
        "Question held",
        "workspaceLink",
        "runAction",
        "aria-invalid",
        "current-question-heading",
        "requestAnimationFrame",
    ):
        assert behavior in script
    assert "alert(" not in script


def test_evidence_dashboard_presents_all_public_proof_surfaces():
    html = (WEB / "downstream-evidence.html").read_text(encoding="utf-8")
    script = (WEB / "downstream-evidence.js").read_text(encoding="utf-8")
    for marker in ("proof-score", "conformance-grid", "drawing-score", "gemma-score"):
        assert marker in html
    for endpoint in (
        "/downstream/proof",
        "/downstream/conformance",
        "/downstream/fixtures/drawing",
        "/downstream/bonus",
    ):
        assert endpoint in script


def test_human_readable_evidence_route_is_public():
    response = TestClient(public_app).get("/evidence")
    assert response.status_code == 200
    assert "Evidence dashboard" in response.text
