"""Authenticated, tenant-scoped API for real Downstream collaboration workspaces."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from downstream import autonomy
from downstream.partner import (
    create_workspace,
    outstanding_ids,
    public_view,
    record_answer,
    record_feedback,
    resume,
    revise_answer,
    skip_question,
)
from downstream.registry import lookup_nid_record
from downstream.store import ScopedWorkspaceStore
from service.routes import AnswerRequest, FeedbackRequest, RevisionRequest, SkipRequest
from spine.api_access import ApiKeyAuthenticator, ApiPrincipal, require_scope


class OpenBetaWorkspaceRequest(BaseModel):
    nid_id: str = Field(min_length=2, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")


def _dam_from_nid(record: dict[str, Any], source_url: str) -> dict[str, Any]:
    return {
        "nid_id": record.get("NIDID"),
        "name": record.get("NAME"),
        "state": record.get("STATE"),
        "county": record.get("COUNTYSTATE"),
        "hazard_potential": record.get("HAZARD_POTENTIAL"),
        "eap_status": record.get("EAP_PREPARED"),
        "year_completed": record.get("YEAR_COMPLETED"),
        "dam_height_ft": record.get("DAM_HEIGHT"),
        "owner_type": record.get("PRIMARY_OWNER_TYPE"),
        "latitude": record.get("LATITUDE"),
        "longitude": record.get("LONGITUDE"),
        "synthetic": False,
        "source": {"name": "USACE National Inventory of Dams", "url": source_url},
    }


def build_beta_router(runtime, auth: ApiKeyAuthenticator) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["beta-api"])
    store = runtime.workspaces

    def scoped(principal: ApiPrincipal, response: Response | None = None) -> ScopedWorkspaceStore:
        require_scope(principal, "downstream:use")
        # Every authenticated call is metered against the key that made it, so one holder of a
        # temporary key cannot spend the whole service's budget. The remaining allowance is
        # returned on every response, so a caller can see the budget without guessing at it.
        verdict = runtime.api_call_quota.enforce(
            principal.key_digest,
            "This API key has used its daily allowance. It resets at UTC midnight.",
        )
        if response is not None:
            response.headers.update(verdict.headers())
        return ScopedWorkspaceStore(store, principal.tenant_id)

    def require(
        workspace_id: str, principal: ApiPrincipal, response: Response | None = None
    ) -> tuple[ScopedWorkspaceStore, dict[str, Any]]:
        owned = scoped(principal, response)
        workspace = owned.get(workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail=f"no workspace {workspace_id}")
        return owned, workspace

    @router.get("")
    def api_info(
        response: Response, principal: ApiPrincipal = Depends(auth)
    ) -> dict[str, Any]:
        require_scope(principal, "downstream:use")
        response.headers.update(
            runtime.api_call_quota.check(principal.key_digest).headers()
        )
        return {
            "quotas": runtime.policy.as_public_dict(),
            "product": "Downstream",
            "api_version": "v1",
            "tenant": principal.tenant_id,
            "key_id": principal.key_id,
            "input": "One live public USACE NID record plus owner-provided answers.",
            "boundary": (
                "Drafting only. No inundation extent, certification, approval, or submission."
            ),
        }

    @router.post("/workspaces", status_code=201)
    def open_workspace(
        request: OpenBetaWorkspaceRequest,
        response: Response,
        principal: ApiPrincipal = Depends(auth),
    ) -> dict[str, Any]:
        try:
            result = lookup_nid_record(request.nid_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail="The public NID service is unavailable."
            ) from exc
        if not result.records:
            raise HTTPException(status_code=404, detail=f"no public NID record {request.nid_id}")
        owned = scoped(principal, response)
        workspace = create_workspace(
            dam=_dam_from_nid(result.records[0], result.source_url),
            drawing=runtime.drawing.read(),
            registry_source={"url": result.source_url, "live": result.live},
            scheduler=runtime.scheduler,
            trigger=autonomy.TRIGGER_API,
        )
        workspace["outstanding"] = outstanding_ids(workspace)
        owned.put(workspace)
        return public_view(workspace)

    @router.get("/workspaces/{workspace_id}/autonomy")
    def workspace_autonomy(
        workspace_id: str, response: Response, principal: ApiPrincipal = Depends(auth)
    ) -> dict[str, Any]:
        return autonomy.autonomy_proof(require(workspace_id, principal, response)[1])

    @router.get("/workspaces/{workspace_id}")
    def get_workspace(
        workspace_id: str, response: Response, principal: ApiPrincipal = Depends(auth)
    ) -> dict[str, Any]:
        return public_view(require(workspace_id, principal, response)[1])

    @router.post("/workspaces/{workspace_id}/answer")
    def answer(
        workspace_id: str,
        request: AnswerRequest,
        response: Response,
        principal: ApiPrincipal = Depends(auth),
    ) -> dict[str, Any]:
        owned, workspace = require(workspace_id, principal, response)
        try:
            record_answer(
                workspace,
                request.question_id,
                request.answer,
                did_not_understand=request.did_not_understand,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        owned.put(workspace)
        return public_view(workspace)

    @router.post("/workspaces/{workspace_id}/answers/{question_id}/revise")
    def revise(
        workspace_id: str,
        question_id: str,
        request: RevisionRequest,
        response: Response,
        principal: ApiPrincipal = Depends(auth),
    ) -> dict[str, Any]:
        owned, workspace = require(workspace_id, principal, response)
        try:
            revise_answer(
                workspace, question_id, request.revised_answer, reason=request.reason
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        owned.put(workspace)
        return public_view(workspace)

    @router.post("/workspaces/{workspace_id}/skip")
    def skip(
        workspace_id: str,
        request: SkipRequest,
        response: Response,
        principal: ApiPrincipal = Depends(auth),
    ) -> dict[str, Any]:
        owned, workspace = require(workspace_id, principal, response)
        try:
            skip_question(workspace, request.question_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        owned.put(workspace)
        return public_view(workspace)

    @router.post("/workspaces/{workspace_id}/feedback")
    def feedback(
        workspace_id: str,
        request: FeedbackRequest,
        response: Response,
        principal: ApiPrincipal = Depends(auth),
    ) -> dict[str, Any]:
        owned, workspace = require(workspace_id, principal, response)
        try:
            record_feedback(
                workspace,
                request.action,
                reason=request.reason,
                revised_text=request.revised_text,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        owned.put(workspace)
        return public_view(workspace)

    @router.post("/workspaces/{workspace_id}/resume")
    def resume_workspace(
        workspace_id: str, response: Response, principal: ApiPrincipal = Depends(auth)
    ) -> dict[str, Any]:
        owned, workspace = require(workspace_id, principal, response)
        resume(workspace)
        owned.put(workspace)
        return public_view(workspace)

    return router
