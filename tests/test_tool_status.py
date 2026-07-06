import pytest

from agent_bridge.errors import UnknownSessionError
from agent_bridge.registry import SessionRegistry
from agent_bridge.tools import status


async def test_status_lists_all_sessions(fake_config):
    registry = SessionRegistry()
    registry.create(backend="claude", repo="sample", model="claude-sonnet-5")
    registry.create(backend="claude", repo="sample", model="claude-sonnet-5")

    result = await status.handle({}, config=fake_config, registry=registry)
    assert len(result["sessions"]) == 2
    assert "bridge_build" in result
    assert "started_at" in result


async def test_status_single_session_detail(fake_config):
    registry = SessionRegistry()
    record = registry.create(backend="claude", repo="sample", model="claude-sonnet-5")

    result = await status.handle(
        {"session_id": record.bridge_session_id}, config=fake_config, registry=registry
    )
    assert result["session"]["bridge_session_id"] == record.bridge_session_id
    assert result["elapsed_s"] >= 0
    assert "bridge_build" in result
    assert "started_at" in result


async def test_status_unknown_session(fake_config):
    registry = SessionRegistry()
    with pytest.raises(UnknownSessionError):
        await status.handle({"session_id": "b-nope"}, config=fake_config, registry=registry)
