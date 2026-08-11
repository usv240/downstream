from downstream.partner import create_workspace, next_question, record_answer


def test_unknown_term_reasks_same_gap_before_advancing():
    workspace = create_workspace()
    first = next_question(workspace)
    record_answer(
        workspace,
        first["id"],
        "Please explain that term.",
        did_not_understand=True,
    )
    repeated = next_question(workspace)
    assert repeated["id"] == first["id"]
    assert repeated["text"] == repeated["plain"]
    assert repeated["gloss"]
    assert first["id"] not in workspace["answers"]


def test_unknown_term_signal_does_not_inflate_answer_or_context_counts():
    workspace = create_workspace()
    first = next_question(workspace)
    record_answer(workspace, first["id"], "Explain", did_not_understand=True)
    assert workspace["sessions"][-1]["answers"] == 0
    assert workspace["asked"] == []
