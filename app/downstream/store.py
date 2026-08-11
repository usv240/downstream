"""Workspace stores. Firestore is used in Cloud Run; memory keeps local tests credential-free."""

from __future__ import annotations

import copy
import threading
from typing import Any, Protocol


class WorkspaceStore(Protocol):
    def put(self, workspace: dict[str, Any]) -> None: ...
    def get(self, workspace_id: str) -> dict[str, Any] | None: ...


class MemoryWorkspaceStore:
    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def put(self, workspace: dict[str, Any]) -> None:
        with self._lock:
            self._items[workspace["workspace_id"]] = copy.deepcopy(workspace)

    def get(self, workspace_id: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._items.get(workspace_id)
            return copy.deepcopy(item) if item is not None else None


class FirestoreWorkspaceStore:
    def __init__(self, client, collection: str = "downstream_workspaces") -> None:
        self._collection = client.collection(collection)

    def put(self, workspace: dict[str, Any]) -> None:
        self._collection.document(workspace["workspace_id"]).set(copy.deepcopy(workspace))

    def get(self, workspace_id: str) -> dict[str, Any] | None:
        snapshot = self._collection.document(workspace_id).get()
        return snapshot.to_dict() if snapshot.exists else None
