import json
from datetime import timedelta

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from spine.api_access import ApiKeyAuthenticator, ApiPrincipal, hash_api_key
from spine.api_key_store import MemoryApiKeyStore
from spine.developer_access import KeyIssuer, build_developer_router


def app_for(auth: ApiKeyAuthenticator) -> TestClient:
    app = FastAPI()

    @app.get("/v1/whoami")
    def whoami(principal: ApiPrincipal = Depends(auth)):
        return {"tenant_id": principal.tenant_id, "key_id": principal.key_id}

    return TestClient(app)


def test_key_resolves_server_controlled_tenant_and_openapi_security_scheme():
    auth = ApiKeyAuthenticator.from_plaintext({
        "dt_test_secret": {"tenant_id": "owner_one", "label": "Owner one", "scopes": ["downstream:use"]}
    })
    api = app_for(auth)
    response = api.get("/v1/whoami", headers={"X-API-Key": "dt_test_secret"})
    assert response.status_code == 200
    assert response.json()["tenant_id"] == "owner_one"
    assert "BetaApiKey" in api.get("/openapi.json").json()["components"]["securitySchemes"]


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_missing_or_wrong_key_is_unauthorized(headers):
    auth = ApiKeyAuthenticator.from_plaintext({
        "right": {"tenant_id": "tenant_one", "label": "One", "scopes": ["*"]}
    })
    assert app_for(auth).get("/v1/whoami", headers=headers).status_code == 401


def test_unprovisioned_beta_api_fails_closed():
    assert app_for(ApiKeyAuthenticator()).get("/v1/whoami").status_code == 503


def test_environment_contains_hashes_not_plaintext(monkeypatch):
    digest = hash_api_key("never-store-this")
    monkeypatch.setenv("BETA_API_KEY_HASHES", json.dumps({
        digest: {"tenant_id": "tenant_one", "label": "One", "scopes": ["*"]}
    }))
    auth = ApiKeyAuthenticator.from_environment()
    assert app_for(auth).get("/v1/whoami", headers={"X-API-Key": "never-store-this"}).status_code == 200


def developer_app(store, issuer):
    auth = ApiKeyAuthenticator(dynamic_lookup=store.get)
    app = FastAPI()
    app.include_router(build_developer_router(
        issuer, auth, product="Downstream", scope="downstream:use"
    ))

    @app.get("/v1/whoami")
    def whoami(principal: ApiPrincipal = Depends(auth)):
        return {"tenant_id": principal.tenant_id}

    return TestClient(app)


def test_invited_developer_can_issue_use_and_revoke_a_temporary_key():
    store = MemoryApiKeyStore("downstream")
    issuer = KeyIssuer(
        store,
        product="downstream",
        scope="downstream:use",
        prefix="ds_beta",
        invitation_hash=hash_api_key("invite-once"),
    )
    api = developer_app(store, issuer)
    issued = api.post("/developer/keys", json={
        "invitation_code": "invite-once",
        "label": "Owner two",
        "acknowledge_terms": True,
    })
    assert issued.status_code == 201
    body = issued.json()
    key = body["api_key"]
    assert key not in str(store.records)
    assert body["tenant_origin"] == "server_minted"
    assert api.get("/v1/whoami", headers={"X-API-Key": key}).json()["tenant_id"] == body["tenant_id"]
    assert api.delete("/v1/key", headers={"X-API-Key": key}).status_code == 200
    assert api.get("/v1/whoami", headers={"X-API-Key": key}).status_code == 401


def test_a_caller_cannot_choose_the_tenant_its_key_will_speak_for():
    """The flaw this replaces: one holder of a shared invitation code could name another
    holder's tenant in the request body and then read that tenant's workspaces."""
    store = MemoryApiKeyStore("downstream")
    issuer = KeyIssuer(
        store,
        product="downstream",
        scope="downstream:use",
        prefix="ds_beta",
        invitation_hash=hash_api_key("invite-once"),
    )
    api = developer_app(store, issuer)
    issued = api.post("/developer/keys", json={
        "invitation_code": "invite-once",
        "label": "Attacker",
        "tenant_id": "owner_one",
        "acknowledge_terms": True,
    })
    assert issued.status_code == 201
    assert issued.json()["tenant_id"] != "owner_one"


def test_two_redemptions_of_one_invitation_code_are_isolated_from_each_other():
    store = MemoryApiKeyStore("downstream")
    issuer = KeyIssuer(
        store,
        product="downstream",
        scope="downstream:use",
        prefix="ds_beta",
        invitation_hash=hash_api_key("invite-once"),
    )
    api = developer_app(store, issuer)
    tenants = set()
    for label in ("First team", "Second team"):
        issued = api.post("/developer/keys", json={
            "invitation_code": "invite-once",
            "label": label,
            "acknowledge_terms": True,
        })
        assert issued.status_code == 201
        tenants.add(issued.json()["tenant_id"])
    assert len(tenants) == 2


def test_invalid_invitation_cannot_issue_a_key_when_invite_only():
    store = MemoryApiKeyStore("downstream")
    issuer = KeyIssuer(
        store,
        product="downstream",
        scope="downstream:use",
        prefix="ds_beta",
        invitation_hash=hash_api_key("correct"),
        mode="invite_only",
    )
    api = developer_app(store, issuer)
    response = api.post("/developer/keys", json={
        "invitation_code": "wrong",
        "label": "Owner two",
        "acknowledge_terms": True,
    })
    assert response.status_code == 401
    assert store.records == {}


def test_open_issuance_needs_no_invitation_code():
    """A judge with no code still has to be able to see the API work."""
    store = MemoryApiKeyStore("downstream")
    issuer = KeyIssuer(
        store, product="downstream", scope="downstream:use", prefix="ds_beta"
    )
    api = developer_app(store, issuer)
    response = api.post("/developer/keys", json={
        "label": "Hackathon judge",
        "email": "judge@example.org",
        "organisation": "Devpost",
        "intended_use": "Evaluating the submission",
        "acknowledge_terms": True,
    })
    assert response.status_code == 201
    assert issuer.mode == "open"
    assert response.json()["tenant_origin"] == "server_minted"


def test_the_details_a_developer_supplies_are_stored_but_grant_nothing():
    store = MemoryApiKeyStore("downstream")
    issuer = KeyIssuer(
        store, product="downstream", scope="downstream:use", prefix="ds_beta"
    )
    api = developer_app(store, issuer)
    api.post("/developer/keys", json={
        "label": "Hackathon judge",
        "email": "judge@example.org",
        "organisation": "Devpost",
        "acknowledge_terms": True,
    })
    record = next(iter(store.records.values()))
    assert record["contact"]["email"] == "judge@example.org"
    assert record["contact"]["organisation"] == "Devpost"
    assert record["scopes"] == ["downstream:use"], "contact details must not widen scope"


def test_an_implausible_email_is_refused_before_a_key_exists():
    store = MemoryApiKeyStore("downstream")
    issuer = KeyIssuer(
        store, product="downstream", scope="downstream:use", prefix="ds_beta"
    )
    api = developer_app(store, issuer)
    response = api.post("/developer/keys", json={
        "label": "Judge", "email": "not-an-address", "acknowledge_terms": True,
    })
    assert response.status_code == 422
    assert store.records == {}


def test_email_is_optional():
    store = MemoryApiKeyStore("downstream")
    issuer = KeyIssuer(
        store, product="downstream", scope="downstream:use", prefix="ds_beta"
    )
    api = developer_app(store, issuer)
    assert api.post(
        "/developer/keys", json={"label": "Judge", "acknowledge_terms": True}
    ).status_code == 201


def test_issuance_can_still_be_switched_off_entirely():
    store = MemoryApiKeyStore("downstream")
    issuer = KeyIssuer(
        store, product="downstream", scope="downstream:use", prefix="ds_beta", mode="disabled"
    )
    api = developer_app(store, issuer)
    response = api.post(
        "/developer/keys", json={"label": "Judge", "acknowledge_terms": True}
    )
    assert response.status_code == 503
    assert store.records == {}


def test_expired_dynamic_key_is_rejected():
    store = MemoryApiKeyStore("downstream")
    key = "ds_beta_expired"
    store.issue(
        hash_api_key(key),
        tenant_id="owner_two",
        label="Owner two",
        scopes=["downstream:use"],
        issued_at=store.now - timedelta(hours=2),
        expires_at=store.now - timedelta(hours=1),
    )
    assert app_for(ApiKeyAuthenticator(dynamic_lookup=store.get)).get(
        "/v1/whoami", headers={"X-API-Key": key}
    ).status_code == 401


def test_dynamic_lookup_failure_fails_closed():
    def broken(_digest):
        raise RuntimeError("database unavailable")

    with pytest.raises(HTTPException) as failure:
        ApiKeyAuthenticator(dynamic_lookup=broken)("key")
    assert failure.value.status_code == 503
