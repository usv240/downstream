"""HTTP routes for the Downstream collaborative authoring workflow."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from downstream import autonomy
from downstream.autonomy import NUDGE_AFTER
from downstream.bonus import gemma_redaction_proof
from downstream.partner import (
    REQUIREMENTS,
    QUESTION_BANK,
    assemble_context,
    context_meter,
    create_workspace,
    next_question,
    outstanding_ids,
    public_view,
    record_answer,
    record_feedback,
    resume,
    revise_answer,
    skip_question,
)
from downstream.registry import fallback_records, search_high_hazard_unreported
from downstream.safety import DRAFT_DISCLOSURE, SCREENING_DISCLOSURE, mapping_gate
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


class RevisionRequest(BaseModel):
    revised_answer: str = Field(min_length=1, max_length=1200)
    reason: str = Field(min_length=2, max_length=500)


def build_router(runtime) -> APIRouter:
    router = APIRouter(prefix="/downstream", tags=["downstream"])
    store = runtime.workspaces

    def require(workspace_id: str) -> dict[str, Any]:
        workspace = store.get(workspace_id)
        if workspace is None or workspace.get("_tenant_id") is not None:
            raise HTTPException(status_code=404, detail=f"no workspace {workspace_id}")
        return workspace

    @router.get("/fixtures/drawing")
    def drawing_fixture() -> dict[str, Any]:
        recording = json.loads(
            (FIXTURES / "cedar_hollow_drawing.recording.json").read_text(
                encoding="utf-8"
            )
        )
        truth = json.loads(
            (FIXTURES / "cedar_hollow_drawing.truth.json").read_text(encoding="utf-8")
        )
        report = json.loads(
            (FIXTURES / "drawing_accuracy_report.json").read_text(encoding="utf-8")
        )
        return {
            "name": "cedar_hollow_drawing",
            "synthetic": True,
            "image_url": "/downstream/fixtures/drawing/image",
            "recording": recording,
            "truth": truth,
            "accuracy": report,
            "note": "One recorded Vertex AI Gemini 3.5 Flash call, graded against adjacent truth.",
        }

    @router.get("/fixtures/drawing/image")
    def drawing_fixture_image() -> FileResponse:
        return FileResponse(
            FIXTURES / "cedar_hollow_drawing.png", media_type="image/png"
        )

    @router.get("/bonus")
    def bonus() -> dict[str, Any]:
        return gemma_redaction_proof()

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
        limit: int = Query(default=5, ge=1, le=25),
        state: str | None = Query(default=None),
    ) -> dict[str, Any]:
        try:
            result = search_high_hazard_unreported(limit=limit, state=state)
        except ValueError as exc:
            # A caller mistake is not a federal outage. Falling through to the fallback here
            # would answer a question the caller did not ask and hide their error.
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception:  # external public endpoint; return an explicit safe fallback
            result = fallback_records()
        return {
            "records": result.records,
            "source_url": result.source_url,
            "live": result.live,
            "interpretation": result.interpretation,
        }

    @router.post("/workspaces")
    def open_workspace(request: Request) -> dict[str, Any]:
        """Open a workspace. The trigger is the only human act in the opening sequence."""
        runtime.public_workspace_quota.enforce_network(
            request,
            "This network has opened its daily allowance of demonstration workspaces. "
            "The allowance resets at UTC midnight.",
        )
        workspace = create_workspace(
            drawing=runtime.drawing.read(),
            scheduler=runtime.scheduler,
            trigger=autonomy.TRIGGER_PUBLIC,
        )
        store.put(workspace)
        return public_view(workspace)

    @router.get("/workspaces/{workspace_id}/autonomy")
    def workspace_autonomy(workspace_id: str) -> dict[str, Any]:
        """The autonomy receipt, derived from the persisted timeline."""
        return autonomy.autonomy_proof(require(workspace_id))

    @router.get("/workspaces/{workspace_id}")
    def get_workspace(workspace_id: str) -> dict[str, Any]:
        return public_view(require(workspace_id))

    @router.get("/workspaces/{workspace_id}/audit")
    def workspace_audit(workspace_id: str) -> dict[str, Any]:
        view = public_view(require(workspace_id))
        return {
            "workspace_id": workspace_id,
            "adaptation": view["adaptation"],
            "evidence_ledger": view["evidence_ledger"],
            "disclosure": view["disclosure"],
        }

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

    @router.post("/workspaces/{workspace_id}/answers/{question_id}/revise")
    def revise(
        workspace_id: str, question_id: str, request: RevisionRequest
    ) -> dict[str, Any]:
        workspace = require(workspace_id)
        try:
            revise_answer(
                workspace, question_id, request.revised_answer, reason=request.reason
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

    DEMO_ANSWERS = {
        "access_heavy_rain": "The gravel lane off Cedar Hollow Road is the only way up, and it "
        "washes out at the second bend in heavy rain.",
        "emergency_manager": "Example County emergency management, duty desk, reachable "
        "after hours through the synthetic non-emergency line.",
        "downstream_people": "A seasonal campground sits below the spillway from May to "
        "September and does not appear on any public parcel layer.",
        "spillway_history": "Water topped the overflow channel in the 1998 storm and cut a "
        "gully on the left abutment.",
        "equipment": "A neighbouring farm keeps a tracked excavator about forty minutes away.",
        "resolve_dam_height_conflict": "Our insurance file uses 28 feet. The drawing has not "
        "been checked since 1958, so the state engineer should confirm it.",
    }

    @router.post("/demo/run")
    def demo_run(request: Request) -> dict[str, Any]:
        """One request. Server-side. Trigger to reviewable draft, with nothing to click.

        A judge should not have to perform eleven interactions to find out whether the workflow
        works. This runs the whole thing in one call and returns the receipt, the draft, and the
        measured context so the result can be checked rather than watched.

        The owner answers here are synthetic and labelled as such. They stand in for the one
        thing the agent is not allowed to invent, so that everything the agent *is* allowed to do
        can be seen end to end.
        """
        runtime.public_workspace_quota.enforce_network(
            request,
            "This network has opened its daily allowance of demonstration workspaces. "
            "The allowance resets at UTC midnight.",
        )
        started = time.perf_counter()
        workspace = create_workspace(
            drawing=runtime.drawing.read(),
            scheduler=runtime.scheduler,
            trigger=autonomy.TRIGGER_PUBLIC,
        )

        # Answer the owner questions as they come, one at a time, in the order the agent asks.
        # Nothing is answered that the agent did not raise.
        asked: list[str] = []
        while True:
            question = next_question(workspace)
            if question is None:
                break
            reply = DEMO_ANSWERS.get(question["id"])
            if reply is None:
                break
            asked.append(question["id"])
            record_answer(workspace, question["id"], reply)

        # One correction, to show the work product changing under feedback.
        revise_answer(
            workspace,
            "access_heavy_rain",
            "The east lane washes out at the second bend.",
            reason="Owner corrected the access location.",
        )

        # Fire the scheduled follow-ups now instead of waiting a week for them to come due.
        # The wake rows, the compare-and-swap claim, the handler and the completion are the
        # production ones; only the clock reading is moved forward, and the response says so.
        rehearsal = runtime.scheduler_at_offset(NUDGE_AFTER.total_seconds() + 60)
        fired: list[str] = []
        for wake_id in workspace.get("wakes", []):
            done = rehearsal.dispatch_wake(
                wake_id,
                lambda wake: autonomy.advance_on_wake(
                    workspace, wake.kind, outstanding=outstanding_ids(workspace)
                ),
            )
            if done is not None:
                fired.append(done.kind)

        workspace["outstanding"] = outstanding_ids(workspace)
        store.put(workspace)
        view = public_view(workspace)
        return {
            "workspace_id": workspace["workspace_id"],
            "resume_url": f"/?workspace={workspace['workspace_id']}",
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "questions_asked_by_the_agent": asked,
            "scheduled_actions_fired": fired,
            "clock": "simulated for this rehearsal; production wakes run on Cloud Scheduler",
            "autonomy_proof": view["autonomy_proof"],
            "context_meter": view["context_meter"],
            "plan": view["plan"],
            "evidence_ledger": view["evidence_ledger"],
            "mapping": view["mapping"],
            "disclosure": [DRAFT_DISCLOSURE, SCREENING_DISCLOSURE],
            "synthetic_owner_answers": True,
        }

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
        check(
            "unvalidated inundation extent fails closed", not decision.may_render_extent
        )
        check("safe stop carries a next action", bool(decision.next_step))
        check(
            "screening disclosure names what was not generated",
            "No inundation" in decision.disclosure,
        )

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
                source_refs=(
                    SourceRef("fema_p64", "identifies potential emergency conditions"),
                ),
            )
        )
        check("empty quotation cannot support a claim", not empty.accepted)
        check("contained quotation supports a bounded claim", valid.accepted)

        workspace = create_workspace()
        meter = public_view(workspace)["context_meter"]
        check("structured context starts within its bound", meter["within_bound"])
        check("all public output is labelled draft", "Draft" in DRAFT_DISCLOSURE)
        for index, question in enumerate(QUESTION_BANK):
            record_answer(workspace, question["id"], f"Owner fact {index + 1}")
        conflict_question = next_question(workspace)
        check(
            "source conflict creates a targeted clarification",
            conflict_question is not None
            and conflict_question.get("basis") == "unresolved_source_conflict",
        )
        record_answer(
            workspace,
            conflict_question["id"],
            "Use 31 feet only after the engineer confirms the legacy drawing.",
        )
        revise_answer(
            workspace,
            "access_heavy_rain",
            "The east lane washes out at the second bend.",
            reason="Owner corrected the access location.",
        )
        adapted = public_view(workspace)
        check(
            "owner correction changes the draft with history",
            adapted["adaptation"]["answer_revisions"] == 1,
        )
        check(
            "every rendered section exposes its evidence class",
            all(row["rendered_from_evidence"] for row in adapted["evidence_ledger"]),
        )

        # The autonomy receipt must be derived from what happened, not from a description.
        receipt = adapted["autonomy_proof"]
        check(
            "the run records more automatic steps than authority steps",
            receipt["automatic_agent_steps"] > receipt["human_authority_steps"],
        )
        check(
            "no system decision is taken over reserved authority",
            receipt["system_decisions_over_reserved_authority"] == 0
            and len(receipt["authority_reserved"]) == len(autonomy.RESERVED_AUTHORITY),
        )
        check(
            "the source conflict is derived from the sources, not hardcoded",
            any(step["step"] == "source_conflict_detected" for step in receipt["timeline"]),
        )
        agreeing = create_workspace(
            facts=[
                {
                    "key": "dam_height_ft",
                    "value": 28,
                    "quoted_text": "MAX. EMBANKMENT HT. 28 FT",
                    "confidence": 0.9,
                    "provenance": "recorded_gemini_drawing_extraction",
                }
            ]
        )
        check(
            "a drawing that agrees with the registry raises no conflict question",
            not any(fact.get("status") == "conflict" for fact in agreeing["facts"]),
        )

        # The context meter has to be capable of reporting failure, or it proves nothing.
        loaded = create_workspace()
        record_answer(loaded, "access_heavy_rain", "detail " * 400)
        check(
            "the context meter can report a budget breach",
            not context_meter(loaded)["within_bound"],
        )
        empty_sessions = create_workspace()
        first = context_meter(empty_sessions)["structured_context_tokens"]
        for _ in range(10):
            resume(empty_sessions)
        check(
            "measured context does not grow with empty sessions",
            context_meter(empty_sessions)["structured_context_tokens"] == first,
        )

        # Identifiers in an owner answer must not reach the model boundary.
        shielded = create_workspace()
        record_answer(
            shielded, "emergency_manager", "Call the duty desk on 555-318-2299 or duty@example.gov."
        )
        boundary = assemble_context(shielded)
        check(
            "owner identifiers do not cross the model boundary",
            "555-318-2299" not in boundary and "duty@example.gov" not in boundary,
        )
        check(
            "the owner keeps the verbatim answer in their own workspace",
            "555-318-2299" in shielded["answers"]["emergency_manager"]["answer"],
        )

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
                    "rule": "turns conflicting retrieved facts into targeted clarification",
                    "implementation": "downstream/collaboration.py: questions_for",
                    "test": "tests/test_collaboration.py::test_source_conflict_becomes_a_targeted_question",
                },
                {
                    "rule": "owner corrections mutate the draft and preserve revision history",
                    "implementation": "downstream/partner.py: revise_answer",
                    "test": "tests/test_collaboration.py::test_revision_changes_plan_and_keeps_history",
                },
                {
                    "rule": "manages state and context across sessions",
                    "implementation": "FirestoreWorkspaceStore plus context_meter",
                    "test": "tests/test_partner.py::test_resume_keeps_facts_and_context_bounded",
                },
                {
                    "rule": "autonomous high-value action over simple chat",
                    "implementation": "downstream/autonomy.py: open_run and autonomy_proof",
                    "test": "tests/test_autonomy.py::test_opening_a_workspace_runs_a_sequence_with_no_human_step",
                },
                {
                    "rule": "asynchronous background execution over long timelines",
                    "implementation": "spine/wake.py plus service/internal_routes.py: /internal/scan-due",
                    "test": "tests/test_internal_routes.py::test_a_due_wake_is_dispatched_and_changes_the_stored_workspace",
                },
                {
                    "rule": "the whole workflow is demonstrable in one request",
                    "implementation": "service/routes.py: /downstream/demo/run",
                    "test": "tests/test_demo_run.py::test_one_request_reaches_a_reviewable_draft",
                },
                {
                    "rule": "identifiers are pseudonymised before any model boundary",
                    "implementation": "downstream/partner.py: shield, over spine/redact.py",
                    "test": "tests/test_redact.py::test_all_identifier_kinds_are_removed",
                },
                {
                    "rule": "untrusted document text cannot issue instructions",
                    "implementation": "downstream/live_model.py over spine/untrusted.py",
                    "test": "tests/test_live_model.py::test_an_instruction_shaped_span_cannot_ground_a_fact",
                },
                {
                    "rule": "public writes and key issuance carry abuse ceilings",
                    "implementation": "spine/quota.py, applied in routes and developer access",
                    "test": "tests/test_demo_run.py::test_the_public_route_is_capped_per_network",
                },
                {
                    "rule": "the page reports the stack the process actually has",
                    "implementation": "service/runtime.py: Runtime.stack, served at /stack",
                    "test": "tests/test_live_stack.py::test_the_badge_hardcodes_no_service_names_at_all",
                },
            ],
            "limitations": [
                "The demo authoring fixture and its owner answers are synthetic.",
                "Gemma runs from a graded recording, never live.",
                "The one-request rehearsal moves a simulated clock so a wake due in three days "
                "can fire inside it. The wake, claim, handler and completion are the production "
                "ones; only the clock reading changes.",
                "No inundation boundary or evacuation zone is generated.",
                "The draft is not approved, certified, submitted, or engineering advice.",
            ],
        }

    return router
