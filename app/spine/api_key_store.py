"""Durable storage for temporary developer API keys.

Only key digests enter this store. Plaintext keys exist only in the issuance response.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from google.cloud import firestore


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _active(data: dict[str, Any], product: str, now: datetime) -> bool:
    expires_at = data.get("expires_at")
    if isinstance(expires_at, datetime) and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return (
        data.get("product") == product
        and data.get("revoked_at") is None
        and isinstance(expires_at, datetime)
        and expires_at > now
    )


class FirestoreApiKeyStore:
    def __init__(self, client: firestore.Client, product: str) -> None:
        self._keys = client.collection("beta_developer_api_keys")
        self._product = product

    def get(self, digest: str) -> dict[str, Any] | None:
        snapshot = self._keys.document(digest).get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict() or {}
        if not _active(data, self._product, _utc_now()):
            return None
        return {
            "tenant_id": data["tenant_id"],
            "label": data["label"],
            "scopes": list(data["scopes"]),
        }

    def issue(
        self,
        digest: str,
        *,
        tenant_id: str,
        label: str,
        scopes: list[str],
        issued_at: datetime,
        expires_at: datetime,
        contact: dict[str, str] | None = None,
    ) -> None:
        # `contact` is what the developer told us about themselves. It is stored beside the
        # digest so the project can see who is using the beta, and it is never read back into
        # an authorisation decision.
        self._keys.document(digest).create({
            "product": self._product,
            "tenant_id": tenant_id,
            "label": label,
            "scopes": scopes,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "revoked_at": None,
            "contact": contact or {},
        })

    def revoke(self, digest: str, revoked_at: datetime) -> bool:
        ref = self._keys.document(digest)
        snapshot = ref.get()
        if not snapshot.exists or (snapshot.to_dict() or {}).get("product") != self._product:
            return False
        ref.update({"revoked_at": revoked_at})
        return True


class MemoryApiKeyStore:
    """Credential-free store with the same expiry and revocation behaviour as Firestore.

    `now` is a live reading unless a test pins one. Freezing it at construction would have made
    every key immortal on the local, no-Firestore path, which is the opposite of the guarantee
    this store exists to provide.
    """

    def __init__(self, product: str, now: datetime | None = None) -> None:
        self.product = product
        self._pinned_now = now
        self.records: dict[str, dict[str, Any]] = {}

    @property
    def now(self) -> datetime:
        return self._pinned_now if self._pinned_now is not None else _utc_now()

    def get(self, digest: str) -> dict[str, Any] | None:
        data = self.records.get(digest)
        if data is None or not _active(data, self.product, self.now):
            return None
        return {
            "tenant_id": data["tenant_id"],
            "label": data["label"],
            "scopes": list(data["scopes"]),
        }

    def issue(self, digest: str, **record: Any) -> None:
        if digest in self.records:
            raise ValueError("duplicate API key digest")
        self.records[digest] = {"product": self.product, "revoked_at": None, **record}

    def revoke(self, digest: str, revoked_at: datetime) -> bool:
        if digest not in self.records:
            return False
        self.records[digest]["revoked_at"] = revoked_at
        return True
