from fastapi import FastAPI
from fastapi.testclient import TestClient

from service.routes import build_router
from service.runtime import local_runtime


def client():
    app = FastAPI()
    app.include_router(build_router(local_runtime()))
    return TestClient(app)


def test_revision_route_changes_rendered_section_and_exposes_history():
    api = client()
    workspace = api.post("/downstream/workspaces", json={}).json()
    workspace_id = workspace["workspace_id"]
    api.post(
        f"/downstream/workspaces/{workspace_id}/answer",
        json={
            "question_id": "access_heavy_rain",
            "answer": "The west lane is reliable.",
        },
    )

    revised = api.post(
        f"/downstream/workspaces/{workspace_id}/answers/access_heavy_rain/revise",
        json={
            "revised_answer": "The east lane washes out at the second bend.",
            "reason": "Owner corrected the access road.",
        },
    )

    assert revised.status_code == 200
    payload = revised.json()
    section = next(row for row in payload["plan"] if row["key"] == "preparedness")
    assert section["text"] == "The east lane washes out at the second bend."
    assert payload["answers"]["access_heavy_rain"]["version"] == 2
    assert len(payload["answers"]["access_heavy_rain"]["history"]) == 2
    assert payload["adaptation"]["answer_revisions"] == 1


def test_revision_of_unanswered_question_is_rejected_without_mutation():
    api = client()
    workspace = api.post("/downstream/workspaces", json={}).json()
    response = api.post(
        f"/downstream/workspaces/{workspace['workspace_id']}/answers/emergency_manager/revise",
        json={"revised_answer": "Call Jordan Lee", "reason": "Correction"},
    )
    assert response.status_code == 422
    fetched = api.get(f"/downstream/workspaces/{workspace['workspace_id']}").json()
    assert "emergency_manager" not in fetched["answers"]


def test_skip_route_records_gap_and_advances_once():
    api = client()
    workspace = api.post("/downstream/workspaces", json={}).json()
    response = api.post(
        f"/downstream/workspaces/{workspace['workspace_id']}/skip",
        json={"question_id": "access_heavy_rain"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["skipped"] == ["access_heavy_rain"]
    assert payload["next_question"]["id"] == "emergency_manager"


def test_audit_route_proves_adaptation_and_section_provenance():
    api = client()
    workspace = api.post("/downstream/workspaces", json={}).json()
    workspace_id = workspace["workspace_id"]
    api.post(
        f"/downstream/workspaces/{workspace_id}/answer",
        json={
            "question_id": "emergency_manager",
            "answer": "Call Jordan Lee after hours.",
        },
    )

    audit = api.get(f"/downstream/workspaces/{workspace_id}/audit")
    assert audit.status_code == 200
    payload = audit.json()
    notification = next(
        row for row in payload["evidence_ledger"] if row["section"] == "notification"
    )
    assert {item["kind"] for item in notification["evidence"]} == {
        "owner_answer",
        "published_requirement",
    }
    assert payload["adaptation"]["sessions_remembered"] == 1
    assert "not approved" in payload["disclosure"]
