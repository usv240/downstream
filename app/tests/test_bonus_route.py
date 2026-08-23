from fastapi import FastAPI
from fastapi.testclient import TestClient

from service.routes import build_router
from service.runtime import local_runtime


def test_bonus_route_returns_measured_gemma_privacy_evidence():
    app = FastAPI()
    app.include_router(build_router(local_runtime()))
    payload = TestClient(app).get("/downstream/bonus").json()
    assert payload["model"] == "gemma-4-26b-a4b-it-maas"
    assert payload["measured"]["recall"] == {"found": 4, "expected": 4}
    assert payload["identifiers_leaked_in_replay"] == []
