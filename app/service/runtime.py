"""Everything the process needs, assembled once.

This exists because the audit found the opposite: a wake scheduler, a tracer, an untrusted-input
gate and a redaction gate all present, all tested, and none of them reachable from a request. A
module that only tests import is not a capability, and the live-stack badge that named Cloud Trace
was making a claim the process could not support.

Assembling them here keeps `main.py` short and gives the routes one object to depend on, so what
is wired is visible in a single place and `/health` can report it truthfully rather than from a
hardcoded list.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from downstream.live_model import DrawingService
from downstream.store import (
    FirestoreLiveProofStore,
    FirestoreWorkspaceStore,
    MemoryLiveProofStore,
    MemoryWorkspaceStore,
    WorkspaceStore,
)
from spine import obs
from spine.api_key_store import FirestoreApiKeyStore, MemoryApiKeyStore
from spine.clock import ClockState, MemoryClockStateStore, RealClock, SimulatedClock
from spine.quota import (
    FirestoreQuotaStore,
    MemoryQuotaStore,
    NetworkFingerprint,
    QuotaGuard,
    QuotaPolicy,
)
from spine.wake import MemoryWakeStore, WakeScheduler, WakeStore

SERVICE_NAME = "downstream"


@dataclass
class Runtime:
    project: str
    persistence: str
    workspaces: WorkspaceStore
    live_proofs: Any
    api_keys: Any
    scheduler: WakeScheduler
    wake_store: WakeStore
    drawing: DrawingService
    policy: QuotaPolicy
    fingerprint: NetworkFingerprint
    public_workspace_quota: QuotaGuard
    api_call_quota: QuotaGuard
    key_issuance_quota: QuotaGuard
    invitation_attempt_quota: QuotaGuard
    tracing_active: bool
    wake_durability: str

    def scheduler_at_offset(self, seconds: float) -> WakeScheduler:
        """A scheduler over the same durable wake store, reading a clock moved forward.

        This is how the one-request demonstration fires a wake that is genuinely due in three
        days without waiting three days. Nothing is faked: the wake row, the compare-and-swap
        claim, the handler and the completion are the production ones. Only the reading of "now"
        changes, and the response says so.
        """
        store = MemoryClockStateStore(ClockState(offset_seconds=seconds))
        return WakeScheduler(self.wake_store, SimulatedClock(store))

    def stack(self) -> dict[str, Any]:
        """What this process is actually using, derived rather than declared.

        The live-stack badge on every page reads this. It used to be a literal list in the
        frontend that named Gemini and Cloud Trace as part of the live request path when neither
        was reachable from a request.
        """
        model_live = self.drawing.live_enabled
        return {
            "request_path": [
                {
                    "service": "Vertex AI Gemini 3.5 Flash",
                    "active": model_live,
                    "detail": (
                        "Live multimodal call on workspace open, with recorded replay as fallback."
                        if model_live
                        else "Recorded and graded call replayed; live inference is off on this deployment."
                    ),
                },
                {"service": "Cloud Run", "active": True, "detail": "Serves this request."},
                {
                    "service": "Firestore",
                    "active": self.persistence == "firestore",
                    "detail": (
                        "Durable workspaces, wakes, API keys, and quota counters."
                        if self.persistence == "firestore"
                        else "Credential-free memory stores on this deployment."
                    ),
                },
                {
                    "service": "Cloud Scheduler",
                    "active": bool(os.environ.get("INTERNAL_SCHEDULER_TOKEN", "").strip()),
                    "detail": (
                        "Wakes the service on a schedule; the scan-due route accepts only its token."
                        if os.environ.get("INTERNAL_SCHEDULER_TOKEN", "").strip()
                        else "No scheduler token configured; due wakes run only when someone visits."
                    ),
                },
                {
                    "service": "Cloud Trace",
                    "active": self.tracing_active,
                    "detail": (
                        "OpenTelemetry spans exported for every run."
                        if self.tracing_active
                        else "Exporter unavailable in this environment; spans are no-ops."
                    ),
                },
                {
                    "service": "Secret Manager",
                    "active": bool(os.environ.get("BETA_ENROLLMENT_CODE_HASH")),
                    "detail": "Supplies the invitation hash and API key digests.",
                },
            ],
            "additional_google_ai": [
                {
                    "service": "Gemma 4 MaaS",
                    "active": False,
                    "detail": "Recorded and graded name-span privacy review; replayed, not called live.",
                }
            ],
            "quotas": self.policy.as_public_dict(),
            "wake_durability": self.wake_durability,
        }


def build_runtime() -> Runtime:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "local")
    use_firestore = os.environ.get("USE_FIRESTORE", "").lower() in {"1", "true", "yes"}
    policy = QuotaPolicy.from_environment()
    fingerprint = NetworkFingerprint.from_environment()

    if use_firestore:
        from google.cloud import firestore

        from spine.firestore_stores import FirestoreWakeStore

        client = firestore.Client(project=project)
        workspaces: WorkspaceStore = FirestoreWorkspaceStore(client)
        live_proofs: Any = FirestoreLiveProofStore(client)
        api_keys: Any = FirestoreApiKeyStore(client, SERVICE_NAME)
        quota_store: Any = FirestoreQuotaStore(client)
        wake_store: Any = FirestoreWakeStore(client, "downstream_wakes")
        persistence = "firestore"
        wake_durability = "firestore_transactional"
    else:
        workspaces = MemoryWorkspaceStore()
        live_proofs: Any = MemoryLiveProofStore()
        api_keys = MemoryApiKeyStore(SERVICE_NAME)
        quota_store = MemoryQuotaStore()
        wake_store = MemoryWakeStore()
        persistence = "memory-local"
        wake_durability = "in_process"

    def guard(name: str, limit: int) -> QuotaGuard:
        return QuotaGuard(quota_store, fingerprint, name=name, limit=limit)

    live_model_quota = guard("live_model", policy.live_model_calls_per_day)

    return Runtime(
        project=project,
        persistence=persistence,
        workspaces=workspaces,
        live_proofs=live_proofs,
        api_keys=api_keys,
        scheduler=WakeScheduler(wake_store, RealClock()),
        wake_store=wake_store,
        drawing=DrawingService.from_environment(project, quota=live_model_quota),
        policy=policy,
        fingerprint=fingerprint,
        public_workspace_quota=guard("public_workspace", policy.public_workspaces_per_day),
        api_call_quota=guard("api_call", policy.api_calls_per_day),
        key_issuance_quota=guard("key_issuance", policy.key_issuances_per_day),
        invitation_attempt_quota=guard("invite_attempt", policy.invitation_attempts_per_day),
        tracing_active=obs.setup_tracing(project, SERVICE_NAME) if project != "local" else False,
        wake_durability=wake_durability,
    )


def local_runtime(
    workspaces: WorkspaceStore | None = None,
    policy: QuotaPolicy | None = None,
    **overrides: Any,
) -> Runtime:
    """A credential-free runtime for tests and local use.

    Quota limits are raised well above anything a test issues, so a suite cannot start failing
    because it happened to make one request too many; the ceilings themselves are exercised
    directly in `tests/test_quota.py` with limits chosen for that purpose.
    """
    policy = policy or QuotaPolicy(
        public_workspaces_per_day=10_000,
        api_calls_per_day=10_000,
        key_issuances_per_day=10_000,
        invitation_attempts_per_day=10_000,
        live_model_calls_per_day=0,
    )
    fingerprint = NetworkFingerprint("test-pepper")
    quota_store = MemoryQuotaStore()
    wake_store = MemoryWakeStore()

    def guard(name: str, limit: int) -> QuotaGuard:
        return QuotaGuard(quota_store, fingerprint, name=name, limit=limit)

    runtime = Runtime(
        project="local",
        persistence="memory-local",
        workspaces=workspaces if workspaces is not None else MemoryWorkspaceStore(),
        live_proofs=MemoryLiveProofStore(),
        api_keys=MemoryApiKeyStore(SERVICE_NAME),
        scheduler=WakeScheduler(wake_store, RealClock()),
        wake_store=wake_store,
        drawing=DrawingService(project="local", live_enabled=False),
        policy=policy,
        fingerprint=fingerprint,
        public_workspace_quota=guard("public_workspace", policy.public_workspaces_per_day),
        api_call_quota=guard("api_call", policy.api_calls_per_day),
        key_issuance_quota=guard("key_issuance", policy.key_issuances_per_day),
        invitation_attempt_quota=guard("invite_attempt", policy.invitation_attempts_per_day),
        tracing_active=False,
        wake_durability="in_process",
    )
    for name, value in overrides.items():
        setattr(runtime, name, value)
    return runtime
