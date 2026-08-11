"""Cloud Run entry point for the standalone Downstream submission."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from downstream.store import FirestoreWorkspaceStore, MemoryWorkspaceStore
from service.routes import build_router

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "local")
USE_FIRESTORE = os.environ.get("USE_FIRESTORE", "").lower() in {"1", "true", "yes"}

if USE_FIRESTORE:
    from google.cloud import firestore

    workspace_store = FirestoreWorkspaceStore(firestore.Client(project=PROJECT))
    persistence = "firestore"
else:
    workspace_store = MemoryWorkspaceStore()
    persistence = "memory-local"

app = FastAPI(
    title="Downstream",
    description="A stateful Emergency Action Plan drafting partner with explicit safety gates.",
    version="0.1.0",
)
app.include_router(build_router(workspace_store))

WEB = Path(__file__).resolve().parent.parent / "web"
app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "project": "downstream",
        "google_cloud_project": PROJECT,
        "persistence": persistence,
        "synthetic_demo": True,
        "inundation_extent": "not_generated",
    }


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB / "downstream.html")


@app.get("/judges", include_in_schema=False)
def judges() -> FileResponse:
    return FileResponse(WEB / "downstream-judges.html")
