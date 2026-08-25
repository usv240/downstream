"""The ceilings that did not exist before.

Downstream shipped with no rate limiting of any kind: unlimited invitation-code guesses against
`/developer/keys`, and unlimited unauthenticated Firestore writes through the public judge route.
These tests pin the behaviour that replaces it.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from spine.quota import (
    MemoryQuotaStore,
    NetworkFingerprint,
    QuotaGuard,
    QuotaPolicy,
    utc_day,
)

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def guard() -> QuotaGuard:
    return QuotaGuard(
        MemoryQuotaStore(), NetworkFingerprint("pepper"), name="test", limit=3
    )


def test_the_ceiling_admits_exactly_its_limit(guard):
    assert [guard.check("bucket", NOW).allowed for _ in range(4)] == [True, True, True, False]


def test_remaining_counts_down_and_reaches_zero(guard):
    assert [guard.check("bucket", NOW).remaining for _ in range(3)] == [2, 1, 0]


def test_separate_buckets_do_not_share_an_allowance(guard):
    for _ in range(3):
        guard.check("one", NOW)
    assert guard.check("two", NOW).allowed


def test_the_allowance_resets_at_utc_midnight(guard):
    for _ in range(3):
        guard.check("bucket", NOW)
    assert not guard.check("bucket", NOW).allowed
    assert guard.check("bucket", NOW + timedelta(days=1)).allowed


def test_a_refusal_is_a_429_carrying_the_reset_time(guard):
    for _ in range(3):
        guard.check("bucket", NOW)
    with pytest.raises(Exception) as raised:
        guard.enforce("bucket", "no more today", NOW)
    assert raised.value.status_code == 429
    assert raised.value.headers["X-RateLimit-Remaining"] == "0"
    assert raised.value.headers["X-RateLimit-Reset"].startswith("2026-08-24")


def test_reset_day_is_utc_not_local():
    assert utc_day(datetime(2026, 8, 23, 23, 59, tzinfo=timezone.utc)) == "2026-08-23"
    assert utc_day(datetime(2026, 8, 24, 0, 1, tzinfo=timezone.utc)) == "2026-08-24"


def fingerprint_app(fingerprint: NetworkFingerprint) -> TestClient:
    app = FastAPI()

    @app.get("/who")
    def who(request: Request) -> dict[str, str]:
        return {"address": fingerprint.client_address(request), "bucket": fingerprint.of(request)}

    return TestClient(app)


def test_a_caller_cannot_mint_a_fresh_bucket_by_prepending_a_forwarded_header():
    """`X-Forwarded-For` is caller-controlled at the head. Only the tail is a proxy's word."""
    api = fingerprint_app(NetworkFingerprint("pepper", trusted_proxy_hops=1))
    honest = api.get("/who", headers={"X-Forwarded-For": "203.0.113.9"}).json()
    spoofed = api.get(
        "/who", headers={"X-Forwarded-For": "10.9.9.9, 198.51.100.4, 203.0.113.9"}
    ).json()
    assert honest["address"] == "203.0.113.9"
    assert spoofed["address"] == "203.0.113.9"
    assert honest["bucket"] == spoofed["bucket"]


def test_the_stored_bucket_key_is_not_the_address():
    api = fingerprint_app(NetworkFingerprint("pepper"))
    body = api.get("/who", headers={"X-Forwarded-For": "203.0.113.9"}).json()
    assert "203.0.113.9" not in body["bucket"]
    assert len(body["bucket"]) == 32


def test_two_deployments_with_different_peppers_cannot_correlate_a_caller():
    first = fingerprint_app(NetworkFingerprint("pepper-one"))
    second = fingerprint_app(NetworkFingerprint("pepper-two"))
    headers = {"X-Forwarded-For": "203.0.113.9"}
    assert first.get("/who", headers=headers).json()["bucket"] != (
        second.get("/who", headers=headers).json()["bucket"]
    )


def test_published_policy_and_enforced_limits_come_from_one_place():
    policy = QuotaPolicy(public_workspaces_per_day=7)
    assert policy.as_public_dict()["public_workspaces_per_network_per_day"] == 7


def test_policy_ignores_a_nonsense_environment_value(monkeypatch):
    monkeypatch.setenv("QUOTA_PUBLIC_WORKSPACES_PER_DAY", "not-a-number")
    assert QuotaPolicy.from_environment().public_workspaces_per_day == 500
    monkeypatch.setenv("QUOTA_PUBLIC_WORKSPACES_PER_DAY", "0")
    assert QuotaPolicy.from_environment().public_workspaces_per_day == 500


def test_the_quota_store_reports_when_it_fails_open():
    """Failing open is the right call; failing open silently is not.

    google-api-core 2.35.0 broke every Firestore transaction in this service. Workspace creation
    returned 500 loudly, which is how it was found -- but the quota store swallowed the same
    exception and kept admitting requests with no signal anywhere. A ceiling that has stopped
    counting has to say so.
    """
    class BrokenStore:
        def consume(self, bucket, day, limit, now):
            raise RuntimeError("400 Invalid database id %28default%29")

    guard = QuotaGuard(BrokenStore(), NetworkFingerprint("pepper"), name="test", limit=3)
    verdict = guard.check("bucket", NOW)
    assert verdict.allowed is True, "an outage must not take the product down"
    assert verdict.degraded is True, "but it must be visible that the ceiling is not counting"
