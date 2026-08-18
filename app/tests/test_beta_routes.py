from fastapi import FastAPI
from fastapi.testclient import TestClient

from downstream.registry import NIDResult
from downstream.store import MemoryWorkspaceStore
from service.beta_routes import build_beta_router
from service.routes import build_router
from spine.api_access import ApiKeyAuthenticator


RECORD = {
    "NIDID": "IA00001",
    "NAME": "Example Dam",
    "STATE": "Iowa",
    "COUNTYSTATE": "Example County, Iowa",
    "DAM_HEIGHT": 22,
    "YEAR_COMPLETED": 1963,
    "HAZARD_POTENTIAL": "High",
    "EAP_PREPARED": None,
    "PRIMARY_OWNER_TYPE": "Private",
    "LATITUDE": 41.1,
    "LONGITUDE": -93.2,
}


def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(
        "service.beta_routes.lookup_nid_record",
        lambda nid_id: NIDResult([RECORD], "https://example.test/nid", True, "public"),
    )
    store = MemoryWorkspaceStore()
    auth = ApiKeyAuthenticator.from_plaintext({
        "owner-one-key": {
            "tenant_id": "owner_one",
            "label": "Owner one",
            "scopes": ["downstream:use"],
        },
        "owner-two-key": {
            "tenant_id": "owner_two",
            "label": "Owner two",
            "scopes": ["downstream:use"],
        },
    })
    app = FastAPI()
    app.include_router(build_router(store))
    app.include_router(build_beta_router(store, auth))
    return TestClient(app)


def test_beta_opens_real_record_workspace_and_keeps_demo_public(monkeypatch):
    api = client(monkeypatch)
    assert api.post("/downstream/workspaces", json={}).status_code == 200
    response = api.post(
        "/v1/workspaces",
        headers={"X-API-Key": "owner-one-key"},
        json={"nid_id": "IA00001"},
    )
    assert response.status_code == 201
    assert response.json()["dam"]["synthetic"] is False
    assert response.json()["dam"]["source"]["name"] == "USACE National Inventory of Dams"


def test_beta_workspace_cannot_be_read_by_another_tenant(monkeypatch):
    api = client(monkeypatch)
    opened = api.post(
        "/v1/workspaces",
        headers={"X-API-Key": "owner-one-key"},
        json={"nid_id": "IA00001"},
    ).json()
    assert api.get(
        f"/v1/workspaces/{opened['workspace_id']}",
        headers={"X-API-Key": "owner-one-key"},
    ).status_code == 200
    assert api.get(
        f"/v1/workspaces/{opened['workspace_id']}",
        headers={"X-API-Key": "owner-two-key"},
    ).status_code == 404
    assert api.get(f"/downstream/workspaces/{opened['workspace_id']}").status_code == 404



def test_tenant_cannot_be_selected_in_request_body(monkeypatch):
    api = client(monkeypatch)
    response = api.post(
        "/v1/workspaces",
        headers={"X-API-Key": "owner-one-key"},
        json={"nid_id": "IA00001", "tenant_id": "owner_two"},
    )
    assert response.status_code == 201
    workspace_id = response.json()["workspace_id"]
    assert api.get(
        f"/v1/workspaces/{workspace_id}",
        headers={"X-API-Key": "owner-two-key"},
    ).status_code == 404


def test_beta_answer_updates_only_owned_workspace(monkeypatch):
    api = client(monkeypatch)
    opened = api.post(
        "/v1/workspaces",
        headers={"X-API-Key": "owner-one-key"},
        json={"nid_id": "IA00001"},
    ).json()
    question = opened["next_question"]
    updated = api.post(
        f"/v1/workspaces/{opened['workspace_id']}/answer",
        headers={"X-API-Key": "owner-one-key"},
        json={"question_id": question["id"], "answer": "The east road remains passable."},
    )
    assert updated.status_code == 200
    assert question["id"] in updated.json()["answers"]
