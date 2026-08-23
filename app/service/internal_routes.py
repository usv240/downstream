"""The scheduler-facing surface.

`spine/wake.py` opens by saying that in production a Cloud Scheduler cron calls
`/internal/scan-due`. Until now that route did not exist, so the durable wake ladder was a tested
library with no way to fire. This is the missing half.

The route is deliberately not part of the public API surface. The service is deployed
`--allow-unauthenticated` so judges can use it without credentials, which means an internal
trigger needs its own shared secret: without `INTERNAL_SCHEDULER_TOKEN` configured the route
refuses to run at all rather than defaulting to open.
"""

from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from downstream import autonomy
from downstream.partner import outstanding_ids, public_view
from spine.wake import Wake


def build_internal_router(runtime) -> APIRouter:
    router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)

    def authorise(token: str | None) -> None:
        expected = os.environ.get("INTERNAL_SCHEDULER_TOKEN", "").strip()
        if not expected:
            raise HTTPException(
                status_code=503,
                detail="Scheduled execution is not provisioned on this deployment.",
            )
        if not token or not hmac.compare_digest(token.strip(), expected):
            raise HTTPException(status_code=401, detail="Invalid scheduler token.")

    def handle(wake: Wake) -> None:
        """Advance one workspace. Must be idempotent by wake id.

        The scheduler may retry after a lease expires, so every action here is an overwrite of a
        derived field rather than an append of a new side effect.
        """
        workspace_id = wake.payload.get("workspace_id")
        if not workspace_id:
            raise ValueError("wake carries no workspace_id")
        workspace = runtime.workspaces.get(workspace_id)
        if workspace is None:
            # The workspace is gone. Completing the wake is correct: retrying cannot succeed.
            return
        autonomy.advance_on_wake(workspace, wake.kind, outstanding=outstanding_ids(workspace))
        runtime.workspaces.put(workspace)

    @router.post("/scan-due")
    def scan_due(
        limit: int = 50,
        x_scheduler_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """What Cloud Scheduler calls. Claims due wakes, runs them, reports what moved."""
        authorise(x_scheduler_token)
        dispatched = runtime.scheduler.dispatch_due(handle, limit=limit)
        return {
            "dispatched": len(dispatched),
            "wakes": [
                {"wake_id": wake.wake_id, "kind": wake.kind, "run_id": wake.run_id}
                for wake in dispatched
            ],
            "dead_lettered": len(runtime.scheduler.dead_letters),
        }

    @router.post("/wakes/{wake_id}/dispatch")
    def dispatch_one(
        wake_id: str,
        x_scheduler_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Fire one known wake now.

        This is how the acceptance flow proves a scheduled action really runs without waiting
        three days for it to come due. It uses the same claim, retry and dead-letter path as the
        batch scan, so what the check exercises is what ships.
        """
        authorise(x_scheduler_token)
        wake = runtime.scheduler.dispatch_wake(wake_id, handle)
        if wake is None:
            raise HTTPException(status_code=409, detail="The wake was not claimable.")
        workspace = runtime.workspaces.get(wake.payload.get("workspace_id", ""))
        return {
            "dispatched": wake.wake_id,
            "kind": wake.kind,
            "workspace": public_view(workspace) if workspace else None,
        }

    return router
