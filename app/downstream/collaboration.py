"""Adaptive collaboration policy and auditable revision history.

This module keeps user correction separate from draft composition. The partner can change how it
asks and what it drafts, while preserving the original answer and every later revision.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable
from typing import Any

HEIGHT_CONFLICT_QUESTION = {
    "id": "resolve_dam_height_conflict",
    "category": "source_conflict",
    "term": "dam height",
    "plain": (
        "The public-style registry says 28 feet, while the legacy drawing says 31 feet. "
        "Which value do your current records use, or who should verify it?"
    ),
    "technical": (
        "Resolve the 28-foot registry versus 31-foot drawing conflict, or name the qualified "
        "reviewer who will resolve it."
    ),
    "why": (
        "Conflicting source values must remain visible until an owner and qualified reviewer "
        "confirm the controlling record."
    ),
    "section": "site_facts",
    "fact_key": "dam_height_ft",
    "basis": "unresolved_source_conflict",
}


def questions_for(
    workspace: dict[str, Any], base_questions: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return stable owner gaps plus questions created by unresolved source conflicts."""
    questions = [copy.deepcopy(question) for question in base_questions]
    height = next(
        (
            fact
            for fact in workspace.get("facts", [])
            if fact.get("key") == "dam_height_ft"
            and fact.get("status") in {"conflict", "owner_response_recorded"}
        ),
        None,
    )
    if height:
        question = copy.deepcopy(HEIGHT_CONFLICT_QUESTION)
        question["evidence"] = {
            "drawing_value": height.get("value"),
            "drawing_quote": height.get("quoted_text"),
            "conflicts_with": height.get("conflicts_with"),
        }
        questions.append(question)
    return questions


def mark_conflict_response(
    workspace: dict[str, Any], question_id: str, answer: str
) -> None:
    """Record owner context without pretending that it resolves an engineering conflict."""
    if question_id != HEIGHT_CONFLICT_QUESTION["id"]:
        return
    fact = next(
        (
            fact
            for fact in workspace.get("facts", [])
            if fact.get("key") == "dam_height_ft"
        ),
        None,
    )
    if fact is None:
        raise ValueError("height conflict is no longer present")
    fact["status"] = "owner_response_recorded"
    fact["owner_response"] = answer
    fact["resolution"] = (
        "requires controlling-record or qualified-engineer confirmation"
    )


def revise_owner_answer(
    workspace: dict[str, Any],
    question_id: str,
    revised_answer: str,
    reason: str,
    at: str,
) -> dict[str, Any]:
    """Replace the current answer while retaining an immutable, numbered history."""
    entry = workspace.get("answers", {}).get(question_id)
    if entry is None:
        raise ValueError("cannot revise an unanswered question")
    clean = " ".join(revised_answer.split())
    why = " ".join(reason.split())
    if not clean:
        raise ValueError("revised answer cannot be empty")
    if not why:
        raise ValueError("revision requires a reason")
    history = entry.setdefault(
        "history",
        [
            {
                "version": entry.get("version", 1),
                "answer": entry["answer"],
                "recorded_at": entry["recorded_at"],
                "reason": "initial owner answer",
            }
        ],
    )
    version = int(entry.get("version", len(history))) + 1
    history.append(
        {
            "version": version,
            "answer": clean,
            "recorded_at": at,
            "reason": why,
        }
    )
    entry.update({"answer": clean, "version": version, "revised_at": at})
    workspace["profile"]["feedback_events"].append(
        {
            "type": "answer_revised",
            "question_id": question_id,
            "version": version,
            "reason": why,
            "at": at,
        }
    )
    if question_id == HEIGHT_CONFLICT_QUESTION["id"]:
        mark_conflict_response(workspace, question_id, clean)
    return entry


def adaptation_snapshot(workspace: dict[str, Any]) -> dict[str, Any]:
    answers = workspace.get("answers", {})
    return {
        "sessions_remembered": len(workspace.get("sessions", [])),
        "terms_rephrased": len(
            workspace.get("profile", {}).get("unfamiliar_terms", [])
        ),
        "feedback_events": len(workspace.get("profile", {}).get("feedback_events", [])),
        "answer_revisions": sum(
            max(0, int(answer.get("version", 1)) - 1) for answer in answers.values()
        ),
        "source_conflicts_surfaced": sum(
            fact.get("status") in {"conflict", "owner_response_recorded"}
            for fact in workspace.get("facts", [])
        ),
        "source_conflicts_with_owner_context": sum(
            fact.get("status") == "owner_response_recorded"
            for fact in workspace.get("facts", [])
        ),
    }


def evidence_ledger(workspace: dict[str, Any]) -> list[dict[str, Any]]:
    """Explain exactly what supports each rendered draft section."""
    answer_by_section: dict[str, list[dict[str, Any]]] = {}
    for question_id, answer in workspace.get("answers", {}).items():
        answer_by_section.setdefault(answer["section"], []).append(
            {
                "kind": "owner_answer",
                "question_id": question_id,
                "version": answer.get("version", 1),
                "provenance": answer["provenance"],
            }
        )
    rows = []
    for section in workspace.get("plan", []):
        evidence = answer_by_section.get(section["key"], [])
        if section.get("source"):
            evidence = [
                {
                    "kind": "published_requirement",
                    "source": section["source"]["source"],
                    "url": section["source"]["url"],
                    "quoted_text": section["source"]["text"],
                },
                *evidence,
            ]
        if section["key"] == "mapping":
            evidence = [{"kind": "fail_closed_mapping_policy"}]
        rows.append(
            {
                "section": section["key"],
                "status": section["status"],
                "evidence": evidence,
                "rendered_from_evidence": bool(evidence),
            }
        )
    return rows
