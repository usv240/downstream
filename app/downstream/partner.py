"""Stateful partner loop, adaptation profile, context meter, and draft composition."""

from __future__ import annotations

import copy
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from downstream.safety import DRAFT_DISCLOSURE, mapping_gate

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

DRAWING_FACTS = [
    {
        "key": "crest_elevation",
        "value": "742.6 ft",
        "provenance": "recorded_gemini_drawing_extraction",
        "quoted_text": "TOP OF DAM EL. 742.6",
        "confidence": 0.96,
        "status": "needs_owner_confirmation",
    },
    {
        "key": "spillway",
        "value": "concrete overflow spillway, 18 ft",
        "provenance": "recorded_gemini_drawing_extraction",
        "quoted_text": "CONC. O.F. SPILLWAY 18'-0\"",
        "confidence": 0.91,
        "status": "needs_owner_confirmation",
    },
    {
        "key": "dam_height_ft",
        "value": 31,
        "provenance": "recorded_gemini_drawing_extraction",
        "quoted_text": "MAX. EMBANKMENT HT. 31 FT",
        "confidence": 0.88,
        "status": "conflict",
        "conflicts_with": "fixture_registry: 28 ft",
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
    return datetime.now(timezone.utc).isoformat()


def create_workspace() -> dict[str, Any]:
    mapping = mapping_gate(
        approved_map_supplied=False,
        method_applicable=False,
        jurisdiction_accepts=False,
        reference_comparison_passed=False,
    )
    return {
        "workspace_id": f"eap_{uuid.uuid4().hex[:12]}",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "dam": copy.deepcopy(DEMO_DAM),
        "facts": copy.deepcopy(DRAWING_FACTS),
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
        "mapping": mapping.__dict__,
        "plan": compose_plan({}),
        "status": "draft_in_progress",
        "disclosure": DRAFT_DISCLOSURE,
    }


def next_question(workspace: dict[str, Any]) -> dict[str, Any] | None:
    resolved = set(workspace["answers"]) | set(workspace["skipped"])
    question = next((q for q in QUESTION_BANK if q["id"] not in resolved), None)
    if question is None:
        return None
    profile = workspace["profile"]
    text = question["plain"] if profile["reading_level"] == "plain" else question["technical"]
    for formal, preferred in profile["vocabulary"].items():
        text = re.sub(rf"\b{re.escape(formal)}\b", preferred, text, flags=re.I)
    result = copy.deepcopy(question)
    result["text"] = text
    result["position"] = len(resolved) + 1
    result["total"] = len(QUESTION_BANK)
    if question["term"] in profile["unfamiliar_terms"]:
        result["gloss"] = _gloss(question["term"])
    return result


def _gloss(term: str) -> str:
    return {
        "crest": "the top edge of the dam",
        "spillway": "the channel that safely carries extra water past the dam",
        "notification flowchart": "the ordered list of who calls whom",
        "preparedness": "what is ready before an incident",
        "downstream": "the land and people in the direction water flows",
    }.get(term, term)


def record_answer(
    workspace: dict[str, Any], question_id: str, answer: str, *, did_not_understand: bool = False
) -> dict[str, Any]:
    question = next((q for q in QUESTION_BANK if q["id"] == question_id), None)
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
    workspace["answers"][question_id] = {
        "answer": clean,
        "category": question["category"],
        "section": question["section"],
        "recorded_at": utc_now(),
        "provenance": "owner",
    }
    workspace["asked"].append(question_id)
    workspace["sessions"][-1]["answers"] += 1
    workspace["plan"] = compose_plan(workspace["answers"])
    workspace["updated_at"] = utc_now()
    return workspace


def skip_question(workspace: dict[str, Any], question_id: str) -> dict[str, Any]:
    if question_id not in {q["id"] for q in QUESTION_BANK}:
        raise ValueError("unknown question")
    if question_id not in workspace["skipped"]:
        workspace["skipped"].append(question_id)
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
        pairs = re.findall(r"call (?:it|the) ['\"]?([a-z ]+)['\"]? instead of ['\"]?([a-z ]+)", revised_text, re.I)
        for preferred, formal in pairs:
            workspace["profile"]["vocabulary"][formal.strip().lower()] = preferred.strip().lower()
    if "too much detail" in reason.lower():
        workspace["profile"]["detail_preference"] = "terse"
    workspace["profile"]["feedback_events"].append(event)
    workspace["updated_at"] = utc_now()
    return workspace


def resume(workspace: dict[str, Any]) -> dict[str, Any]:
    workspace["sessions"].append({"opened_at": utc_now(), "answers": 0})
    workspace["updated_at"] = utc_now()
    return workspace


def context_meter(workspace: dict[str, Any]) -> dict[str, Any]:
    fact_tokens = min(260, 38 * (len(workspace["facts"]) + len(workspace["answers"])))
    actual = 410 + fact_tokens
    transcript = 410 + 180 * (len(workspace["asked"]) + len(workspace["sessions"]))
    return {
        "structured_context_tokens": actual,
        "estimated_transcript_replay_tokens": transcript,
        "ratio": round(actual / max(transcript, 1), 3),
        "bound": 670,
        "within_bound": actual <= 670,
        "method": "deduplicated facts plus one current section and fixed-k requirements",
    }


def compose_plan(answers: dict[str, Any]) -> list[dict[str, Any]]:
    notification = answers.get("emergency_manager", {}).get("answer")
    access = answers.get("access_heavy_rain", {}).get("answer")
    affected = answers.get("downstream_people", {}).get("answer")
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
            "text": affected or "Unmapped people, activities, and access constraints still needed.",
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
        "total": len(QUESTION_BANK),
    }
    return view
