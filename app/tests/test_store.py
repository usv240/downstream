from downstream.partner import create_workspace
from downstream.store import MemoryWorkspaceStore


def test_memory_store_round_trip_is_copy_isolated():
    store = MemoryWorkspaceStore()
    workspace = create_workspace()
    store.put(workspace)
    first = store.get(workspace["workspace_id"])
    first["dam"]["name"] = "mutated"
    assert store.get(workspace["workspace_id"])["dam"]["name"] != "mutated"


def test_missing_workspace_returns_none():
    assert MemoryWorkspaceStore().get("none") is None


def test_put_replaces_same_workspace_atomically():
    store = MemoryWorkspaceStore()
    workspace = create_workspace()
    store.put(workspace)
    workspace["status"] = "changed"
    store.put(workspace)
    assert store.get(workspace["workspace_id"])["status"] == "changed"
