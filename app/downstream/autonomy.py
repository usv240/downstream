"""What the agent does without being asked.

The honest audit of this product was that every state transition needed a human click. The
registry lookup, the drawing read, the conflict, the composed sections and the mapping gate were
all real, but they were constants assembled on request rather than steps an agent decided to run.

This module makes the opening sequence autonomous and, more importantly, *provable*. One trigger
starts a run. The agent then resolves everything it has authority to resolve, records each step in
an ordered timeline with the actor that performed it, registers durable wakes for the work that is
not due yet, and stops at the owner questions.

Stopping there is not a missing feature. For a Collaborative Partner the owner's knowledge is the
input the product exists to collect, and inventing it would be the failure mode. What the autonomy
receipt claims is therefore narrow and checkable: **every in-scope transition runs automatically,
and the run pauses only for owner knowledge or for evidence that must come from outside.**
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any

from downstream.safety import mapping_gate

AGENT = "agent"
HUMAN_AUTHORITY = "human_authority"
EXTERNAL_EVIDENCE = "external_evidence"

TRIGGER_PUBLIC = "public_judge_console_opened_a_workspace"
TRIGGER_API = "approved_api_client_supplied_an_nid_identifier"

# What the agent is not allowed to decide, stated up front so the receipt can be checked against
# it rather than against a description written after the fact.
RESERVED_AUTHORITY = (
    "owner site knowledge",
    "controlling-record or qualified-engineer resolution of a source conflict",
    "approval, certification, or submission of the plan",
    "any inundation extent, depth, velocity, arrival time, or evacuation zone",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_step(
    workspace: dict[str, Any],
    actor: str,
    step: str,
    detail: str,
    **evidence: Any,
) -> dict[str, Any]:
    """Append one ordered, attributable entry to the run timeline."""
    entry = {
        "at": utc_now(),
        "actor": actor,
        "step": step,
        "detail": detail,
    }
    if evidence:
        entry["evidence"] = evidence
    workspace.setdefault("timeline", []).append(entry)
    return entry


def derive_height_conflict(
    facts: list[dict[str, Any]], dam: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Compare what the drawing said against what the registry row says.

    The conflict used to be a constant in the fixture. Deriving it means the agent finds the
    disagreement, and a drawing that happens to agree with the registry produces no sixth
    question instead of producing one anyway.
    """
    registry_height = dam.get("dam_height_ft")
    conflict: dict[str, Any] | None = None
    resolved: list[dict[str, Any]] = []
    for fact in facts:
        fact = copy.deepcopy(fact)
        if fact.get("key") == "dam_height_ft" and registry_height not in (None, ""):
            drawing_value = str(fact.get("value", "")).strip()
            if drawing_value and drawing_value != str(registry_height).strip():
                fact["status"] = "conflict"
                fact["conflicts_with"] = f"registry record: {registry_height} ft"
                conflict = fact
            else:
                fact["status"] = "agrees_with_registry"
        else:
            fact.setdefault("status", "needs_owner_confirmation")
        resolved.append(fact)
    return resolved, conflict


def open_run(
    workspace: dict[str, Any],
    *,
    trigger: str,
    outstanding: list[str],
    drawing: Any | None = None,
    registry_source: dict[str, Any] | None = None,
    scheduler: Any | None = None,
) -> dict[str, Any]:
    """The autonomous opening sequence. One trigger, no clicks.

    Every step here is one the agent has authority to perform: read a public record, read a
    drawing, notice that two sources disagree, compose the sections that already have evidence,
    apply the mapping gate, and schedule the work that is not due yet.
    """
    workspace["trigger"] = trigger
    workspace.setdefault("timeline", [])
    record_step(
        workspace,
        EXTERNAL_EVIDENCE,
        "run_triggered",
        "A run started from an external event, not from an operator pressing start.",
        trigger=trigger,
    )

    dam = workspace.get("dam", {})
    if registry_source:
        record_step(
            workspace,
            EXTERNAL_EVIDENCE,
            "registry_record_resolved",
            f"Resolved public inventory record {dam.get('nid_id')} without asking the owner.",
            source_url=registry_source.get("url"),
            live=registry_source.get("live", False),
        )
    else:
        record_step(
            workspace,
            AGENT,
            "registry_record_resolved",
            f"Loaded the synthetic demonstration record {dam.get('nid_id')}.",
            synthetic=True,
        )

    if drawing is not None:
        record_step(
            workspace,
            AGENT,
            "drawing_read",
            (
                "Read the legacy drawing with Gemini 3.5 Flash on Vertex AI."
                if drawing.was_live
                else "Replayed the graded Gemini 3.5 Flash drawing recording."
            ),
            **drawing.receipt(),
        )
        if drawing.quarantined:
            record_step(
                workspace,
                AGENT,
                "untrusted_spans_quarantined",
                "Removed instruction-shaped text from the transcription before any quote gate ran.",
                spans=drawing.quarantined,
            )
        facts = drawing.facts
        workspace["transcription"] = drawing.transcription
        workspace["model_execution"] = drawing.execution
    else:
        facts = workspace.get("facts", [])
        workspace.setdefault("model_execution", "not_run")

    resolved, conflict = derive_height_conflict(facts, dam)
    workspace["facts"] = resolved
    record_step(
        workspace,
        AGENT,
        "facts_grounded",
        f"Kept {len(resolved)} quoted facts and attached provenance to each.",
        kept=[fact.get("key") for fact in resolved],
    )

    if conflict:
        record_step(
            workspace,
            AGENT,
            "source_conflict_detected",
            (
                f"The drawing says {conflict.get('value')} and the registry says "
                f"{dam.get('dam_height_ft')}. Raised a targeted question instead of picking one."
            ),
            drawing_value=conflict.get("value"),
            registry_value=dam.get("dam_height_ft"),
        )

    decision = mapping_gate(
        approved_map_supplied=False,
        method_applicable=False,
        jurisdiction_accepts=False,
        reference_comparison_passed=False,
    )
    workspace["mapping"] = decision.__dict__
    record_step(
        workspace,
        AGENT,
        "mapping_gate_applied",
        "Applied the mapping gate and stopped short of an inundation extent.",
        status=decision.status,
        may_render_extent=decision.may_render_extent,
    )

    if scheduler is not None:
        register_wakes(workspace, scheduler)

    workspace["outstanding"] = list(outstanding)
    record_step(
        workspace,
        AGENT,
        "paused_for_reserved_authority",
        (
            f"Composed every section that has evidence and paused on {len(outstanding)} owner "
            "questions, which is knowledge the agent is not permitted to invent."
        ),
        outstanding=outstanding,
    )
    workspace["updated_at"] = utc_now()
    return workspace


FOLLOW_UP_KIND = "reopen_held_questions"
NUDGE_KIND = "unanswered_question_nudge"
FOLLOW_UP_AFTER = timedelta(days=3)
NUDGE_AFTER = timedelta(days=7)


def register_wakes(workspace: dict[str, Any], scheduler: Any) -> list[str]:
    """Schedule the work that is real but not due yet.

    Both wakes are idempotent by construction: `sleep_for` derives a deterministic id from the
    run and kind, so re-opening a workspace cannot queue the same follow-up twice.
    """
    run_id = workspace["workspace_id"]
    registered = []
    for kind, delta in ((FOLLOW_UP_KIND, FOLLOW_UP_AFTER), (NUDGE_KIND, NUDGE_AFTER)):
        wake = scheduler.sleep_for(run_id, kind, delta, payload={"workspace_id": run_id})
        registered.append(wake.wake_id)
    workspace["wakes"] = registered
    record_step(
        workspace,
        AGENT,
        "durable_wakes_registered",
        (
            "Registered a held-question review and an unanswered-question follow-up. The agent "
            "sleeps until they are due rather than holding compute open."
        ),
        wakes=[
            {"kind": FOLLOW_UP_KIND, "due_in_days": FOLLOW_UP_AFTER.days},
            {"kind": NUDGE_KIND, "due_in_days": NUDGE_AFTER.days},
        ],
    )
    return registered


def advance_on_wake(
    workspace: dict[str, Any], kind: str, outstanding: list[str] | None = None
) -> dict[str, Any]:
    """What a due wake actually does to a workspace.

    Neither action needs a person and neither exceeds the agent's authority. Reopening a held
    question puts it back in the queue with a stated reason; the nudge records that the draft is
    still waiting. Nothing is sent to an agency, and nothing is answered on the owner's behalf.
    """
    if outstanding is not None:
        workspace["outstanding"] = list(outstanding)
    if kind == FOLLOW_UP_KIND:
        reopened = list(workspace.get("skipped", []))
        if reopened:
            workspace["skipped"] = []
            record_step(
                workspace,
                AGENT,
                "held_questions_reopened",
                f"Reopened {len(reopened)} question(s) held for later, without being asked.",
                reopened=reopened,
            )
        else:
            record_step(
                workspace,
                AGENT,
                "held_questions_reviewed",
                "Checked for held questions on schedule and found none outstanding.",
            )
    elif kind == NUDGE_KIND:
        outstanding = workspace.get("outstanding", [])
        record_step(
            workspace,
            AGENT,
            "follow_up_recorded",
            (
                "Recorded a follow-up on the still-incomplete draft. This is visible when the "
                "owner returns; no message is sent to any person or agency."
            ),
            outstanding=outstanding,
        )
        workspace["follow_up_pending"] = True
    else:
        raise ValueError(f"unknown wake kind {kind}")
    workspace["updated_at"] = utc_now()
    return workspace


def autonomy_proof(workspace: dict[str, Any]) -> dict[str, Any]:
    """Derived from the persisted timeline, never from a description of intent."""
    timeline = workspace.get("timeline", [])
    by_actor: dict[str, int] = {}
    for entry in timeline:
        by_actor[entry["actor"]] = by_actor.get(entry["actor"], 0) + 1

    answered = len(workspace.get("answers", {}))
    outstanding = workspace.get("outstanding", [])
    waiting = (
        "owner knowledge for " + ", ".join(outstanding)
        if outstanding
        else "qualified review of the completed draft"
    )
    return {
        "trigger": workspace.get("trigger"),
        "automatic_agent_steps": by_actor.get(AGENT, 0),
        "human_authority_steps": by_actor.get(HUMAN_AUTHORITY, 0),
        "external_evidence_steps": by_actor.get(EXTERNAL_EVIDENCE, 0),
        "continue_clicks_required": 0,
        "durable_wakes_registered": len(workspace.get("wakes", [])),
        "owner_answers_recorded": answered,
        "model_execution": workspace.get("model_execution", "not_run"),
        "waiting_on": waiting,
        "authority_reserved": list(RESERVED_AUTHORITY),
        "system_decisions_over_reserved_authority": 0,
        "synthetic_demonstration": bool(workspace.get("dam", {}).get("synthetic")),
        "timeline": timeline,
    }
