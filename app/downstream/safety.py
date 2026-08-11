"""Safety gates for mapping and regulatory output."""

from __future__ import annotations

from dataclasses import dataclass

SCREENING_DISCLOSURE = (
    "No inundation boundary has been generated. The displayed path is a documented flow-path "
    "input, not a flood extent, arrival-time estimate, evacuation zone, or engineering analysis."
)

DRAFT_DISCLOSURE = (
    "Draft for owner, emergency manager, and state dam-safety review. It is not approved, "
    "certified, or submitted. It is not a substitute for jurisdiction-specific engineering judgment."
)


@dataclass(frozen=True)
class MappingDecision:
    status: str
    may_render_extent: bool
    reason: str
    next_step: str
    disclosure: str = SCREENING_DISCLOSURE


def mapping_gate(
    *,
    approved_map_supplied: bool,
    method_applicable: bool,
    jurisdiction_accepts: bool,
    reference_comparison_passed: bool,
) -> MappingDecision:
    if approved_map_supplied:
        return MappingDecision(
            status="approved_map_supplied",
            may_render_extent=True,
            reason="The owner supplied an approved map with reviewable provenance.",
            next_step="Verify its date, authority, limitations, and downstream contacts.",
        )
    failed = []
    if not method_applicable:
        failed.append("published method applicability is unproven")
    if not jurisdiction_accepts:
        failed.append("jurisdictional acceptance is unproven")
    if not reference_comparison_passed:
        failed.append("reference-map comparison has not passed")
    if failed:
        return MappingDecision(
            status="safe_stop",
            may_render_extent=False,
            reason="; ".join(failed),
            next_step="Request an approved map or route this section to a qualified reviewer.",
        )
    return MappingDecision(
        status="validated_screening_method",
        may_render_extent=True,
        reason="All documented simplified-method gates passed.",
        next_step="Render with assumptions, comparison results, and screening disclosure.",
    )
