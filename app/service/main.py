"""Cloud Run entry point for the standalone Downstream submission."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from service.beta_routes import build_beta_router
from service.internal_routes import build_internal_router
from service.routes import build_router
from service.runtime import build_runtime
from spine.api_access import ApiKeyAuthenticator
from spine.config import PINNED_REGION, RegionViolation
from spine.developer_access import KeyIssuer, build_developer_router

REGION = os.environ.get("GOOGLE_CLOUD_REGION", os.environ.get("REGION", PINNED_REGION)).strip()
if REGION and REGION != PINNED_REGION:
    # Data sovereignty is a stated property of this system. A deployment configured outside the
    # pinned region fails to boot rather than quietly contradicting the claim.
    raise RegionViolation(
        f"region is {REGION!r} but every stored resource must be in {PINNED_REGION!r}."
    )

runtime = build_runtime()

app = FastAPI(
    title="Downstream",
    description="A stateful Emergency Action Plan drafting partner with explicit safety gates.",
    version="0.2.0",
)
app.include_router(build_router(runtime))

beta_auth = ApiKeyAuthenticator.from_environment(dynamic_lookup=runtime.api_keys.get)
key_issuer = KeyIssuer.from_environment(
    runtime.api_keys, product="downstream", scope="downstream:use", prefix="ds_beta"
)
app.include_router(build_beta_router(runtime, beta_auth))
app.include_router(
    build_developer_router(
        key_issuer,
        beta_auth,
        product="Downstream",
        scope="downstream:use",
        issuance_quota=runtime.key_issuance_quota,
        attempt_quota=runtime.invitation_attempt_quota,
        policy=runtime.policy,
    )
)
app.include_router(build_internal_router(runtime))

WEB = Path(__file__).resolve().parent.parent / "web"
app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "project": "downstream",
        "google_cloud_project": runtime.project,
        "region": PINNED_REGION,
        "persistence": runtime.persistence,
        "synthetic_demo": True,
        "inundation_extent": "not_generated",
        "beta_api": "configured" if beta_auth.enabled else "not_provisioned",
        # Report the mode itself. Deriving a label from `enabled` here said "invite_only" while
        # /developer/config correctly said "open", which is precisely the kind of drift this
        # project asserts it does not have.
        "developer_key_issuance": key_issuer.mode,
        "model_execution": runtime.drawing.mode,
        "tracing": "cloud_trace" if runtime.tracing_active else "inactive",
        "wake_durability": runtime.wake_durability,
        "scheduled_wakes": "cloud_scheduler_calls_/internal/scan-due",
    }


@app.get("/stack")
def stack() -> dict[str, Any]:
    """What this process is actually using. The live-stack badge renders exactly this."""
    return runtime.stack()


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
