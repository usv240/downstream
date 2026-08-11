"""HTTP routes for the Downstream collaborative authoring workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from downstream.partner import (
    REQUIREMENTS,
    create_workspace,
    public_view,
    record_answer,
    record_feedback,
    resume,
    skip_question,
)
from downstream.registry import fallback_records, search_high_hazard_unreported
from downstream.safety import DRAFT_DISCLOSURE, SCREENING_DISCLOSURE, mapping_gate
from downstream.store import WorkspaceStore
from spine.verify import Claim, ClaimKind, SourceRef, Verifier

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class AnswerRequest(BaseModel):
    question_id: str = Field(min_length=2, max_length=80)
    answer: str = Field(min_length=1, max_length=1200)
    did_not_understand: bool = False


class SkipRequest(BaseModel):
    question_id: str = Field(min_length=2, max_length=80)


class FeedbackRequest(BaseModel):
    action: str
    reason: str = Field(default="", max_length=500)
    revised_text: str = Field(default="", max_length=1200)


def build_router(store: WorkspaceStore) -> APIRouter:
    router = APIRouter(prefix="/downstream", tags=["downstream"])

    def require(workspace_id: str) -> dict[str, Any]:
        workspace = store.get(workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail=f"no workspace {workspace_id}")
        return workspace


    @router.get("/fixtures/drawing")
    def drawing_fixture() -> dict[str, Any]:
        recording = json.loads(
            (FIXTURES / "cedar_hollow_drawing.recording.json").read_text(encoding="utf-8")
        )
        truth = json.loads(
            (FIXTURES / "cedar_hollow_drawing.truth.json").read_text(encoding="utf-8")
        )
        report = json.loads(
            (FIXTURES / "drawing_accuracy_report.json").read_text(encoding="utf-8")
        )
        return {
            "name": "cedar_hollow_drawing", "synthetic": True,
            "image_url": "/downstream/fixtures/drawing/image",
            "recording": recording, "truth": truth, "accuracy": report,
            "note": "One recorded Vertex AI Gemini 3.5 Flash call, graded against adjacent truth.",
        }

    @router.get("/fixtures/drawing/image")
    def drawing_fixture_image() -> FileResponse:
        return FileResponse(FIXTURES / "cedar_hollow_drawing.png", media_type="image/png")
    @router.get("/research")
    def research() -> dict[str, Any]:
        return {
            "measured_snapshot": {
                "measured_on": "2026-08-11",
                "source": "USACE NID public ArcGIS FeatureServer count queries",
                "total_records": 92606,
                "high_hazard_records": 16972,
                "interpretation": (
                    "High hazard is a consequence classification. It does not describe the "
                    "condition of a dam or predict failure."
                ),
            },
            "sources": [
                {
                    "title": "National Inventory of Dams public service",
                    "url": "https://nid.sec.usace.army.mil/nid/",
                    "use": "Current federal inventory, field definitions, and live records.",
                },
                {
                    "title": "FEMA P-64: Emergency Action Planning for Dams",
                    "url": REQUIREMENTS["purpose"]["url"],
                    "use": "Federal EAP purpose, roles, and plan elements.",
                },
                {
                    "title": "ASDSO Emergency Action Planning",
                    "url": REQUIREMENTS["notification"]["url"],
                    "use": "Owner collaboration, notification flow, and mapping limits.",
                },
                {
                    "title": "Simplified Inundation Maps for Emergency Action Plans",
                    "url": "https://www.damsafety.org/sites/default/files/files/EAPWG%20Final%20SIMS.pdf",
                    "use": "Applicability limits and requirement for regulatory coordination.",
                },
            ],
            "claim_boundary": (
                "A null EAP_PREPARED field is described only as unreported in that public field. "
                "It is never presented as proof that a plan does not exist."
            ),
        }

    @router.get("/nid/search")
    def nid_search(
        limit: int = Query(default=5, ge=1, le=25), state: str | None = Query(default=None)
    ) -> dict[str, Any]:
        try:
            result = search_high_hazard_unreported(limit=limit, state=state)
        except Exception:  # external public endpoint; return an explicit safe fallback
            result = fallback_records()
        return {
            "records": result.records,
            "source_url": result.source_url,
            "live": result.live,
            "interpretation": result.interpretation,
        }

    @router.post("/workspaces")
    def open_workspace() -> dict[str, Any]:
        workspace = create_workspace()
        store.put(workspace)
        return public_view(workspace)

    @router.get("/workspaces/{workspace_id}")
    def get_workspace(workspace_id: str) -> dict[str, Any]:
        return public_view(require(workspace_id))

    @router.post("/workspaces/{workspace_id}/resume")
    def resume_workspace(workspace_id: str) -> dict[str, Any]:
        workspace = resume(require(workspace_id))
        store.put(workspace)
        return public_view(workspace)

    @router.post("/workspaces/{workspace_id}/answer")
    def answer(workspace_id: str, request: AnswerRequest) -> dict[str, Any]:
        workspace = require(workspace_id)
        try:
            record_answer(
                workspace,
                request.question_id,
                request.answer,
                did_not_understand=request.did_not_understand,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        store.put(workspace)
        return public_view(workspace)

    @router.post("/workspaces/{workspace_id}/skip")
    def skip(workspace_id: str, request: SkipRequest) -> dict[str, Any]:
        workspace = require(workspace_id)
        try:
            skip_question(workspace, request.question_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        store.put(workspace)
        return public_view(workspace)

    @router.post("/workspaces/{workspace_id}/feedback")
    def feedback(workspace_id: str, request: FeedbackRequest) -> dict[str, Any]:
        workspace = require(workspace_id)
        try:
            record_feedback(
                workspace,
                request.action,
                reason=request.reason,
                revised_text=request.revised_text,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        store.put(workspace)
        return public_view(workspace)

    @router.get("/proof")
    def proof() -> dict[str, Any]:
        checks: list[dict[str, Any]] = []

        def check(name: str, passed: bool, detail: str = "") -> None:
            checks.append({"check": name, "pass": bool(passed), "detail": detail})

        decision = mapping_gate(
            approved_map_supplied=False,
            method_applicable=False,
            jurisdiction_accepts=False,
            reference_comparison_passed=False,
        )
        check("unvalidated inundation extent fails closed", not decision.may_render_extent)
        check("safe stop carries a next action", bool(decision.next_step))
        check("screening disclosure names what was not generated", "No inundation" in decision.disclosure)

        source = REQUIREMENTS["purpose"]["text"]
        verifier = Verifier({"fema_p64": source})
        empty = verifier.verify(
            Claim(
                id="empty_ref",
                text="The draft is automatically approved.",
                kind=ClaimKind.REGULATORY,
                source_refs=(SourceRef("fema_p64", ""),),
            )
        )
        valid = verifier.verify(
            Claim(
                id="valid_ref",
                text="An EAP identifies emergency conditions and actions.",
                kind=ClaimKind.REGULATORY,
                source_refs=(SourceRef("fema_p64", "identifies potential emergency conditions"),),
            )
        )
        check("empty quotation cannot support a claim", not empty.accepted)
        check("contained quotation supports a bounded claim", valid.accepted)

        workspace = create_workspace()
        meter = public_view(workspace)["context_meter"]
        check("structured context starts within its bound", meter["within_bound"])
        check("all public output is labelled draft", "Draft" in DRAFT_DISCLOSURE)
        passed = sum(row["pass"] for row in checks)
        return {
            "passed": passed,
            "total": len(checks),
            "checks": checks,
            "disclosures": [DRAFT_DISCLOSURE, SCREENING_DISCLOSURE],
        }

    @router.get("/conformance")
    def conformance() -> dict[str, Any]:
        return {
            "category": "The Collaborative Partner",
            "rules": [
                {
                    "rule": "asks clarifying questions and guides step by step",
                    "implementation": "downstream/partner.py: next_question",
                    "test": "tests/test_partner.py::test_questions_are_one_at_a_time_and_not_repeated",
                },
                {
                    "rule": "captures feedback and adapts to the user's way of thinking",
                    "implementation": "downstream/partner.py: record_feedback and profile",
                    "test": "tests/test_partner.py::test_unknown_term_changes_later_language",
                },
                {
                    "rule": "manages state and context across sessions",
                    "implementation": "FirestoreWorkspaceStore plus context_meter",
                    "test": "tests/test_partner.py::test_resume_keeps_facts_and_context_bounded",
                },
                {
                    "rule": "autonomous high-value action over simple chat",
                    "implementation": "structured facts, plan sections, mapping gate, verifier",
                    "test": "tests/test_routes.py::test_end_to_end_partner_flow",
                },
            ],
            "limitations": [
                "The demo authoring fixture is synthetic.",
                "No inundation boundary or evacuation zone is generated.",
                "The draft is not approved, certified, submitted, or engineering advice.",
            ],
        }

    return router
