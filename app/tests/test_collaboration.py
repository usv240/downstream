import pytest

from downstream.collaboration import adaptation_snapshot, evidence_ledger, questions_for
from downstream.partner import (
    QUESTION_BANK,
    create_workspace,
    next_question,
    record_answer,
    revise_answer,
)


def answer_base_questions(workspace):
    for index, question in enumerate(QUESTION_BANK):
        record_answer(workspace, question["id"], f"Owner fact {index + 1}")


def test_source_conflict_becomes_a_targeted_question():
    workspace = create_workspace()
    answer_base_questions(workspace)

    question = next_question(workspace)
    assert question["id"] == "resolve_dam_height_conflict"
    assert question["basis"] == "unresolved_source_conflict"
    assert question["evidence"] == {
        "drawing_value": 31,
        "drawing_quote": "MAX. EMBANKMENT HT. 31 FT",
        "conflicts_with": "registry record: 28 ft",
    }

    record_answer(workspace, question["id"], "Please explain.", did_not_understand=True)
    repeated = next_question(workspace)
    assert repeated["id"] == question["id"]
    assert repeated["text"] == repeated["plain"]
    assert repeated["gloss"].startswith("the vertical distance")


def test_conflict_response_adds_context_without_claiming_resolution():
    workspace = create_workspace()
    answer_base_questions(workspace)
    record_answer(
        workspace,
        "resolve_dam_height_conflict",
        "Our inspection sheet uses 31 feet, pending engineer confirmation.",
    )

    fact = next(fact for fact in workspace["facts"] if fact["key"] == "dam_height_ft")
    section = next(
        section for section in workspace["plan"] if section["key"] == "site_facts"
    )
    assert fact["status"] == "owner_response_recorded"
    assert "qualified-engineer" in fact["resolution"]
    assert section["status"] == "needs_qualified_confirmation"
    assert next_question(workspace) is None


def test_revision_changes_plan_and_keeps_history():
    workspace = create_workspace()
    record_answer(workspace, "access_heavy_rain", "The west lane is reliable.")
    revise_answer(
        workspace,
        "access_heavy_rain",
        "The east lane washes out at the second bend.",
        reason="Owner corrected the access road.",
    )

    answer = workspace["answers"]["access_heavy_rain"]
    section = next(
        section for section in workspace["plan"] if section["key"] == "preparedness"
    )
    assert answer["version"] == 2
    assert [row["answer"] for row in answer["history"]] == [
        "The west lane is reliable.",
        "The east lane washes out at the second bend.",
    ]
    assert section["text"] == "The east lane washes out at the second bend."
    assert adaptation_snapshot(workspace)["answer_revisions"] == 1
    ledger = next(
        row for row in evidence_ledger(workspace) if row["section"] == "preparedness"
    )
    assert ledger["evidence"] == [
        {
            "kind": "owner_answer",
            "question_id": "access_heavy_rain",
            "version": 2,
            "provenance": "owner",
        }
    ]


@pytest.mark.parametrize(
    ("question_id", "answer", "reason", "message"),
    [
        ("access_heavy_rain", "New answer", "Correction", "unanswered"),
        ("answered", "  ", "Correction", "empty"),
        ("answered", "New answer", "  ", "requires a reason"),
    ],
)
def test_invalid_revision_fails_closed(question_id, answer, reason, message):
    workspace = create_workspace()
    if question_id == "answered":
        question_id = "access_heavy_rain"
        record_answer(workspace, question_id, "Initial answer")
    with pytest.raises(ValueError, match=message):
        revise_answer(workspace, question_id, answer, reason=reason)


def test_conflict_question_disappears_when_no_conflicting_source_exists():
    workspace = create_workspace()
    workspace["facts"] = [
        fact for fact in workspace["facts"] if fact["key"] != "dam_height_ft"
    ]
    assert len(questions_for(workspace, QUESTION_BANK)) == len(QUESTION_BANK)


def test_a_correction_that_adds_an_identifier_is_shielded_too():
    """The model-safe form is derived from the answer, so a revision has to regenerate it.

    It did not. An owner who corrected an answer to add the after-hours number they had left out
    would have had that number sitting in the form meant to protect it -- or, if the original
    answer had carried no identifier at all, the correction's number would have crossed the model
    boundary unprotected.
    """
    from downstream.partner import create_workspace, record_answer, revise_answer

    workspace = create_workspace()
    record_answer(workspace, "emergency_manager", "The county duty desk covers after hours.")
    assert workspace["answers"]["emergency_manager"]["identifier_shapes"] == []

    revise_answer(
        workspace,
        "emergency_manager",
        "After hours call the county duty desk on 406-555-0142, not the daytime office line.",
        reason="Owner added the number.",
    )
    entry = workspace["answers"]["emergency_manager"]
    assert "PHONE" in entry["identifier_shapes"]
    assert "406-555-0142" in entry["answer"], "the owner keeps their own words"
    assert "406-555-0142" not in entry["model_safe_answer"]
    assert "PHONE_1" in entry["model_safe_answer"]


def test_the_model_boundary_reflects_the_current_version_not_the_first_one():
    from downstream.partner import assemble_context, create_workspace, record_answer, revise_answer

    workspace = create_workspace()
    record_answer(workspace, "emergency_manager", "Ring the old number, 406-555-0100.")
    revise_answer(
        workspace, "emergency_manager", "Ring the new number, 406-555-0142.",
        reason="Owner corrected it.",
    )
    boundary = assemble_context(workspace)
    assert "406-555-0100" not in boundary
    assert "406-555-0142" not in boundary
    assert "old number" not in boundary, "the boundary should carry the current answer"
