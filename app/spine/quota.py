"""Daily call and issuance ceilings.

Downstream ran with no ceiling at all: `/developer/keys` accepted unlimited invitation-code
guesses, and the public judge route wrote an unbounded number of Firestore documents for anyone
who could hold down a key. Both are cheap to abuse and expensive to own.

Three properties matter here:

* **The counter is atomic.** Two concurrent requests cannot both read 49 and both write 50.
  Firestore transactions provide that; the memory store uses a lock for the same reason.
* **A raw client IP is never stored.** What lands in Firestore is an HMAC of the address under a
  server-held pepper, so the document is a stable bucket key and not a location record.
* **A caller cannot forge a fresh bucket.** `X-Forwarded-For` is attacker-controlled at the head
  and proxy-controlled at the tail, so only the tail is trusted.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from fastapi import HTTPException, Request


def utc_day(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")


def _next_utc_midnight(now: datetime) -> datetime:
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


@dataclass(frozen=True)
class QuotaVerdict:
    allowed: bool
    limit: int
    used: int
    resets_at: str
    # True when the backend could not be reached and this verdict is a fail-open guess rather
    # than a count. Failing open is the right call; failing open silently is not -- a transitive
    # dependency once broke every Firestore transaction here and the ceiling stopped counting
    # with no signal anywhere, because the exception was swallowed and never surfaced.
    degraded: bool = False

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    def headers(self) -> dict[str, str]:
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": self.resets_at,
        }
        if self.degraded:
            headers["X-RateLimit-Degraded"] = "true"
        return headers


class QuotaStore(Protocol):
    def consume(self, bucket: str, day: str, limit: int, now: datetime) -> QuotaVerdict: ...


class MemoryQuotaStore:
    """Per-process ceiling. Correct for a single instance, and for every local test."""

    def __init__(self) -> None:
        self._counts: dict[tuple[str, str], int] = {}
        self._lock = threading.Lock()

    def consume(self, bucket: str, day: str, limit: int, now: datetime) -> QuotaVerdict:
        resets_at = _next_utc_midnight(now).isoformat()
        with self._lock:
            used = self._counts.get((bucket, day), 0)
            if used >= limit:
                return QuotaVerdict(False, limit, used, resets_at)
            self._counts[(bucket, day)] = used + 1
            return QuotaVerdict(True, limit, used + 1, resets_at)


class FirestoreQuotaStore:
    """Cross-instance ceiling. Cloud Run runs many containers; the counter must be shared."""

    def __init__(self, client, collection: str = "downstream_quota") -> None:
        self._client = client
        self._collection = client.collection(collection)

    def consume(self, bucket: str, day: str, limit: int, now: datetime) -> QuotaVerdict:
        from google.cloud import firestore

        ref = self._collection.document(f"{day}__{bucket}")
        resets_at = _next_utc_midnight(now).isoformat()

        @firestore.transactional
        def bump(txn) -> tuple[bool, int]:
            snapshot = ref.get(transaction=txn)
            used = int((snapshot.to_dict() or {}).get("count", 0)) if snapshot.exists else 0
            if used >= limit:
                return False, used
            txn.set(
                ref,
                {"count": used + 1, "day": day, "bucket": bucket, "reset_at": resets_at},
                merge=True,
            )
            return True, used + 1

        try:
            allowed, used = bump(self._client.transaction())
        except Exception:
            # A quota backend outage must not take the product down. Fail open, but say so: a
            # silent fail-open is indistinguishable from a working ceiling right up until the
            # bill arrives.
            return QuotaVerdict(True, limit, 0, resets_at, degraded=True)
        return QuotaVerdict(allowed, limit, used, resets_at)


class NetworkFingerprint:
    """A stable, non-reversible bucket key for one caller network."""

    def __init__(self, pepper: str, trusted_proxy_hops: int = 1) -> None:
        self._pepper = pepper.encode("utf-8")
        self._hops = max(1, trusted_proxy_hops)

    @classmethod
    def from_environment(cls) -> "NetworkFingerprint":
        pepper = os.environ.get("QUOTA_FINGERPRINT_PEPPER", "").strip()
        if not pepper:
            # Per-process pepper. Buckets stay consistent for the life of the instance and are
            # unlinkable across deployments, which is the right default when no secret is set.
            pepper = hashlib.sha256(os.urandom(32)).hexdigest()
        try:
            hops = int(os.environ.get("TRUSTED_PROXY_HOPS", "1"))
        except ValueError:
            hops = 1
        return cls(pepper, hops)

    def client_address(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            chain = [part.strip() for part in forwarded.split(",") if part.strip()]
            if chain:
                # The head is caller-supplied and can be invented. Count back from the tail,
                # which only a proxy we actually sit behind can write.
                index = max(0, len(chain) - self._hops)
                return chain[index]
        return request.client.host if request.client else "unknown"

    def of(self, request: Request) -> str:
        address = self.client_address(request)
        return hmac.new(self._pepper, address.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


class QuotaGuard:
    """One ceiling, applied to one named bucket family."""

    def __init__(
        self,
        store: QuotaStore,
        fingerprint: NetworkFingerprint,
        *,
        name: str,
        limit: int,
    ) -> None:
        self._store = store
        self._fingerprint = fingerprint
        self.name = name
        self.limit = limit

    def check(self, bucket: str, now: datetime | None = None) -> QuotaVerdict:
        at = now or datetime.now(timezone.utc)
        try:
            return self._store.consume(f"{self.name}:{bucket}", utc_day(at), self.limit, at)
        except Exception:
            # The Firestore store already fails open internally; this catches a store that does
            # not, so a counting outage can never become a 500 on the product path either.
            return QuotaVerdict(
                True, self.limit, 0, _next_utc_midnight(at).isoformat(), degraded=True
            )

    def enforce(self, bucket: str, detail: str, now: datetime | None = None) -> QuotaVerdict:
        verdict = self.check(bucket, now)
        if not verdict.allowed:
            raise HTTPException(status_code=429, detail=detail, headers=verdict.headers())
        return verdict

    def enforce_network(self, request: Request, detail: str) -> QuotaVerdict:
        return self.enforce(self._fingerprint.of(request), detail)


@dataclass(frozen=True)
class QuotaPolicy:
    """Every ceiling in one place, so the published numbers and the code cannot drift."""

    # Sized so a judge testing thoroughly never hits a wall. The ceilings exist to stop a
    # runaway script, not to ration honest use. Live model calls stay tight because they are
    # the only line item that costs real money per request.
    public_workspaces_per_day: int = 500
    api_calls_per_day: int = 1000
    key_issuances_per_day: int = 50
    invitation_attempts_per_day: int = 200
    live_model_calls_per_day: int = 25

    @classmethod
    def from_environment(cls) -> "QuotaPolicy":
        def read(name: str, default: int) -> int:
            try:
                value = int(os.environ.get(name, default))
            except ValueError:
                return default
            return value if value > 0 else default

        return cls(
            public_workspaces_per_day=read("QUOTA_PUBLIC_WORKSPACES_PER_DAY", 500),
            api_calls_per_day=read("QUOTA_API_CALLS_PER_DAY", 1000),
            key_issuances_per_day=read("QUOTA_KEY_ISSUANCES_PER_DAY", 50),
            invitation_attempts_per_day=read("QUOTA_INVITE_ATTEMPTS_PER_DAY", 200),
            live_model_calls_per_day=read("QUOTA_LIVE_MODEL_CALLS_PER_DAY", 25),
        )

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "public_workspaces_per_network_per_day": self.public_workspaces_per_day,
            "api_calls_per_key_per_day": self.api_calls_per_day,
            "key_issuances_per_network_per_day": self.key_issuances_per_day,
            "invitation_attempts_per_network_per_day": self.invitation_attempts_per_day,
            "live_model_calls_per_day": self.live_model_calls_per_day,
        }
