"""Proof that the agent runs when nobody is watching.

Everything else on the public page runs on a clock the visitor controls. That is honest, and the
interface says so, but it leaves one fair objection unanswered: *you pressed a button, so how is
that autonomous?* The button moves time, not the plan -- which is easier to assert than to watch.

This closes it. A wake is registered against the **wall clock** and nothing on the page executes
it. Cloud Scheduler calls `/internal/scan-due`, that request claims the wake and runs it, and the
handler writes a step into the workspace timeline stamped with the Cloud Run revision that did the
work. The page only polls to find out whether that has happened yet. Close the tab and it still
fires.

The lead is deliberately short. The wait is the lead plus however long until the next sweep, and
that second term is not the cron interval: measured against a deployed job, real gaps ran from 51
to 84 seconds. A long lead buys nothing an observer can see, because the reveal happens later
either way, and it costs the entire margin.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

LEAD_SECONDS = 20
WAKE_KIND = "unattended_draft_review"
COLLECTION = "downstream_live_proof"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def revision() -> str:
    """Which Cloud Run revision executed this. Set by the platform, absent locally."""
    return os.environ.get("K_REVISION", "local")


@dataclass(frozen=True)
class ArmedProof:
    wake_id: str
    workspace_id: str
    armed_at: str
    due_at: str
    lead_seconds: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "wake_id": self.wake_id,
            "workspace_id": self.workspace_id,
            "armed_at": self.armed_at,
            "due_at": self.due_at,
            "seconds_until_due": self.lead_seconds,
            "note": (
                "Registered on the real clock. Nothing on this page will run it. Cloud Scheduler "
                "claims due work and executes it; you can close this tab and it will still fire."
            ),
        }


def arm(scheduler, workspace_id: str, store) -> ArmedProof:
    """Register the wake and record that it was armed, so the poll can tell 'not yet' from 'never'."""
    now = utc_now()
    due_at = now + timedelta(seconds=LEAD_SECONDS)
    wake = scheduler.sleep_until(
        run_id=workspace_id,
        kind=WAKE_KIND,
        due_at=due_at,
        payload={"workspace_id": workspace_id, "armed_at": now.isoformat()},
        # A fresh discriminator each time: arming twice is two separate proofs, not one wake
        # returned twice by the idempotent registration path.
        discriminator=f"{WAKE_KIND}:{now.timestamp()}",
    )
    armed = ArmedProof(
        wake_id=wake.wake_id,
        workspace_id=workspace_id,
        armed_at=now.isoformat(),
        due_at=due_at.isoformat(),
        lead_seconds=LEAD_SECONDS,
    )
    store.record_armed(armed)
    return armed


def status(armed: dict[str, Any] | None, workspace: dict[str, Any] | None) -> dict[str, Any]:
    """Has the scheduler picked it up yet? Read-only: polling never causes the work."""
    if armed is None:
        return {"found": False}

    now = utc_now()
    due_at = armed.get("due_at")
    seconds_left = None
    if isinstance(due_at, str):
        try:
            seconds_left = max(0, int(datetime.fromisoformat(due_at).timestamp() - now.timestamp()))
        except ValueError:
            seconds_left = None

    step = None
    if workspace:
        step = next(
            (
                entry
                for entry in reversed(workspace.get("timeline", []))
                if entry.get("step") == "unattended_review_ran"
                and entry.get("evidence", {}).get("wake_id") == armed.get("wake_id")
            ),
            None,
        )

    if step is None:
        return {
            "found": True,
            "fired": False,
            "seconds_until_due": seconds_left,
            "status": "waiting" if seconds_left else "due, waiting for the next scan",
        }

    evidence = step.get("evidence", {})
    return {
        "found": True,
        "fired": True,
        "fired_at": step.get("at"),
        "revision": evidence.get("revision"),
        "waited_seconds": evidence.get("waited_seconds"),
        "detail": step.get("detail"),
        "note": (
            "Executed by the scheduled worker on the revision named above, not by this page. "
            "The timestamp is wall-clock time."
        ),
    }
