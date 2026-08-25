"""The developer page has to actually work for someone who arrives with nothing.

The failure this guards against is a page that documents an API nobody can reach: an invitation
gate with no way to get an invitation, a reference that drifts from the routes, or a console whose
script addresses elements the markup no longer has.
"""

import json
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from service.beta_routes import build_beta_router
from service.routes import build_router
from service.runtime import local_runtime
from spine.api_access import ApiKeyAuthenticator
from spine.developer_access import KeyIssuer, build_developer_router
from spine.quota import QuotaPolicy

WEB = Path(__file__).resolve().parents[1] / "web"
HTML = (WEB / "developer.html").read_text(encoding="utf-8")
JS = (WEB / "developer.js").read_text(encoding="utf-8")
PAGES = ("downstream.html", "developer.html", "downstream-judges-v2.html", "downstream-evidence.html")


# --------------------------------------------------------------------------- the page

def test_every_element_the_console_addresses_exists_in_the_markup():
    referenced = set(re.findall(r'\$\("#([a-zA-Z0-9_-]+)"\)', JS))
    present = set(re.findall(r'id="([a-zA-Z0-9_-]+)"', HTML))
    assert not referenced - present, f"script addresses missing elements: {sorted(referenced - present)}"


def test_the_key_is_reachable_from_every_public_page():
    """Reachable, not necessarily in the navigation bar.

    It lived in the bar until a sixth item wrapped the whole thing onto two rows at desktop
    width. On the landing page it now sits beside the primary action in the hero, which is both
    tidier and read sooner.
    """
    for name in PAGES:
        html = (WEB / name).read_text(encoding="utf-8")
        assert 'href="/developer"' in html or 'href="#create-key"' in html, name


def test_no_public_page_wraps_its_navigation_bar():
    """Five links fit on one row at desktop width. Six do not."""
    for name in PAGES:
        html = (WEB / name).read_text(encoding="utf-8")
        nav = re.search(r"<header.*?<nav[^>]*>(.*?)</nav>", html, re.S)
        assert nav, name
        links = re.findall(r"<a\s+[^>]*href=", nav.group(1))
        assert len(links) <= 5, f"{name} has {len(links)} nav links and will wrap"


def test_the_landing_hero_offers_the_key_beside_the_primary_action():
    landing = (WEB / "downstream.html").read_text(encoding="utf-8")
    row = landing[landing.index('<div class="btn-row">'):]
    row = row[: row.index("</div>")]
    assert "Run the guided demo" in row
    assert 'href="/developer"' in row, "the key should sit in the same button row"


def test_the_landing_page_explains_the_key_and_links_to_it():
    landing = (WEB / "downstream.html").read_text(encoding="utf-8")
    assert 'href="/developer"' in landing
    assert "API key" in landing


def test_the_console_offers_raw_and_formatted_views_and_a_reproducible_curl():
    for token in ("formatted-output", "raw-output", "headers-output", "curl-output"):
        assert f'id="{token}"' in HTML


def test_the_page_never_writes_a_credential_to_browser_storage():
    code = "".join(
        line for line in JS.splitlines(keepends=True)
        if not line.lstrip().startswith(("//", "*", "/*"))
    )
    for token in ("localStorage.", "sessionStorage.", "document.cookie"):
        assert token not in code


def test_the_page_documents_the_limits_and_the_boundary():
    assert "Daily limits" in HTML
    assert "X-RateLimit-Reset" in HTML
    for word in ("approves", "certifies", "submits"):
        assert word in HTML
    assert "inundation extent" in HTML


# --------------------------------------------------------------------------- the reference

def documented_paths() -> set[str]:
    """Paths named in the console's endpoint table, normalised of query strings."""
    return {
        path.split("?")[0]
        for path in re.findall(r'path:\s*"([^"]+)"', JS)
    }


def test_the_reference_documents_every_authenticated_route_the_service_exposes():
    app = FastAPI()
    runtime = local_runtime()
    auth = ApiKeyAuthenticator.from_plaintext(
        {"k": {"tenant_id": "tenant_one", "label": "One", "scopes": ["downstream:use"]}}
    )
    app.include_router(build_beta_router(runtime, auth))
    served = {
        path for path in app.openapi()["paths"] if path.startswith("/v1")
    }
    documented = documented_paths()
    missing = {p for p in served if p not in documented}
    assert not missing, f"routes the page never mentions: {sorted(missing)}"


def test_the_reference_invents_no_route_the_service_does_not_serve():
    app = FastAPI()
    runtime = local_runtime()
    auth = ApiKeyAuthenticator.from_plaintext(
        {"k": {"tenant_id": "tenant_one", "label": "One", "scopes": ["downstream:use"]}}
    )
    issuer = KeyIssuer(runtime.api_keys, product="downstream", scope="downstream:use", prefix="ds")
    app.include_router(build_router(runtime))
    app.include_router(build_beta_router(runtime, auth))
    app.include_router(
        build_developer_router(issuer, auth, product="Downstream", scope="downstream:use")
    )
    served = set(app.openapi()["paths"]) | {"/health", "/stack"}
    for path in documented_paths():
        assert path in served, f"the page documents {path}, which nothing serves"


# --------------------------------------------------------------------------- the journey

@pytest.fixture
def api(monkeypatch) -> TestClient:
    from downstream.registry import NIDResult

    monkeypatch.setattr(
        "service.beta_routes.lookup_nid_record",
        lambda nid_id: NIDResult(
            [{"NIDID": nid_id, "NAME": "Test Dam", "STATE": "Iowa", "HAZARD_POTENTIAL": "High"}],
            "https://example.test/nid",
            True,
            "public",
        ),
    )
    runtime = local_runtime(policy=QuotaPolicy())
    issuer = KeyIssuer(
        runtime.api_keys, product="downstream", scope="downstream:use", prefix="ds_beta"
    )
    auth = ApiKeyAuthenticator(dynamic_lookup=runtime.api_keys.get)
    app = FastAPI()
    app.include_router(build_router(runtime))
    app.include_router(build_beta_router(runtime, auth))
    app.include_router(
        build_developer_router(
            issuer,
            auth,
            product="Downstream",
            scope="downstream:use",
            issuance_quota=runtime.key_issuance_quota,
            attempt_quota=runtime.invitation_attempt_quota,
            policy=runtime.policy,
        )
    )
    return TestClient(app)


def mint(api: TestClient, label: str = "Judge") -> dict:
    response = api.post(
        "/developer/keys",
        json={"label": label, "email": "judge@example.org", "acknowledge_terms": True},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_a_judge_with_nothing_can_get_a_working_key(api):
    key = mint(api)
    assert key["tenant_origin"] == "server_minted"
    assert api.get("/v1", headers={"X-API-Key": key["api_key"]}).status_code == 200


def test_the_issuance_response_says_how_many_keys_are_left(api):
    key = mint(api)
    assert key["keys_remaining_today"] == QuotaPolicy().key_issuances_per_day - 1
    assert key["allowance_resets_at"]


def test_the_daily_key_allowance_is_generous_enough_for_thorough_testing(api):
    assert QuotaPolicy().key_issuances_per_day >= 50
    assert QuotaPolicy().api_calls_per_day >= 1000


def test_the_full_console_sequence_succeeds_end_to_end(api):
    """Exactly the eight calls the page's 'Run the whole sequence' button performs."""
    headers = {"X-API-Key": mint(api)["api_key"]}

    created = api.post("/v1/workspaces", json={"nid_id": "IA03081"}, headers=headers)
    assert created.status_code == 201
    workspace = created.json()
    wid = workspace["workspace_id"]
    qid = workspace["next_question"]["id"]

    assert api.post(
        f"/v1/workspaces/{wid}/answer",
        json={"question_id": qid, "answer": "The service road washes out at the low crossing."},
        headers=headers,
    ).status_code == 200
    assert api.post(
        f"/v1/workspaces/{wid}/skip", json={"question_id": "emergency_manager"}, headers=headers
    ).status_code == 200
    assert api.post(
        f"/v1/workspaces/{wid}/answers/{qid}/revise",
        json={"revised_answer": "Only the low crossing washes out.", "reason": "Narrowed it."},
        headers=headers,
    ).status_code == 200
    assert api.post(
        f"/v1/workspaces/{wid}/feedback",
        json={"action": "not_right", "reason": "Too much detail"},
        headers=headers,
    ).status_code == 200

    resumed = api.post(f"/v1/workspaces/{wid}/resume", headers=headers).json()
    assert "emergency_manager" in resumed["sessions"][-1]["reopened_questions"]

    receipt = api.get(f"/v1/workspaces/{wid}/autonomy", headers=headers).json()
    assert receipt["continue_clicks_required"] == 0
    assert receipt["automatic_agent_steps"] > receipt["human_authority_steps"]

    final = api.get(f"/v1/workspaces/{wid}", headers=headers).json()
    assert final["answers"][qid]["version"] == 2
    assert len(final["answers"][qid]["history"]) == 2
    assert final["profile"]["detail_preference"] == "terse"
    assert final["mapping"]["may_render_extent"] is False


def test_two_self_service_keys_cannot_see_each_other(api):
    first = mint(api, "First judge")
    second = mint(api, "Second judge")
    assert first["tenant_id"] != second["tenant_id"]
    wid = api.post(
        "/v1/workspaces", json={"nid_id": "IA03081"},
        headers={"X-API-Key": first["api_key"]},
    ).json()["workspace_id"]
    assert api.get(
        f"/v1/workspaces/{wid}", headers={"X-API-Key": second["api_key"]}
    ).status_code == 404


def test_a_key_stops_working_the_moment_it_is_revoked(api):
    headers = {"X-API-Key": mint(api)["api_key"]}
    assert api.delete("/v1/key", headers=headers).status_code == 200
    assert api.get("/v1", headers=headers).status_code == 401


def test_the_config_the_page_reads_matches_what_the_service_enforces(api):
    config = api.get("/developer/config").json()
    assert config["issuance"] == "open"
    assert config["requires_invitation"] is False
    assert config["quotas"]["key_issuances_per_network_per_day"] == QuotaPolicy().key_issuances_per_day
    assert config["quotas"]["api_calls_per_key_per_day"] == QuotaPolicy().api_calls_per_day


def endpoint_table() -> str:
    """Just the ENDPOINTS declaration, not the code that later builds requests from it."""
    start = JS.index("const ENDPOINTS = [")
    end = JS.index("/* ---", start)
    return JS[start:end]


def test_the_example_bodies_shown_on_the_page_are_valid_json():
    bodies = re.findall(r"body:\s*(\{[^}]*\})", endpoint_table())
    assert bodies, "the reference should carry at least one example body"
    for match in bodies:
        normalised = re.sub(r"(\w+):", r'"\1":', match).replace("'", '"')
        normalised = normalised.replace('"false"', "false").replace('"true"', "true")
        assert json.loads(normalised), "an example body must not be empty"


def test_every_documented_endpoint_carries_a_summary_and_an_explanation():
    table = endpoint_table()
    assert table.count("summary:") == table.count("path:")
    assert table.count("detail:") == table.count("path:")


def test_health_and_developer_config_agree_about_issuance(monkeypatch):
    """These drifted in production once: health said invite_only while config said open."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "local")
    monkeypatch.delenv("USE_FIRESTORE", raising=False)
    monkeypatch.setenv("DEVELOPER_ISSUANCE_MODE", "open")
    import importlib

    import service.main as main

    importlib.reload(main)
    client = TestClient(main.app)
    assert (
        client.get("/health").json()["developer_key_issuance"]
        == client.get("/developer/config").json()["issuance"]
    )
