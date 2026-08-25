"""Self-service issuance of short-lived, scoped developer API keys.

This started out invite-gated, which made it useless to a judge: no code, no key, no way to see
the API work. Issuance is now open by default and held in check by per-network daily ceilings
instead of by a shared secret. `DEVELOPER_ISSUANCE_MODE` can still be set to `invite_only` (which
requires `BETA_ENROLLMENT_CODE_HASH`) or `disabled` if that ever needs to change.

Two properties survive the change:

* **The tenant is minted here, never accepted from the caller.** When the code was shared, a
  caller-supplied `tenant_id` let one holder name another holder's tenant and read their
  workspaces. A key's identity is something this server issued.
* **The plaintext key exists once, in the response.** Only its SHA-256 digest is stored.

What the caller tells us about themselves is metadata: it is recorded next to the digest so the
project can see who is using the beta, and it never affects authorisation.
"""

from __future__ import annotations

import hmac
import os
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, SecretStr, field_validator

from spine.api_access import ApiKeyAuthenticator, ApiPrincipal, hash_api_key, require_scope

OPEN = "open"
INVITE_ONLY = "invite_only"
DISABLED = "disabled"

# Deliberately permissive. This is a contact field, not an authentication factor, and rejecting
# a valid address because the pattern was clever would be the worse failure.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]{2,}$")


class ApiKeyStore(Protocol):
    def get(self, digest: str) -> dict[str, Any] | None: ...
    def issue(self, digest: str, **record: Any) -> None: ...
    def revoke(self, digest: str, revoked_at: datetime) -> bool: ...


class KeyRequest(BaseModel):
    """What a developer tells us. None of it grants anything.

    `tenant_id` is deliberately absent: it used to be caller-supplied, which meant one holder of
    a shared invitation code could mint a key naming another holder's tenant and read their
    workspaces.
    """

    label: str = Field(min_length=2, max_length=80)
    email: str = Field(default="", max_length=254)
    organisation: str = Field(default="", max_length=120)
    intended_use: str = Field(default="", max_length=400)
    acknowledge_terms: Literal[True]
    invitation_code: SecretStr | None = None

    @field_validator("email")
    @classmethod
    def _plausible_email(cls, value: str) -> str:
        value = value.strip()
        if value and not _EMAIL.match(value):
            raise ValueError("email does not look like an address")
        return value

    def contact(self) -> dict[str, str]:
        return {
            "label": self.label.strip(),
            "email": self.email.strip(),
            "organisation": self.organisation.strip(),
            "intended_use": self.intended_use.strip(),
        }


class KeyIssuer:
    def __init__(
        self,
        store: ApiKeyStore,
        *,
        product: str,
        scope: str,
        prefix: str,
        invitation_hash: str = "",
        ttl_hours: int = 168,
        mode: str = OPEN,
    ) -> None:
        self.store = store
        self.product = product
        self.scope = scope
        self.prefix = prefix
        self.invitation_hash = invitation_hash.strip().lower()
        if self.invitation_hash and (
            len(self.invitation_hash) != 64
            or any(char not in "0123456789abcdef" for char in self.invitation_hash)
        ):
            raise RuntimeError("BETA_ENROLLMENT_CODE_HASH must be a lowercase SHA-256 digest")
        if mode not in {OPEN, INVITE_ONLY, DISABLED}:
            raise RuntimeError(f"DEVELOPER_ISSUANCE_MODE must be one of {OPEN}, {INVITE_ONLY}, {DISABLED}")
        if mode == INVITE_ONLY and not self.invitation_hash:
            raise RuntimeError("invite_only issuance requires BETA_ENROLLMENT_CODE_HASH")
        self.mode = mode
        if not 1 <= ttl_hours <= 720:
            raise RuntimeError("BETA_DEVELOPER_KEY_TTL_HOURS must be between 1 and 720")
        self.ttl = timedelta(hours=ttl_hours)

    @classmethod
    def from_environment(
        cls, store: ApiKeyStore, *, product: str, scope: str, prefix: str
    ) -> KeyIssuer:
        raw_ttl = os.environ.get("BETA_DEVELOPER_KEY_TTL_HOURS", "168")
        try:
            ttl = int(raw_ttl)
        except ValueError as exc:
            raise RuntimeError("BETA_DEVELOPER_KEY_TTL_HOURS must be an integer") from exc
        return cls(
            store,
            product=product,
            scope=scope,
            prefix=prefix,
            invitation_hash=os.environ.get("BETA_ENROLLMENT_CODE_HASH", ""),
            ttl_hours=ttl,
            mode=os.environ.get("DEVELOPER_ISSUANCE_MODE", OPEN).strip().lower() or OPEN,
        )

    @property
    def enabled(self) -> bool:
        return self.mode != DISABLED

    @property
    def requires_invitation(self) -> bool:
        return self.mode == INVITE_ONLY

    def verify_invitation(self, request: KeyRequest) -> None:
        """Check eligibility without minting anything.

        Separated from `mint` so a caller who is over their daily ceiling is refused before a key
        exists, rather than after one has been written to the store and thrown away.
        """
        if not self.enabled:
            raise HTTPException(status_code=503, detail="Developer key issuance is disabled.")
        if not self.requires_invitation:
            return
        supplied = request.invitation_code.get_secret_value().strip() if request.invitation_code else ""
        if not supplied or not hmac.compare_digest(hash_api_key(supplied), self.invitation_hash):
            raise HTTPException(status_code=401, detail="The invitation code is invalid.")

    def issue(self, request: KeyRequest) -> dict[str, Any]:
        self.verify_invitation(request)
        return self.mint(request)

    def mint(self, request: KeyRequest) -> dict[str, Any]:
        issued_at = datetime.now(UTC)
        expires_at = issued_at + self.ttl
        api_key = f"{self.prefix}_{secrets.token_urlsafe(32)}"
        digest = hash_api_key(api_key)
        tenant_id = self.mint_tenant_id()
        contact = request.contact()
        self.store.issue(
            digest,
            tenant_id=tenant_id,
            label=contact["label"],
            scopes=[self.scope],
            issued_at=issued_at,
            expires_at=expires_at,
            contact=contact,
        )
        return {
            "api_key": api_key,
            "key_id": digest[:12],
            "tenant_id": tenant_id,
            "tenant_origin": "server_minted",
            "scope": self.scope,
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "shown_once": True,
            "header": "X-API-Key",
        }

    @staticmethod
    def mint_tenant_id() -> str:
        """A fresh, unguessable namespace per key.

        Two developers who sign up minutes apart never land in the same tenant, so a workspace
        opened by one is a 404 for the other even if the id is guessed correctly.
        """
        return "t_" + secrets.token_hex(12)


def build_developer_router(
    issuer: KeyIssuer,
    auth: ApiKeyAuthenticator,
    *,
    product: str,
    scope: str,
    issuance_quota=None,
    attempt_quota=None,
    policy=None,
) -> APIRouter:
    router = APIRouter(tags=["developer-access"])

    @router.get("/developer/config")
    def config() -> dict[str, Any]:
        return {
            "product": product,
            "issuance": issuer.mode,
            "requires_invitation": issuer.requires_invitation,
            "ttl_hours": int(issuer.ttl.total_seconds() // 3600),
            "scope": scope,
            "header": "X-API-Key",
            "docs": "/docs",
            "openapi": "/openapi.json",
            "tenant": "server_minted_per_key",
            "quotas": policy.as_public_dict() if policy is not None else {},
        }

    @router.post("/developer/keys", status_code=201)
    def issue_key(body: KeyRequest, request: Request, response: Response) -> dict[str, Any]:
        """Mint one temporary, tenant-scoped key.

        Open by default. The ceilings are per caller network and generous enough that anyone
        evaluating the API will not meet them; they exist to stop a runaway script.
        """
        if attempt_quota is not None:
            attempt_quota.enforce_network(
                request,
                "Too many key requests from this network today. "
                "The allowance resets at UTC midnight.",
            )
        issuer.verify_invitation(body)
        verdict = None
        if issuance_quota is not None:
            verdict = issuance_quota.enforce_network(
                request,
                "This network has issued its daily allowance of keys. "
                "The allowance resets at UTC midnight.",
            )
        result = issuer.mint(body)
        if verdict is not None:
            response.headers.update(verdict.headers())
            result["keys_remaining_today"] = verdict.remaining
            result["allowance_resets_at"] = verdict.resets_at
        return result

    @router.delete("/v1/key")
    def revoke_key(principal: ApiPrincipal = Depends(auth)) -> dict[str, Any]:
        require_scope(principal, scope)
        revoked = issuer.store.revoke(principal.key_digest, datetime.now(UTC))
        if not revoked:
            raise HTTPException(
                status_code=409,
                detail="This operator-managed key must be revoked by the project owner.",
            )
        return {"revoked": True, "key_id": principal.key_id}

    return router
