import json
import subprocess

import pytest

from agent_bridge import paths
from agent_bridge.config import Config, load_config


@pytest.fixture
def tmp_bridge_home(tmp_path, monkeypatch):
    home = tmp_path / "bridge_home"
    monkeypatch.setattr(paths, "BRIDGE_HOME", home)
    monkeypatch.setattr(paths, "CONFIG_PATH", home / "config.json")
    monkeypatch.setattr(paths, "SESSIONS_PATH", home / "sessions.json")
    monkeypatch.setattr(paths, "LOG_DIR", home / "log")
    monkeypatch.setattr(paths, "WORKTREES_DIR", home / "worktrees")
    paths.ensure_bridge_home()
    return home


def _init_git_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


@pytest.fixture
def sample_repo(tmp_path):
    repo = tmp_path / "sample_repo"
    _init_git_repo(repo)
    return repo


@pytest.fixture
def sensitive_repo(tmp_path):
    repo = tmp_path / "sensitive_repo"
    _init_git_repo(repo)
    return repo


@pytest.fixture
def fake_config(tmp_bridge_home, sample_repo, sensitive_repo) -> Config:
    config_data = {
        "repos": {
            "sample": {"path": str(sample_repo)},
            "sensitive-repo": {"path": str(sensitive_repo), "sensitive": True},
        },
        "defaults": {"backend": "claude", "model": {"claude": "claude-sonnet-5", "cursor": "auto"}},
        "limits": {"concurrency": 2, "timeout_min": 30},
        "binaries": {"claude": "claude", "cursor": "agent"},
    }
    paths.CONFIG_PATH.write_text(json.dumps(config_data))
    return load_config()


class FakeProc:
    """Stand-in for subprocess.Popen's return value."""

    def __init__(self, stdout="", stderr="", returncode=0, communicate_effect=None):
        self.stdout_val = stdout
        self.stderr_val = stderr
        self.returncode = returncode
        self.pid = 999999
        self._effect = communicate_effect
        self.communicate_calls = 0

    def communicate(self, timeout=None):
        self.communicate_calls += 1
        if self._effect is not None:
            outcome = self._effect(self.communicate_calls)
            if isinstance(outcome, BaseException):
                raise outcome
            if outcome is not None:
                return outcome
        return self.stdout_val, self.stderr_val


@pytest.fixture
def mock_claude_popen(monkeypatch):
    """Patches subprocess.Popen as used by agent_bridge.runner. Tests set
    `state["proc"]` to a FakeProc before calling code that invokes run_claude,
    and can inspect `state["last_argv"]` / `state["last_kwargs"]` afterward.
    """
    state = {"proc": FakeProc(stdout='{"result": "ok"}'), "last_argv": None, "last_kwargs": None}

    def fake_popen(argv, **kwargs):
        state["last_argv"] = argv
        state["last_kwargs"] = kwargs
        proc = state["proc"]
        if isinstance(proc, BaseException):
            raise proc
        return proc

    monkeypatch.setattr("agent_bridge.runner.Popen", fake_popen)
    monkeypatch.setattr("agent_bridge.runner.os.killpg", lambda pid, sig: None)
    return state
