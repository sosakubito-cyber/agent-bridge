import json
import subprocess

import pytest

from agent_bridge.errors import ApprovalNotGrantedError, NoPlanArtifactError, BridgeError
from agent_bridge.registry import SessionRegistry
from agent_bridge.tools import execute
from agent_bridge.worktree import create_worktree


def _planned_session(registry, repo="sample", backend_session_id="sess-1"):
    record = registry.create(backend="claude", repo=repo, model="claude-sonnet-5")
    return registry.update(
        record.bridge_session_id,
        has_plan=True,
        backend_session_id=backend_session_id,
    )


async def test_execute_happy_path_uses_worktree_and_resume(fake_config, mock_claude_popen):
    registry = SessionRegistry()
    session = _planned_session(registry)
    mock_claude_popen["proc"].stdout_val = json.dumps({"result": "done", "cost_usd": 0.02})
    mock_claude_popen["proc"].returncode = 0

    result = await execute.handle(
        {"session_id": session.bridge_session_id, "approved": True},
        config=fake_config,
        registry=registry,
    )

    assert result["result_markdown"] == "done"
    assert "--resume" in mock_claude_popen["last_argv"]
    assert "sess-1" in mock_claude_popen["last_argv"]
    prompt = mock_claude_popen["last_argv"][mock_claude_popen["last_argv"].index("-p") + 1]
    assert "push は行わない" in prompt

    updated = registry.require(session.bridge_session_id)
    assert updated.phase == "done"
    assert updated.worktree is not None


async def test_execute_without_plan_rejects(fake_config, mock_claude_popen):
    registry = SessionRegistry()
    record = registry.create(backend="claude", repo="sample", model="claude-sonnet-5")
    with pytest.raises(NoPlanArtifactError):
        await execute.handle(
            {"session_id": record.bridge_session_id, "approved": True},
            config=fake_config,
            registry=registry,
        )
    assert mock_claude_popen["last_argv"] is None


async def test_execute_without_approved_rejects(fake_config, mock_claude_popen):
    registry = SessionRegistry()
    session = _planned_session(registry)
    with pytest.raises(ApprovalNotGrantedError):
        await execute.handle(
            {"session_id": session.bridge_session_id, "approved": False},
            config=fake_config,
            registry=registry,
        )
    assert mock_claude_popen["last_argv"] is None
    unchanged = registry.require(session.bridge_session_id)
    assert unchanged.worktree is None


async def test_execute_timeout_sigterm_then_sigkill(fake_config, mock_claude_popen):
    registry = SessionRegistry()
    session = _planned_session(registry)

    def effect(call_number):
        if call_number in (1, 2):
            return subprocess.TimeoutExpired(cmd="claude", timeout=1)
        return ("", "")

    mock_claude_popen["proc"]._effect = effect

    result = await execute.handle(
        {"session_id": session.bridge_session_id, "approved": True, "timeout_min": 1},
        config=fake_config,
        registry=registry,
    )
    assert result is not None
    updated = registry.require(session.bridge_session_id)
    assert updated.phase == "failed"


async def test_execute_nonzero_exit_marks_failed(fake_config, mock_claude_popen):
    registry = SessionRegistry()
    session = _planned_session(registry)
    mock_claude_popen["proc"].returncode = 1
    mock_claude_popen["proc"].stderr_val = "execute blew up"

    with pytest.raises(BridgeError) as exc_info:
        await execute.handle(
            {"session_id": session.bridge_session_id, "approved": True},
            config=fake_config,
            registry=registry,
        )
    assert "execute blew up" in str(exc_info.value)
    updated = registry.require(session.bridge_session_id)
    assert updated.phase == "failed"


async def test_execute_without_worktree_uses_repo_path_directly(fake_config, mock_claude_popen, sample_repo):
    registry = SessionRegistry()
    session = _planned_session(registry)
    mock_claude_popen["proc"].stdout_val = json.dumps({"result": "done"})

    await execute.handle(
        {"session_id": session.bridge_session_id, "approved": True, "use_worktree": False},
        config=fake_config,
        registry=registry,
    )
    assert mock_claude_popen["last_kwargs"]["cwd"] == sample_repo
    updated = registry.require(session.bridge_session_id)
    assert updated.worktree is None


async def test_execute_reuses_plan_created_worktree(fake_config, mock_claude_popen, sample_repo):
    """Regression: if plan() already created a worktree, execute() must resume
    the backend session from that same cwd — not create a second worktree
    (which would also crash: same branch name would already exist) and not
    fall back to repo.path (which reintroduces the stale-permission-scope bug
    this was built to fix)."""
    registry = SessionRegistry()
    session = _planned_session(registry)
    pre_existing = create_worktree(sample_repo, session.bridge_session_id)
    session = registry.update(session.bridge_session_id, worktree=str(pre_existing))

    mock_claude_popen["proc"].stdout_val = json.dumps({"result": "done"})
    await execute.handle(
        {"session_id": session.bridge_session_id, "approved": True},
        config=fake_config,
        registry=registry,
    )
    assert mock_claude_popen["last_kwargs"]["cwd"] == pre_existing
