from agent_bridge.errors import UnknownSessionError
from agent_bridge.registry import SessionRegistry
import pytest


def test_create_and_get(tmp_bridge_home):
    registry = SessionRegistry()
    record = registry.create(backend="claude", repo="sample", model="claude-sonnet-5")
    assert record.phase == "planned"
    assert record.has_plan is False

    fetched = registry.get(record.bridge_session_id)
    assert fetched is not None
    assert fetched.bridge_session_id == record.bridge_session_id


def test_get_unknown_returns_none(tmp_bridge_home):
    registry = SessionRegistry()
    assert registry.get("b-nonexistent") is None


def test_require_unknown_raises(tmp_bridge_home):
    registry = SessionRegistry()
    with pytest.raises(UnknownSessionError):
        registry.require("b-nonexistent")


def test_update_sets_has_plan(tmp_bridge_home):
    registry = SessionRegistry()
    record = registry.create(backend="claude", repo="sample", model="claude-sonnet-5")
    updated = registry.update(record.bridge_session_id, has_plan=True, phase="planned")
    assert updated.has_plan is True


def test_two_registry_instances_do_not_clobber_each_other(tmp_bridge_home):
    """Two separate SessionRegistry objects pointed at the same file, writing
    sequentially, must both end up persisted (exercises the locked read-modify-write)."""
    registry_a = SessionRegistry()
    registry_b = SessionRegistry()

    record_a = registry_a.create(backend="claude", repo="sample", model="claude-sonnet-5")
    record_b = registry_b.create(backend="claude", repo="sample", model="claude-sonnet-5")

    registry_c = SessionRegistry()
    all_sessions = {s.bridge_session_id for s in registry_c.list_all()}
    assert record_a.bridge_session_id in all_sessions
    assert record_b.bridge_session_id in all_sessions
