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
from service.beta_routes import build_beta_router
from spine.api_access import ApiKeyAuthenticator
from spine.api_key_store import FirestoreApiKeyStore, MemoryApiKeyStore
from spine.developer_access import KeyIssuer, build_developer_router

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "local")
USE_FIRESTORE = os.environ.get("USE_FIRESTORE", "").lower() in {"1", "true", "yes"}

if USE_FIRESTORE:
    from google.cloud import firestore

    firestore_client = firestore.Client(project=PROJECT)
    workspace_store = FirestoreWorkspaceStore(firestore_client)
    developer_key_store = FirestoreApiKeyStore(firestore_client, "downstream")
    persistence = "firestore"
else:
    workspace_store = MemoryWorkspaceStore()
    developer_key_store = MemoryApiKeyStore("downstream")
    persistence = "memory-local"

app = FastAPI(
    title="Downstream",
    description="A stateful Emergency Action Plan drafting partner with explicit safety gates.",
    version="0.1.0",
)
app.include_router(build_router(workspace_store))
beta_auth = ApiKeyAuthenticator.from_environment(dynamic_lookup=developer_key_store.get)
key_issuer = KeyIssuer.from_environment(
    developer_key_store, product="downstream", scope="downstream:use", prefix="ds_beta"
)
app.include_router(build_beta_router(workspace_store, beta_auth))
app.include_router(build_developer_router(
    key_issuer, beta_auth, product="Downstream", scope="downstream:use"
))

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
        "beta_api": "configured" if beta_auth.enabled else "not_provisioned",
        "developer_key_issuance": "invite_only" if key_issuer.enabled else "disabled",
    }


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB / "downstream.html")


@app.get("/judges", include_in_schema=False)
def judges() -> FileResponse:
    return FileResponse(WEB / "downstream-judges-v2.html")


@app.get("/developer", include_in_schema=False)
def developer() -> FileResponse:
    return FileResponse(WEB / "developer.html")


@app.get("/evidence", include_in_schema=False)
def evidence() -> FileResponse:
    return FileResponse(WEB / "downstream-evidence.html")
