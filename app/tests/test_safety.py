import pytest

from downstream.safety import DRAFT_DISCLOSURE, SCREENING_DISCLOSURE, mapping_gate


@pytest.mark.parametrize(
    "applicable,accepted,compared,missing",
    [
        (False, True, True, "applicability"),
        (True, False, True, "jurisdictional"),
        (True, True, False, "reference-map"),
        (False, False, False, "applicability"),
    ],
)
def test_any_missing_validation_gate_stops_extent(applicable, accepted, compared, missing):
    decision = mapping_gate(
        approved_map_supplied=False,
        method_applicable=applicable,
        jurisdiction_accepts=accepted,
        reference_comparison_passed=compared,
    )
    assert decision.status == "safe_stop"
    assert decision.may_render_extent is False
    assert missing in decision.reason


def test_all_simplified_method_gates_must_pass():
    decision = mapping_gate(
        approved_map_supplied=False,
        method_applicable=True,
        jurisdiction_accepts=True,
        reference_comparison_passed=True,
    )
    assert decision.may_render_extent is True
    assert decision.status == "validated_screening_method"


def test_approved_map_path_preserves_review_step():
    decision = mapping_gate(
        approved_map_supplied=True,
        method_applicable=False,
        jurisdiction_accepts=False,
        reference_comparison_passed=False,
    )
    assert decision.may_render_extent is True
    assert "date" in decision.next_step
    assert "limitations" in decision.next_step


def test_disclosures_do_not_claim_approval_or_engineering_analysis():
    assert "No inundation boundary" in SCREENING_DISCLOSURE
    assert "not approved" in DRAFT_DISCLOSURE
    assert "not a substitute" in DRAFT_DISCLOSURE


def test_safe_stop_gives_an_action_not_only_a_warning():
    decision = mapping_gate(
        approved_map_supplied=False,
        method_applicable=False,
        jurisdiction_accepts=False,
        reference_comparison_passed=False,
    )
    assert "Request" in decision.next_step
    assert "qualified reviewer" in decision.next_step
