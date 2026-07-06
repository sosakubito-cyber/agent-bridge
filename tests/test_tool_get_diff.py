import pytest

from agent_bridge.errors import UnknownSessionError
from agent_bridge.registry import SessionRegistry
from agent_bridge.tools import get_diff


async def test_get_diff_falls_back_to_repo_path_without_worktree(fake_config, sample_repo):
    registry = SessionRegistry()
    record = registry.create(backend="claude", repo="sample", model="claude-sonnet-5")
    (sample_repo / "README.md").write_text("hello\nchanged!\n")

    result = await get_diff.handle(
        {"session_id": record.bridge_session_id}, config=fake_config, registry=registry
    )
    assert "changed!" in result["diff"]
    assert "README.md" in result["changed_files"]


async def test_get_diff_uses_session_worktree_when_set(fake_config, sample_repo):
    registry = SessionRegistry()
    record = registry.create(backend="claude", repo="sample", model="claude-sonnet-5")
    registry.update(record.bridge_session_id, worktree=str(sample_repo))
    (sample_repo / "README.md").write_text("hello\nfrom worktree\n")

    result = await get_diff.handle(
        {"session_id": record.bridge_session_id}, config=fake_config, registry=registry
    )
    assert "from worktree" in result["diff"]


async def test_get_diff_stat_only_differs_from_full_diff(fake_config, sample_repo):
    registry = SessionRegistry()
    record = registry.create(backend="claude", repo="sample", model="claude-sonnet-5")
    (sample_repo / "README.md").write_text("hello\nstat test\n")

    full = await get_diff.handle(
        {"session_id": record.bridge_session_id, "stat_only": False},
        config=fake_config,
        registry=registry,
    )
    stat = await get_diff.handle(
        {"session_id": record.bridge_session_id, "stat_only": True},
        config=fake_config,
        registry=registry,
    )
    assert "stat test" in full["diff"]
    assert "stat test" not in stat["diff"]
    assert "1 file changed" in stat["diff"] or "1 +" in stat["diff"]


async def test_get_diff_unknown_session(fake_config):
    registry = SessionRegistry()
    with pytest.raises(UnknownSessionError):
        await get_diff.handle({"session_id": "b-nope"}, config=fake_config, registry=registry)
