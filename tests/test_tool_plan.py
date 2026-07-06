import json

import pytest

from agent_bridge.config import Config
from agent_bridge.errors import BridgeError, CursorNotImplementedError, UnregisteredRepoError
from agent_bridge.registry import SessionRegistry
from agent_bridge.tools import plan


async def test_plan_happy_path(fake_config, mock_claude_popen):
    mock_claude_popen["proc"].stdout_val = json.dumps(
        {"result": "# Plan\ndo it", "session_id": "sess-1", "usage": {"input_tokens": 5}, "cost_usd": 0.01}
    )
    registry = SessionRegistry()
    result = await plan.handle(
        {"task": "add a feature", "repo": "sample"}, config=fake_config, registry=registry
    )
    assert result["plan_markdown"] == "# Plan\ndo it"
    assert result["next_step_hint"]
    session = registry.require(result["bridge_session_id"])
    assert session.phase == "planned"
    assert session.has_plan is True


async def test_plan_unregistered_repo_rejects_before_spawning(fake_config, mock_claude_popen):
    registry = SessionRegistry()
    with pytest.raises(UnregisteredRepoError):
        await plan.handle(
            {"task": "x", "repo": "does-not-exist"}, config=fake_config, registry=registry
        )
    assert mock_claude_popen["last_argv"] is None


async def test_plan_nonzero_exit_raises_with_stderr(fake_config, mock_claude_popen):
    mock_claude_popen["proc"].returncode = 1
    mock_claude_popen["proc"].stderr_val = "boom: something failed"
    registry = SessionRegistry()
    with pytest.raises(BridgeError) as exc_info:
        await plan.handle({"task": "x", "repo": "sample"}, config=fake_config, registry=registry)
    assert "boom" in str(exc_info.value)


async def test_plan_json_parse_failure_does_not_crash(fake_config, mock_claude_popen):
    mock_claude_popen["proc"].stdout_val = "not valid json"
    mock_claude_popen["proc"].returncode = 0
    registry = SessionRegistry()
    result = await plan.handle({"task": "x", "repo": "sample"}, config=fake_config, registry=registry)
    assert result["plan_markdown"] is None
    assert any("parse" in w for w in result["warnings"])


async def test_plan_rejects_silent_fable_default(fake_config, mock_claude_popen):
    fable_config = Config(
        repos=fake_config.repos,
        default_backend="claude",
        default_models={"claude": "claude-fable-5", "cursor": "auto"},
        concurrency_limit=2,
        default_timeout_min=30,
        claude_binary="claude",
        cursor_binary="agent",
    )
    registry = SessionRegistry()
    with pytest.raises(BridgeError):
        await plan.handle({"task": "x", "repo": "sample"}, config=fable_config, registry=registry)
    assert mock_claude_popen["last_argv"] is None


async def test_plan_rejects_cursor_backend(fake_config, mock_claude_popen):
    registry = SessionRegistry()
    with pytest.raises(CursorNotImplementedError):
        await plan.handle(
            {"task": "x", "repo": "sample", "backend": "cursor"},
            config=fake_config,
            registry=registry,
        )
    assert mock_claude_popen["last_argv"] is None
