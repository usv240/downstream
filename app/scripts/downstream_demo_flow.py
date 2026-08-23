"""Executable judge rehearsal against local or deployed Downstream."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request


class API:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.last_headers: dict[str, str] = {}

    def call(
        self, method: str, path: str, body: dict | None = None, key: str | None = None
    ) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"}
        if key:
            headers["X-API-Key"] = key
        request = urllib.request.Request(
            self.base + path, data=data, method=method, headers=headers
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                self.last_headers = {k.lower(): v for k, v in response.headers.items()}
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"{method} {path}: {exc.code} {exc.read().decode()}"
            ) from exc

    def status(self, method: str, path: str, key: str | None = None) -> int:
        """The status code alone, for routes whose refusal is the thing being checked."""
        headers = {"X-API-Key": key} if key else {}
        request = urllib.request.Request(self.base + path, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status
        except urllib.error.HTTPError as exc:
            return exc.code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8087")
    args = parser.parse_args()
    api = API(args.url)
    checks: list[bool] = []

    def check(label: str, condition: bool) -> None:
        checks.append(bool(condition))
        print(f"{'PASS' if condition else 'FAIL'}  {label}")

    health = api.call("GET", "/health")
    check("standalone service healthy", health.get("project") == "downstream")
    check("health discloses synthetic demo", health.get("synthetic_demo") is True)
    check(
        "health discloses no inundation extent",
        health.get("inundation_extent") == "not_generated",
    )

    research = api.call("GET", "/downstream/research")
    check(
        "current NID snapshot measured",
        research["measured_snapshot"]["total_records"] == 92606,
    )
    check(
        "null-field interpretation is bounded",
        "unreported" in research["claim_boundary"],
    )

    workspace = api.call("POST", "/downstream/workspaces", {})
    workspace_id = workspace["workspace_id"]
    check("preset is synthetic", workspace["dam"]["synthetic"] is True)
    check(
        "drawing conflict is surfaced",
        any(fact["status"] == "conflict" for fact in workspace["facts"]),
    )
    check(
        "only one owner question is presented",
        workspace["next_question"]["id"] == "access_heavy_rain",
    )
    check(
        "context starts inside its hard bound",
        workspace["context_meter"]["within_bound"] is True,
    )

    first = workspace["next_question"]
    workspace = api.call(
        "POST",
        f"/downstream/workspaces/{workspace_id}/answer",
        {
            "question_id": first["id"],
            "answer": "Please explain this term.",
            "did_not_understand": True,
        },
    )
    check("feedback changes profile", workspace["profile"]["reading_level"] == "plain")
    check(
        "same unresolved question is re-asked plainly",
        workspace["next_question"]["id"] == first["id"]
        and workspace["next_question"]["text"] == workspace["next_question"]["plain"]
        and bool(workspace["next_question"].get("gloss")),
    )
    workspace = api.call(
        "POST",
        f"/downstream/workspaces/{workspace_id}/answer",
        {
            "question_id": first["id"],
            "answer": "The gravel lane washes out at the second bend.",
        },
    )
    check(
        "answer becomes a structured owner fact",
        workspace["answers"][first["id"]]["provenance"] == "owner",
    )

    for index in range(4):
        question = workspace["next_question"]
        workspace = api.call(
            "POST",
            f"/downstream/workspaces/{workspace_id}/answer",
            {
                "question_id": question["id"],
                "answer": f"Synthetic owner fact {index + 2}",
            },
        )
    conflict = workspace["next_question"]
    check(
        "retrieved-source conflict becomes a targeted clarification",
        conflict["id"] == "resolve_dam_height_conflict"
        and conflict["basis"] == "unresolved_source_conflict",
    )
    workspace = api.call(
        "POST",
        f"/downstream/workspaces/{workspace_id}/skip",
        {"question_id": conflict["id"]},
    )
    check(
        "dynamic source conflict can be held without losing prior answers",
        workspace["next_question"] is None
        and workspace["progress"]["skipped"] == 1
        and len(workspace["answers"]) == 5,
    )
    workspace = api.call(
        "POST", f"/downstream/workspaces/{workspace_id}/resume", {}
    )
    conflict = workspace["next_question"]
    check(
        "new session reopens the held source conflict",
        conflict["id"] == "resolve_dam_height_conflict"
        and workspace["progress"]["skipped"] == 0,
    )
    workspace = api.call(
        "POST",
        f"/downstream/workspaces/{workspace_id}/answer",
        {
            "question_id": conflict["id"],
            "answer": "Use 31 feet only after the engineer confirms the legacy drawing.",
        },
    )
    check(
        "partner completes without repeating a question",
        workspace["progress"]["answered"] == 6 and workspace["next_question"] is None,
    )
    height = next(fact for fact in workspace["facts"] if fact["key"] == "dam_height_ft")
    check(
        "owner context does not falsely resolve the source conflict",
        height["status"] == "owner_response_recorded"
        and "qualified-engineer" in height["resolution"],
    )
    workspace = api.call(
        "POST",
        f"/downstream/workspaces/{workspace_id}/answers/access_heavy_rain/revise",
        {
            "revised_answer": "The east lane washes out at the second bend.",
            "reason": "Owner corrected the access location.",
        },
    )
    preparedness = next(
        row for row in workspace["plan"] if row["key"] == "preparedness"
    )
    check(
        "owner correction changes the draft and preserves history",
        workspace["adaptation"]["answer_revisions"] == 1
        and preparedness["text"].startswith("The east lane"),
    )
    audit = api.call("GET", f"/downstream/workspaces/{workspace_id}/audit")
    check(
        "every rendered section publishes an evidence class",
        all(row["rendered_from_evidence"] for row in audit["evidence_ledger"]),
    )
    check(
        "mapping remains blocked after plan completion",
        workspace["mapping"]["may_render_extent"] is False,
    )
    check("draft carries review boundary", "not approved" in workspace["disclosure"])

    before = workspace["context_meter"]["structured_context_tokens"]
    for _ in range(4):
        workspace = api.call(
            "POST", f"/downstream/workspaces/{workspace_id}/resume", {}
        )
    check(
        "resume retains all six facts and the revision",
        len(workspace["answers"]) == 6
        and workspace["adaptation"]["answer_revisions"] == 1,
    )
    check(
        "context does not grow with empty sessions",
        workspace["context_meter"]["structured_context_tokens"] == before,
    )

    bonus = api.call("GET", "/downstream/bonus")
    check(
        "recorded Gemma privacy layer leaks no returned identifier",
        bonus["identifiers_leaked_in_replay"] == []
        and bonus["measured"]["recall"] == {"found": 4, "expected": 4},
    )
    proof = api.call("GET", "/downstream/proof")
    check("executable safety proof is all green", proof["passed"] == proof["total"])

    # --- Autonomy -----------------------------------------------------------------------
    # The claim under check is narrow: the agent runs every in-scope transition itself and
    # stops only where a person or the outside world has to supply something.
    receipt = api.call("GET", f"/downstream/workspaces/{workspace_id}/autonomy")
    check(
        "the opening sequence ran without a human step",
        receipt["timeline"][0]["step"] == "run_triggered"
        and receipt["timeline"][0]["actor"] == "external_evidence",
    )
    check(
        "the agent does more automatically than it asks of a person",
        receipt["automatic_agent_steps"] > receipt["human_authority_steps"],
    )
    check("no continue click is required", receipt["continue_clicks_required"] == 0)
    check(
        "reserved authority is declared and never exercised",
        receipt["system_decisions_over_reserved_authority"] == 0
        and len(receipt["authority_reserved"]) == 4,
    )
    check(
        "the source conflict was derived, not hardcoded",
        any(step["step"] == "source_conflict_detected" for step in receipt["timeline"]),
    )
    check("durable wakes were registered on open", receipt["durable_wakes_registered"] == 2)

    single = api.call("POST", "/downstream/demo/run")
    check(
        "one request reaches a reviewable draft",
        single["autonomy_proof"]["continue_clicks_required"] == 0
        and len(single["plan"]) == 6,
    )
    check(
        "the agent asked every question including the conflict",
        single["questions_asked_by_the_agent"][-1] == "resolve_dam_height_conflict",
    )
    check(
        "scheduled actions really fired",
        sorted(single["scheduled_actions_fired"])
        == ["reopen_held_questions", "unanswered_question_nudge"],
    )
    check("the rehearsal admits its clock was moved", "simulated" in single["clock"])
    check("the rehearsal admits its owner answers are synthetic", single["synthetic_owner_answers"])
    check(
        "no inundation extent is produced however complete the run",
        single["mapping"]["may_render_extent"] is False,
    )

    # --- Truthful reporting -------------------------------------------------------------
    stack = api.call("GET", "/stack")
    reported = {row["service"]: row for row in stack["request_path"]}
    check("the service reports its own stack", "Cloud Run" in reported)
    check(
        "a replayed model is never reported as being in the request path",
        reported["Vertex AI Gemini 3.5 Flash"]["active"]
        == (health["model_execution"] == "live_with_replay_fallback"),
    )
    check(
        "tracing is reported from the process, not asserted by the page",
        reported["Cloud Trace"]["active"] == (health["tracing"] == "cloud_trace"),
    )
    check(
        "Gemma is published as a recording rather than a live call",
        stack["additional_google_ai"][0]["active"] is False,
    )
    check("published limits exist and are non-zero", all(v > 0 for v in stack["quotas"].values()))

    # --- Abuse control ------------------------------------------------------------------
    check(
        "the scheduler route refuses an unauthenticated trigger",
        api.status("POST", "/internal/scan-due") in {401, 503},
    )
    check(
        "an unauthenticated /v1 call is refused",
        api.status("GET", "/v1") == 401,
    )

    # --- Self-service developer key ------------------------------------------------------
    # A judge arrives with nothing. They must be able to get a key and drive the whole API.
    config = api.call("GET", "/developer/config")
    check("key issuance is self-service", config["issuance"] == "open")
    check("no invitation code is required", config["requires_invitation"] is False)
    check(
        "the published allowance is generous enough to test with",
        config["quotas"]["key_issuances_per_network_per_day"] >= 50
        and config["quotas"]["api_calls_per_key_per_day"] >= 1000,
    )

    issued = api.call("POST", "/developer/keys", {
        "label": "Executable judge rehearsal",
        "email": "rehearsal@example.org",
        "intended_use": "Automated end-to-end check",
        "acknowledge_terms": True,
    })
    key = issued["api_key"]
    check("a key is issued without an invitation", bool(key))
    check("the tenant is minted by the server", issued["tenant_origin"] == "server_minted")
    check("the response says how many keys remain", "keys_remaining_today" in issued)

    second = api.call("POST", "/developer/keys", {
        "label": "Second rehearsal key", "acknowledge_terms": True,
    })
    check(
        "two self-service keys land in different tenants",
        second["tenant_id"] != issued["tenant_id"],
    )

    identifiers = api.call("GET", "/downstream/nid/search?limit=1&state=IA")["records"]
    nid = identifiers[0]["NIDID"] if identifiers else None
    check("a live public identifier is discoverable", bool(nid))

    owned = api.call("POST", "/v1/workspaces", {"nid_id": nid}, key=key)
    api_workspace = owned["workspace_id"]
    question = owned["next_question"]["id"]
    check("the key opens a workspace from a real record", owned["dam"]["synthetic"] is False)
    check(
        "every authenticated response reports the remaining budget",
        api.last_headers.get("x-ratelimit-remaining") is not None,
    )

    api.call("POST", f"/v1/workspaces/{api_workspace}/answer",
             {"question_id": question, "answer": "The service road washes out at the low crossing."},
             key=key)
    api.call("POST", f"/v1/workspaces/{api_workspace}/skip",
             {"question_id": "emergency_manager"}, key=key)
    api.call("POST", f"/v1/workspaces/{api_workspace}/answers/{question}/revise",
             {"revised_answer": "Only the low crossing washes out.", "reason": "Owner narrowed it."},
             key=key)
    api.call("POST", f"/v1/workspaces/{api_workspace}/feedback",
             {"action": "not_right", "reason": "Too much detail"}, key=key)
    resumed = api.call("POST", f"/v1/workspaces/{api_workspace}/resume", key=key)
    receipt = api.call("GET", f"/v1/workspaces/{api_workspace}/autonomy", key=key)
    final = api.call("GET", f"/v1/workspaces/{api_workspace}", key=key)

    check("the API resume reopens a held question",
          "emergency_manager" in resumed["sessions"][-1]["reopened_questions"])
    check("the API revision keeps both versions",
          final["answers"][question]["version"] == 2
          and len(final["answers"][question]["history"]) == 2)
    check("API feedback changes the profile", final["profile"]["detail_preference"] == "terse")
    check("the API publishes an autonomy receipt",
          receipt["continue_clicks_required"] == 0
          and receipt["automatic_agent_steps"] > receipt["human_authority_steps"])
    check("the API still refuses to render an extent",
          final["mapping"]["may_render_extent"] is False)
    check("another key cannot read this workspace",
          api.status("GET", f"/v1/workspaces/{api_workspace}",
                     key=second["api_key"]) == 404)

    api.call("DELETE", "/v1/key", key=second["api_key"])
    api.call("DELETE", "/v1/key", key=key)
    check("a revoked key stops working immediately", api.status("GET", "/v1", key=key) == 401)

    schema = api.call("GET", "/openapi.json")
    check(
        "the scheduler surface stays out of the public schema",
        not any(path.startswith("/internal") for path in schema["paths"]),
    )
    check(
        "no approve, certify, or submit endpoint exists",
        not any(
            any(word in path for word in ("approve", "certify", "submit"))
            for path in schema["paths"]
        ),
    )

    print(
        f"\n{sum(checks)}/{len(checks)} Downstream demo checks passed against {args.url}"
    )
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
