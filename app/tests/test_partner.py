import pytest

from downstream.collaboration import questions_for
from downstream.partner import (
    DRAWING_FACTS,
    QUESTION_BANK,
    compose_plan,
    context_meter,
    create_workspace,
    next_question,
    public_view,
    record_answer,
    record_feedback,
    resume,
    skip_question,
)


def test_workspace_is_explicitly_synthetic():
    workspace = create_workspace()
    assert workspace["dam"]["synthetic"] is True
    assert workspace["dam"]["nid_id"].startswith("SYNTH-")


def test_drawing_facts_carry_quotes_and_no_pre_baked_conflict():
    """The fixture states what the drawing said. It does not state the answer.

    The conflict used to be written into this constant, which meant the product could not have
    got it wrong. Deriving it is the point of the check below.
    """
    assert all(fact["quoted_text"] for fact in DRAWING_FACTS)
    assert not any("conflict" in str(fact.get("status", "")) for fact in DRAWING_FACTS)
    assert not any("conflicts_with" in fact for fact in DRAWING_FACTS)


def test_conflict_is_derived_by_comparing_the_drawing_against_the_registry():
    workspace = create_workspace()
    conflict = next(fact for fact in workspace["facts"] if fact["status"] == "conflict")
    assert conflict["key"] == "dam_height_ft"
    assert str(workspace["dam"]["dam_height_ft"]) in conflict["conflicts_with"]


def test_a_drawing_that_agrees_with_the_registry_raises_no_conflict():
    workspace = create_workspace(
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
    assert [fact["status"] for fact in workspace["facts"]] == ["agrees_with_registry"]
    assert all(q["id"] != "resolve_dam_height_conflict" for q in questions_for(workspace, []))


def test_questions_are_one_at_a_time_and_not_repeated():
    workspace = create_workspace()
    seen = []
    for _ in range(len(QUESTION_BANK) + 1):
        question = next_question(workspace)
        assert question["id"] not in seen
        seen.append(question["id"])
        record_answer(workspace, question["id"], f"Answer for {question['id']}")
    assert next_question(workspace) is None
    assert seen == [question["id"] for question in QUESTION_BANK] + [
        "resolve_dam_height_conflict"
    ]


def test_known_registry_and_drawing_facts_are_not_asked():
    ids = {question["id"] for question in QUESTION_BANK}
    assert "dam_height_ft" not in ids
    assert "year_completed" not in ids
    assert "crest_elevation" not in ids


def test_unknown_term_changes_later_language():
    workspace = create_workspace()
    first = next_question(workspace)
    record_answer(
        workspace, first["id"], "The gravel lane washes out", did_not_understand=True
    )
    assert workspace["profile"]["reading_level"] == "plain"
    assert first["term"] in workspace["profile"]["unfamiliar_terms"]
    assert next_question(workspace)["text"] == next_question(workspace)["plain"]


def test_answer_is_normalised_and_has_provenance():
    workspace = create_workspace()
    record_answer(workspace, "access_heavy_rain", "  The lane   washes out.  ")
    answer = workspace["answers"]["access_heavy_rain"]
    assert answer["answer"] == "The lane washes out."
    assert answer["provenance"] == "owner"


@pytest.mark.parametrize("answer", ["", "   ", "\n\t"])
def test_empty_answer_is_rejected(answer):
    with pytest.raises(ValueError, match="empty"):
        record_answer(create_workspace(), "access_heavy_rain", answer)


def test_answer_cannot_be_laundered_by_repeating_question():
    workspace = create_workspace()
    record_answer(workspace, "access_heavy_rain", "First answer")
    with pytest.raises(ValueError, match="already answered"):
        record_answer(workspace, "access_heavy_rain", "Replacement without review")


def test_skip_records_a_gap_instead_of_dropping_it():
    workspace = create_workspace()
    skip_question(workspace, "access_heavy_rain")
    assert "access_heavy_rain" in workspace["skipped"]
    assert next_question(workspace)["id"] == "emergency_manager"


def test_not_right_requires_reason_and_adapts_detail():
    workspace = create_workspace()
    with pytest.raises(ValueError, match="requires a reason"):
        record_feedback(workspace, "not_right")
    record_feedback(workspace, "not_right", reason="Too much detail")
    assert workspace["profile"]["detail_preference"] == "terse"


def test_edit_requires_the_revised_text():
    with pytest.raises(ValueError, match="requires revised text"):
        record_feedback(create_workspace(), "edit")


def test_resume_keeps_facts_and_context_bounded():
    workspace = create_workspace()
    for question in QUESTION_BANK:
        record_answer(workspace, question["id"], "A short owner fact")
    before = context_meter(workspace)
    for _ in range(8):
        resume(workspace)
    after = context_meter(workspace)
    assert after["structured_context_tokens"] == before["structured_context_tokens"]
    assert after["within_bound"] is True
    assert (
        after["estimated_transcript_replay_tokens"]
        > before["estimated_transcript_replay_tokens"]
    )


def test_plan_changes_from_owner_fact_not_chat_prose():
    workspace = create_workspace()
    record_answer(workspace, "emergency_manager", "Call Jordan Lee at the county desk")
    section = next(row for row in workspace["plan"] if row["key"] == "notification")
    assert section["text"] == "Call Jordan Lee at the county desk"
    assert section["status"] == "ready_for_review"


def test_mapping_section_is_always_blocked_in_demo_plan():
    section = next(row for row in compose_plan({}) if row["key"] == "mapping")
    assert section["status"] == "blocked_for_qualified_review"
    # The refusal has to be legible to someone who does not know the term "inundation boundary":
    # it is the strongest thing the draft does, and it was described in words that hid it.
    assert section["text"].startswith("No flood map")
    assert "qualified engineer" in section["text"]


def test_public_view_adds_question_meter_and_progress_without_mutating_store():
    workspace = create_workspace()
    view = public_view(workspace)
    assert "next_question" not in workspace
    assert view["next_question"]["id"] == "access_heavy_rain"
    assert view["context_meter"]["within_bound"] is True
    assert view["progress"] == {"answered": 0, "skipped": 0, "total": 6}
