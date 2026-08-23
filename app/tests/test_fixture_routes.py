from fastapi import FastAPI
from fastapi.testclient import TestClient

from service.routes import build_router
from service.runtime import local_runtime


def api():
    app = FastAPI()
    app.include_router(build_router(local_runtime()))
    return TestClient(app)


def test_recorded_gemini_fixture_is_public_and_graded():
    payload = api().get("/downstream/fixtures/drawing").json()
    assert payload["synthetic"] is True
    assert payload["accuracy"]["model"] == "gemini-3.5-flash"
    assert payload["accuracy"]["correct"] == payload["accuracy"]["total"] == 5


def test_every_recorded_quote_occurs_in_recorded_transcription():
    recording = api().get("/downstream/fixtures/drawing").json()["recording"]
    assert all(fact["quoted_text"] in recording["transcription"] for fact in recording["facts"])


def test_synthetic_drawing_image_is_a_real_png():
    response = api().get("/downstream/fixtures/drawing/image")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.content.startswith(b"\x89PNG")
    assert len(response.content) > 10000
