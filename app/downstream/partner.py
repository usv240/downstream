"""Stateful partner loop, adaptation profile, context meter, and draft composition."""

from __future__ import annotations

import copy
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from downstream import autonomy
from downstream.collaboration import (
    adaptation_snapshot,
    evidence_ledger,
    mark_conflict_response,
    questions_for,
    revise_owner_answer,
)
from downstream.safety import DRAFT_DISCLOSURE
from spine.redact import Redactor

DEMO_DAM = {
    "nid_id": "SYNTH-DEMO-01",
    "name": "Cedar Hollow Demo Dam",
    "state": "Demonstration jurisdiction",
    "county": "Example County",
    "hazard_potential": "High",
    "eap_status": "Synthetic fixture, not reported to NID",
    "year_completed": 1958,
    "dam_height_ft": 28,
    "owner_type": "Synthetic private owner",
    "synthetic": True,
}

# The baseline drawing read, used when no drawing service is attached. The conflict is
# deliberately absent: `autonomy.derive_height_conflict` finds it by comparing these values
# against the registry row, so a drawing that agrees produces no sixth question.
DRAWING_FACTS = [
    {
        "key": "crest_elevation",
        "value": "742.6 ft",
        "provenance": "recorded_gemini_drawing_extraction",
        "quoted_text": "TOP OF DAM EL. 742.6",
        "confidence": 0.96,
    },
    {
        "key": "spillway",
        "value": "concrete overflow spillway, 18 ft",
        "provenance": "recorded_gemini_drawing_extraction",
        "quoted_text": "CONC. O.F. SPILLWAY 18'-0\"",
        "confidence": 0.91,
    },
    {
        "key": "dam_height_ft",
        "value": 31,
        "provenance": "recorded_gemini_drawing_extraction",
        "quoted_text": "MAX. EMBANKMENT HT. 31 FT",
        "confidence": 0.88,
    },
]

QUESTION_BANK = [
    {
        "id": "access_heavy_rain",
        "category": "access",
        "term": "crest",
        "plain": "How do you reach the top of the dam during heavy rain, and can that road wash out?",
        "technical": "How is the dam crest accessed during adverse weather?",
        "why": "The draft must identify practical access limits before an emergency.",
        "section": "preparedness",
    },
    {
        "id": "emergency_manager",
        "category": "contacts",
        "term": "notification flowchart",
        "plain": "Who is the county emergency manager, and which number works after hours?",
        "technical": "Provide the primary emergency-management notification contact.",
        "why": "The notification chain must come from a person, never generated text.",
        "section": "notification",
    },
    {
        "id": "downstream_people",
        "category": "local_knowledge",
        "term": "downstream",
        "plain": "Who lives, works, camps, or keeps animals below the dam that a map may miss?",
        "technical": "Identify transient or unmapped downstream exposure.",
        "why": "Local knowledge can reveal people and places absent from public datasets.",
        "section": "affected_areas",
    },
    {
        "id": "spillway_history",
        "category": "history",
        "term": "spillway",
        "plain": "Has water ever gone over the overflow channel, and what happened?",
        "technical": "Describe prior spillway activation and observed consequences.",
        "why": "Observed history helps reviewers understand site-specific warning signs.",
        "section": "detection",
    },
    {
        "id": "equipment",
        "category": "resources",
        "term": "preparedness",
        "plain": "Who has useful equipment nearby, and how long would it take to arrive?",
        "technical": "List locally available emergency equipment and mobilization time.",
        "why": "A usable plan names resources and realistic response times.",
        "section": "preparedness",
    },
]

REQUIREMENTS = {
    "purpose": {
        "text": "An EAP is a formal document that identifies potential emergency conditions at a dam and specifies actions to be followed to minimize loss of life and property damage.",
        "source": "FEMA P-64, Basic Considerations, page I-1",
        "url": "https://www.fema.gov/sites/default/files/2020-08/fema_dam-safety_emergency-action-planning_P-64.pdf",
    },
    "notification": {
        "text": "An EAP includes a notification flowchart with names and numbers of who will call whom and in what priority.",
        "source": "ASDSO, Emergency Action Planning",
        "url": "https://damsafety.org/dam-owners/emergency-action-planning",
    },
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def outstanding_ids(workspace: dict[str, Any]) -> list[str]:
    """Question ids the owner has neither answered nor held."""
    resolved = set(workspace.get("answers", {})) | set(workspace.get("skipped", []))
    return [
        question["id"]
        for question in questions_for(workspace, QUESTION_BANK)
        if question["id"] not in resolved
    ]


def create_workspace(
    *,
    dam: dict[str, Any] | None = None,
    facts: list[dict[str, Any]] | None = None,
    drawing: Any | None = None,
    registry_source: dict[str, Any] | None = None,
    scheduler: Any | None = None,
    trigger: str = autonomy.TRIGGER_PUBLIC,
) -> dict[str, Any]:
    """Open a workspace by running the autonomous opening sequence.

    Nothing here waits for a click. The caller supplies a trigger and, optionally, a drawing
    service and a wake scheduler; the agent resolves the record, reads the drawing, grounds the
    facts, derives any source conflict, applies the mapping gate, schedules its follow-ups and
    stops at the owner questions.
    """
    workspace = {
        "workspace_id": f"eap_{uuid.uuid4().hex[:12]}",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "dam": copy.deepcopy(dam if dam is not None else DEMO_DAM),
        "facts": copy.deepcopy(facts if facts is not None else DRAWING_FACTS),
        "answers": {},
        "asked": [],
        "skipped": [],
        "sessions": [{"opened_at": utc_now(), "answers": 0}],
        "profile": {
            "reading_level": "standard",
            "detail_preference": "standard",
            "format_preference": "bulleted",
            "vocabulary": {},
            "unfamiliar_terms": [],
            "feedback_events": [],
        },
        "plan": compose_plan({}),
        "status": "draft_in_progress",
        "disclosure": DRAFT_DISCLOSURE,
    }
    autonomy.open_run(
        workspace,
        trigger=trigger,
        outstanding=[],
        drawing=drawing,
        registry_source=registry_source,
        scheduler=scheduler,
    )
    # The question set depends on the facts the run just grounded, so it is computed after.
    workspace["outstanding"] = outstanding_ids(workspace)
    return workspace


def next_question(workspace: dict[str, Any]) -> dict[str, Any] | None:
    resolved = set(workspace["answers"]) | set(workspace["skipped"])
    questions = questions_for(workspace, QUESTION_BANK)
    question = next((q for q in questions if q["id"] not in resolved), None)
    if question is None:
        return None
    profile = workspace["profile"]
    text = (
        question["plain"]
        if profile["reading_level"] == "plain"
        else question["technical"]
    )
    for formal, preferred in profile["vocabulary"].items():
        text = re.sub(rf"\b{re.escape(formal)}\b", preferred, text, flags=re.I)
    result = copy.deepcopy(question)
    result["text"] = text
    result["position"] = len(resolved) + 1
    result["total"] = len(questions)
    result.setdefault("basis", "missing_owner_fact")
    if question["term"] in profile["unfamiliar_terms"]:
        result["gloss"] = _gloss(question["term"])
    return result


def _gloss(term: str) -> str:
    return {
        "crest": "the top edge of the dam",
        "spillway": "the channel that safely carries extra water past the dam",
        "notification flowchart": "the ordered list of who calls whom",
        "preparedness": "what is ready before an incident",
        "dam height": "the vertical distance from the lowest foundation point to the top of the dam",
        "downstream": "the land and people in the direction water flows",
    }.get(term, term)


_REDACTOR = Redactor()


def shield(text: str) -> dict[str, Any]:
    """Pseudonymise shaped identifiers for anything that leaves the workspace.

    This deliberately does not overwrite the owner's words. An Emergency Action Plan needs the
    emergency manager's actual name and actual after-hours number; replacing them would destroy
    the artefact the owner came here to build. What it produces is a parallel, model-safe form,
    and a list of the identifier shapes found so the interface can say what it noticed.
    """
    result = _REDACTOR.redact(text)
    return {
        "text": result.text,
        "shapes": sorted({item.kind for item in result.replacements}),
    }


def record_answer(
    workspace: dict[str, Any],
    question_id: str,
    answer: str,
    *,
    did_not_understand: bool = False,
) -> dict[str, Any]:
    question = next(
        (q for q in questions_for(workspace, QUESTION_BANK) if q["id"] == question_id),
        None,
    )
    if question is None:
        raise ValueError("unknown question")
    if question_id in workspace["answers"]:
        raise ValueError("question already answered")
    if did_not_understand:
        term = question["term"]
        if term not in workspace["profile"]["unfamiliar_terms"]:
            workspace["profile"]["unfamiliar_terms"].append(term)
        workspace["profile"]["reading_level"] = "plain"
        workspace["profile"]["feedback_events"].append(
            {"type": "term_not_understood", "term": term, "at": utc_now()}
        )
        workspace["updated_at"] = utc_now()
        return workspace
    clean = " ".join(answer.split())
    if not clean:
        raise ValueError("answer cannot be empty")
    recorded_at = utc_now()
    shielded = shield(clean)
    workspace["answers"][question_id] = {
        "answer": clean,
        "model_safe_answer": shielded["text"],
        "identifier_shapes": shielded["shapes"],
        "category": question["category"],
        "section": question["section"],
        "recorded_at": recorded_at,
        "provenance": "owner",
        "version": 1,
        "history": [
            {
                "version": 1,
                "answer": clean,
                "recorded_at": recorded_at,
                "reason": "initial owner answer",
            }
        ],
    }
    mark_conflict_response(workspace, question_id, clean)
    workspace["asked"].append(question_id)
    workspace["sessions"][-1]["answers"] += 1
    workspace["plan"] = compose_plan(workspace["answers"])
    autonomy.record_step(
        workspace,
        autonomy.HUMAN_AUTHORITY,
        "owner_answer_recorded",
        f"The owner supplied knowledge for {question_id}; the agent did not infer it.",
        question_id=question_id,
        section=question["section"],
    )
    workspace["outstanding"] = outstanding_ids(workspace)
    autonomy.record_step(
        workspace,
        autonomy.AGENT,
        "sections_recomposed",
        "Recomposed every section whose evidence changed, without being asked.",
        sections=[section["key"] for section in workspace["plan"]],
    )
    workspace["updated_at"] = utc_now()
    return workspace


def revise_answer(
    workspace: dict[str, Any], question_id: str, revised_answer: str, *, reason: str
) -> dict[str, Any]:
    """Apply owner correction to the work product and retain the previous version."""
    at = utc_now()
    entry = revise_owner_answer(workspace, question_id, revised_answer, reason, at)
    # Re-shield. The model-safe form is derived from the answer, so a correction that introduces
    # an identifier -- an owner adding the after-hours number they had left out -- must produce a
    # new one. Leaving the old form in place meant the boundary silently described the previous
    # version of an answer, and an answer that gained its first identifier through a correction
    # would have had none of it pseudonymised at all.
    shielded = shield(entry["answer"])
    entry["model_safe_answer"] = shielded["text"]
    entry["identifier_shapes"] = shielded["shapes"]
    workspace["plan"] = compose_plan(workspace["answers"])
    autonomy.record_step(
        workspace,
        autonomy.HUMAN_AUTHORITY,
        "owner_correction_applied",
        f"The owner corrected {question_id}; both versions are retained.",
        question_id=question_id,
        version=workspace["answers"][question_id]["version"],
    )
    workspace["updated_at"] = at
    return workspace


def skip_question(workspace: dict[str, Any], question_id: str) -> dict[str, Any]:
    valid_ids = {q["id"] for q in questions_for(workspace, QUESTION_BANK)}
    if question_id not in valid_ids:
        raise ValueError("unknown question")
    if question_id in workspace["answers"]:
        raise ValueError("question already answered")
    if question_id not in workspace["skipped"]:
        workspace["skipped"].append(question_id)
    workspace["outstanding"] = outstanding_ids(workspace)
    workspace["updated_at"] = utc_now()
    return workspace


def record_feedback(
    workspace: dict[str, Any], action: str, *, reason: str = "", revised_text: str = ""
) -> dict[str, Any]:
    if action not in {"accept", "edit", "not_right"}:
        raise ValueError("unsupported feedback action")
    if action == "not_right" and not reason.strip():
        raise ValueError("not_right requires a reason")
    event = {"type": action, "reason": reason.strip(), "at": utc_now()}
    if action == "edit":
        if not revised_text.strip():
            raise ValueError("edit requires revised text")
        event["revised_text"] = revised_text.strip()
        pairs = re.findall(
            r"call (?:it|the) ['\"]?([a-z ]+)['\"]? instead of ['\"]?([a-z ]+)",
            revised_text,
            re.I,
        )
        for preferred, formal in pairs:
            workspace["profile"]["vocabulary"][
                formal.strip().lower()
            ] = preferred.strip().lower()
    if "too much detail" in reason.lower():
        workspace["profile"]["detail_preference"] = "terse"
    workspace["profile"]["feedback_events"].append(event)
    workspace["updated_at"] = utc_now()
    return workspace


def resume(workspace: dict[str, Any]) -> dict[str, Any]:
    reopened = list(workspace["skipped"])
    workspace["skipped"].clear()
    workspace["sessions"].append(
        {"opened_at": utc_now(), "answers": 0, "reopened_questions": reopened}
    )
    if reopened:
        autonomy.record_step(
            workspace,
            autonomy.AGENT,
            "held_questions_reopened",
            f"Reopened {len(reopened)} held question(s) on the next session without being asked.",
            reopened=reopened,
        )
    workspace["outstanding"] = outstanding_ids(workspace)
    workspace["updated_at"] = utc_now()
    return workspace


CONTEXT_BUDGET_TOKENS = 900


def assemble_context(workspace: dict[str, Any]) -> str:
    """Build the exact payload a model turn would receive.

    Bounded on purpose: deduplicated facts, the one section currently in play, and a fixed k of
    requirement passages. Prior answers contribute their current value only, never their revision
    history, and no session transcript is replayed.
    """
    question = next_question(workspace)
    section_key = question["section"] if question else "purpose"
    parts: list[str] = [json.dumps(workspace.get("dam", {}), sort_keys=True)]
    seen: set[str] = set()
    for fact in workspace.get("facts", []):
        key = str(fact.get("key"))
        if key in seen:
            continue
        seen.add(key)
        parts.append(json.dumps(fact, sort_keys=True, default=str))
    for answer in workspace.get("answers", {}).values():
        # The redaction gate is load-bearing here: what crosses the model boundary is the
        # pseudonymised form. The verbatim answer stays in the owner's workspace, because a
        # notification flowchart is useless without the real name and the real number.
        parts.append(str(answer.get("model_safe_answer") or answer.get("answer", "")))
    for section in workspace.get("plan", []):
        if section["key"] == section_key:
            parts.append(json.dumps(section, sort_keys=True, default=str))
    for requirement in REQUIREMENTS.values():
        parts.append(requirement["text"])
    if question:
        parts.append(str(question.get("text", "")))
    return "\n".join(parts)


def transcript_replay(workspace: dict[str, Any]) -> str:
    """What naive replay would have sent: every turn, every version, every session."""
    parts: list[str] = [json.dumps(workspace.get("dam", {}), sort_keys=True)]
    for fact in workspace.get("facts", []):
        parts.append(json.dumps(fact, sort_keys=True, default=str))
    for question_id, answer in workspace.get("answers", {}).items():
        for entry in answer.get("history", []):
            parts.append(f"{question_id} v{entry.get('version')}: {entry.get('answer')}")
            parts.append(str(entry.get("reason", "")))
    for question in QUESTION_BANK:
        parts.append(question["plain"])
        parts.append(question["technical"])
        parts.append(question["why"])
    for event in workspace.get("profile", {}).get("feedback_events", []):
        parts.append(json.dumps(event, sort_keys=True, default=str))
    for entry in workspace.get("timeline", []):
        parts.append(json.dumps(entry, sort_keys=True, default=str))
    for index, session in enumerate(workspace.get("sessions", [])):
        parts.append(f"session {index}: {json.dumps(session, sort_keys=True, default=str)}")
    for requirement in REQUIREMENTS.values():
        parts.append(requirement["text"])
    return "\n".join(parts)


def estimate_tokens(text: str) -> int:
    """Four characters per token. Coarse, stated as an estimate, applied to both sides equally."""
    return (len(text) + 3) // 4


def context_meter(workspace: dict[str, Any]) -> dict[str, Any]:
    """Measure the context this turn would actually send.

    This used to be a formula whose result was clamped below its own bound, so `within_bound`
    could never be false and the two demo checks that read it could never fail. It now measures
    the assembled payload, which means the bound is a budget the design has to keep rather than
    an arithmetic identity.
    """
    actual = estimate_tokens(assemble_context(workspace))
    replay = estimate_tokens(transcript_replay(workspace))
    return {
        "structured_context_tokens": actual,
        "estimated_transcript_replay_tokens": replay,
        "ratio": round(actual / max(replay, 1), 3),
        "bound": CONTEXT_BUDGET_TOKENS,
        "within_bound": actual <= CONTEXT_BUDGET_TOKENS,
        "headroom_tokens": CONTEXT_BUDGET_TOKENS - actual,
        "method": (
            "measured over the assembled turn payload: deduplicated facts, current answers, one "
            "active section, and fixed-k requirements. Four characters per token."
        ),
    }


def compose_plan(answers: dict[str, Any]) -> list[dict[str, Any]]:
    notification = answers.get("emergency_manager", {}).get("answer")
    access = answers.get("access_heavy_rain", {}).get("answer")
    affected = answers.get("downstream_people", {}).get("answer")
    conflict = answers.get("resolve_dam_height_conflict", {}).get("answer")
    sections = [
        {
            "key": "purpose",
            "title": "Purpose and status",
            "status": "draft",
            "text": "This draft organizes owner-supplied and source-grounded facts for review.",
            "source": REQUIREMENTS["purpose"],
        },
        {
            "key": "notification",
            "title": "Notification flow",
            "status": "ready_for_review" if notification else "needs_owner_fact",
            "text": notification or "After-hours emergency contact still needed.",
            "source": REQUIREMENTS["notification"],
        },
        {
            "key": "preparedness",
            "title": "Access and preparedness",
            "status": "ready_for_review" if access else "needs_owner_fact",
            "text": access or "Heavy-rain access conditions still needed.",
            "source": None,
        },
        {
            "key": "affected_areas",
            "title": "Downstream local knowledge",
            "status": "ready_for_review" if affected else "needs_owner_fact",
            "text": affected
            or "Unmapped people, activities, and access constraints still needed.",
            "source": None,
        },
        {
            "key": "site_facts",
            "title": "Conflicting site facts",
            "status": (
                "needs_qualified_confirmation" if conflict else "needs_owner_fact"
            ),
            "text": conflict
            or "The 28-foot registry and 31-foot drawing values still conflict.",
            "source": None,
        },
        {
            "key": "mapping",
            "title": "Mapping safety gate",
            "status": "blocked_for_qualified_review",
            "text": "No inundation boundary generated. A documented flow path may be reviewed.",
            "source": None,
        },
    ]
    return sections


def public_view(workspace: dict[str, Any]) -> dict[str, Any]:
    view = copy.deepcopy(workspace)
    view["next_question"] = next_question(workspace)
    view["context_meter"] = context_meter(workspace)
    view["progress"] = {
        "answered": len(workspace["answers"]),
        "skipped": len(workspace["skipped"]),
        "total": len(questions_for(workspace, QUESTION_BANK)),
    }
    view["adaptation"] = adaptation_snapshot(workspace)
    view["evidence_ledger"] = evidence_ledger(workspace)
    view["autonomy_proof"] = autonomy.autonomy_proof(workspace)
    view.pop("_tenant_id", None)
    return view
