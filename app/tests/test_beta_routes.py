from fastapi import FastAPI
from fastapi.testclient import TestClient

from downstream.registry import NIDResult
from downstream.store import MemoryWorkspaceStore
from service.beta_routes import build_beta_router
from service.routes import build_router
from service.runtime import local_runtime
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
    runtime = local_runtime(MemoryWorkspaceStore())
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
    app.include_router(build_router(runtime))
    app.include_router(build_beta_router(runtime, auth))
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


def test_every_authenticated_response_shows_the_remaining_budget(monkeypatch):
    """A caller should never have to guess how much allowance is left."""
    api = client(monkeypatch)
    headers = {"X-API-Key": "owner-one-key"}
    info = api.get("/v1", headers=headers)
    assert info.headers["x-ratelimit-limit"]
    assert int(info.headers["x-ratelimit-remaining"]) >= 0
    assert info.headers["x-ratelimit-reset"]

    created = api.post("/v1/workspaces", json={"nid_id": "IA00001"}, headers=headers)
    assert created.status_code == 201
    assert created.headers["x-ratelimit-limit"]

    workspace_id = created.json()["workspace_id"]
    fetched = api.get(f"/v1/workspaces/{workspace_id}", headers=headers)
    assert fetched.headers["x-ratelimit-limit"]


def test_the_remaining_budget_counts_down_as_calls_are_made(monkeypatch):
    api = client(monkeypatch)
    headers = {"X-API-Key": "owner-one-key"}
    first = int(api.get("/v1", headers=headers).headers["x-ratelimit-remaining"])
    api.get("/v1", headers=headers)
    third = int(api.get("/v1", headers=headers).headers["x-ratelimit-remaining"])
    assert third < first


def test_the_autonomy_receipt_is_reachable_over_the_api(monkeypatch):
    api = client(monkeypatch)
    headers = {"X-API-Key": "owner-one-key"}
    workspace_id = api.post(
        "/v1/workspaces", json={"nid_id": "IA00001"}, headers=headers
    ).json()["workspace_id"]
    receipt = api.get(f"/v1/workspaces/{workspace_id}/autonomy", headers=headers)
    assert receipt.status_code == 200
    body = receipt.json()
    assert body["trigger"] == "approved_api_client_supplied_an_nid_identifier"
    assert body["continue_clicks_required"] == 0
    assert body["automatic_agent_steps"] > 0


def test_another_tenant_cannot_read_the_autonomy_receipt(monkeypatch):
    api = client(monkeypatch)
    workspace_id = api.post(
        "/v1/workspaces", json={"nid_id": "IA00001"}, headers={"X-API-Key": "owner-one-key"}
    ).json()["workspace_id"]
    assert api.get(
        f"/v1/workspaces/{workspace_id}/autonomy", headers={"X-API-Key": "owner-two-key"}
    ).status_code == 404
