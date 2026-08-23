"""What the agent does on its own, and what it refuses to do.

The claim under test is narrow on purpose: every in-scope transition runs automatically, and the
run pauses only for owner knowledge or for evidence that must come from outside. These tests
check that claim against the persisted timeline rather than against a description of intent.
"""

from downstream import autonomy
from downstream.partner import (
    QUESTION_BANK,
    create_workspace,
    next_question,
    outstanding_ids,
    public_view,
    record_answer,
    revise_answer,
    skip_question,
)
from spine.clock import ClockState, MemoryClockStateStore, SimulatedClock
from spine.wake import MemoryWakeStore, WakeScheduler


def scheduler(offset_seconds: float = 0.0) -> WakeScheduler:
    store = MemoryClockStateStore(ClockState(offset_seconds=offset_seconds))
    return WakeScheduler(MemoryWakeStore(), SimulatedClock(store))


def test_opening_a_workspace_runs_a_sequence_with_no_human_step():
    workspace = create_workspace()
    steps = [entry["step"] for entry in workspace["timeline"]]
    assert steps == [
        "run_triggered",
        "registry_record_resolved",
        "facts_grounded",
        "source_conflict_detected",
        "mapping_gate_applied",
        "paused_for_reserved_authority",
    ]
    assert not any(entry["actor"] == autonomy.HUMAN_AUTHORITY for entry in workspace["timeline"])


def test_the_run_starts_from_a_trigger_recorded_as_external():
    workspace = create_workspace()
    first = workspace["timeline"][0]
    assert first["actor"] == autonomy.EXTERNAL_EVIDENCE
    assert first["evidence"]["trigger"] == autonomy.TRIGGER_PUBLIC


def test_the_receipt_counts_what_the_timeline_records():
    workspace = create_workspace()
    record_answer(workspace, "access_heavy_rain", "The lane washes out at the second bend.")
    proof = autonomy.autonomy_proof(workspace)
    timeline = workspace["timeline"]
    assert proof["automatic_agent_steps"] == sum(
        1 for entry in timeline if entry["actor"] == autonomy.AGENT
    )
    assert proof["human_authority_steps"] == sum(
        1 for entry in timeline if entry["actor"] == autonomy.HUMAN_AUTHORITY
    )
    assert proof["continue_clicks_required"] == 0


def test_an_owner_answer_is_recorded_as_authority_not_as_agent_work():
    workspace = create_workspace()
    record_answer(workspace, "access_heavy_rain", "The lane washes out.")
    entry = next(e for e in workspace["timeline"] if e["step"] == "owner_answer_recorded")
    assert entry["actor"] == autonomy.HUMAN_AUTHORITY


def test_recomposition_after_an_answer_happens_without_being_asked():
    workspace = create_workspace()
    record_answer(workspace, "access_heavy_rain", "The lane washes out.")
    entry = next(e for e in workspace["timeline"] if e["step"] == "sections_recomposed")
    assert entry["actor"] == autonomy.AGENT


def test_the_receipt_names_what_the_run_is_waiting_for():
    workspace = create_workspace()
    assert "owner knowledge" in autonomy.autonomy_proof(workspace)["waiting_on"]
    for question in QUESTION_BANK:
        record_answer(workspace, question["id"], "A synthetic owner fact.")
    conflict = next_question(workspace)
    record_answer(workspace, conflict["id"], "The state engineer should confirm it.")
    workspace["outstanding"] = outstanding_ids(workspace)
    assert autonomy.autonomy_proof(workspace)["waiting_on"] == (
        "qualified review of the completed draft"
    )


def test_reserved_authority_is_declared_and_never_exercised():
    workspace = create_workspace()
    for question in QUESTION_BANK:
        record_answer(workspace, question["id"], "A synthetic owner fact.")
    revise_answer(workspace, "equipment", "A tracked excavator.", reason="Owner correction.")
    proof = autonomy.autonomy_proof(workspace)
    assert proof["system_decisions_over_reserved_authority"] == 0
    assert "approval, certification, or submission of the plan" in proof["authority_reserved"]
    assert workspace["mapping"]["may_render_extent"] is False


def test_opening_registers_two_durable_wakes():
    workspace = create_workspace(scheduler=scheduler())
    assert len(workspace["wakes"]) == 2
    assert autonomy.autonomy_proof(workspace)["durable_wakes_registered"] == 2


def test_registering_the_same_run_twice_does_not_duplicate_a_wake():
    shared = scheduler()
    workspace = create_workspace(scheduler=shared)
    first = list(workspace["wakes"])
    autonomy.register_wakes(workspace, shared)
    assert workspace["wakes"] == first
    assert len(shared.pending_for(workspace["workspace_id"])) == 2


def test_a_wake_does_not_fire_before_it_is_due():
    shared = scheduler()
    workspace = create_workspace(scheduler=shared)
    assert shared.dispatch_wake(workspace["wakes"][0], lambda wake: None) is None


def test_a_due_wake_reopens_held_questions_without_being_asked():
    workspace = create_workspace(scheduler=scheduler())
    skip_question(workspace, "equipment")
    assert workspace["skipped"] == ["equipment"]
    autonomy.advance_on_wake(
        workspace, autonomy.FOLLOW_UP_KIND, outstanding=outstanding_ids(workspace)
    )
    assert workspace["skipped"] == []
    entry = next(e for e in workspace["timeline"] if e["step"] == "held_questions_reopened")
    assert entry["evidence"]["reopened"] == ["equipment"]


def test_the_follow_up_wake_records_a_nudge_and_sends_nothing():
    workspace = create_workspace(scheduler=scheduler())
    autonomy.advance_on_wake(
        workspace, autonomy.NUDGE_KIND, outstanding=outstanding_ids(workspace)
    )
    entry = next(e for e in workspace["timeline"] if e["step"] == "follow_up_recorded")
    assert "no message is sent" in entry["detail"]
    assert workspace["follow_up_pending"] is True


def test_an_unknown_wake_kind_is_refused_rather_than_guessed():
    workspace = create_workspace()
    try:
        autonomy.advance_on_wake(workspace, "invent_an_inundation_map")
    except ValueError as exc:
        assert "unknown wake kind" in str(exc)
    else:  # pragma: no cover - the raise is the behaviour under test
        raise AssertionError("an unknown wake kind must not be handled silently")


def test_the_receipt_reaches_the_public_view():
    assert "autonomy_proof" in public_view(create_workspace())


def test_the_public_view_does_not_leak_the_internal_tenant_field():
    workspace = create_workspace()
    workspace["_tenant_id"] = "t_secret"
    assert "_tenant_id" not in public_view(workspace)
