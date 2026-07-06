import pytest

from agent_bridge.config import resolve_repo
from agent_bridge.errors import SensitiveRepoGuardError
from agent_bridge.guardrails import check_sensitive_repo


def test_sensitive_repo_rejects_cursor_backend(fake_config):
    repo = resolve_repo(fake_config, "sensitive-repo")
    with pytest.raises(SensitiveRepoGuardError):
        check_sensitive_repo(repo, backend="cursor", model="claude-sonnet-5")


def test_sensitive_repo_rejects_fable_without_confirm(fake_config):
    repo = resolve_repo(fake_config, "sensitive-repo")
    with pytest.raises(SensitiveRepoGuardError):
        check_sensitive_repo(repo, backend="claude", model="claude-fable-5")


def test_sensitive_repo_allows_fable_with_confirm(fake_config):
    repo = resolve_repo(fake_config, "sensitive-repo")
    check_sensitive_repo(
        repo, backend="claude", model="claude-fable-5", confirm_sensitive_model=True
    )  # must not raise


def test_non_sensitive_repo_allows_fable(fake_config):
    repo = resolve_repo(fake_config, "sample")
    check_sensitive_repo(repo, backend="claude", model="claude-fable-5")  # must not raise


def test_non_sensitive_repo_allows_cursor(fake_config):
    repo = resolve_repo(fake_config, "sample")
    check_sensitive_repo(repo, backend="cursor", model="claude-sonnet-5")  # must not raise
