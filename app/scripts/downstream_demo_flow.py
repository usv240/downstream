"""Executable judge rehearsal against local or deployed Downstream."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request


class API:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"{method} {path}: {exc.code} {exc.read().decode()}"
            ) from exc


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
    schema = api.call("GET", "/openapi.json")
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
