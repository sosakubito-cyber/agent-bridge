import subprocess
from pathlib import Path

import pytest

from agent_bridge.errors import ClaudeBinaryNotFoundError
from agent_bridge.runner import ClaudeInvocation, build_argv, build_env, run_claude


def _inv(**overrides):
    defaults = dict(
        prompt="do the thing",
        cwd=Path("/tmp"),
        permission_mode="plan",
        model="claude-sonnet-5",
        timeout_s=30,
    )
    defaults.update(overrides)
    return ClaudeInvocation(**defaults)


def test_build_argv_basic():
    argv = build_argv("claude", _inv())
    assert argv[0] == "claude"
    assert "-p" in argv and "do the thing" in argv
    assert "--permission-mode" in argv and "plan" in argv
    assert "--model" in argv and "claude-sonnet-5" in argv
    assert "--output-format" in argv and "json" in argv
    assert "--resume" not in argv


def test_build_argv_includes_resume_when_present():
    argv = build_argv("claude", _inv(resume_backend_session_id="sess-123"))
    assert "--resume" in argv
    assert "sess-123" in argv


def test_run_claude_happy_path(mock_claude_popen):
    mock_claude_popen["proc"].stdout_val = '{"result": "ok", "usage": {"input_tokens": 1}}'
    mock_claude_popen["proc"].returncode = 0
    result = run_claude("claude", _inv())
    assert result.exit_code == 0
    assert result.parsed.result_text == "ok"
    assert mock_claude_popen["last_kwargs"]["cwd"] == Path("/tmp")


def test_build_env_passes_through_user_for_keychain_auth(monkeypatch):
    """USER must reach claude for OAuth/keychain-based auth to resolve
    (empirically confirmed 2026-07-07: `claude auth status` reports
    loggedIn:false without it, even with HOME set)."""
    monkeypatch.setenv("USER", "alice")
    env = build_env()
    assert env.get("USER") == "alice"


def test_build_env_passes_through_arbitrary_non_secret_vars(monkeypatch):
    """Blocklist approach (SPEC §5-6, revised 2026-07-07): inherit the full
    parent environment except secret-shaped names — not just a fixed
    allowlist — since Keychain-based auth's real requirements aren't fully
    enumerable without inspecting credential internals."""
    monkeypatch.setenv("SOME_HARMLESS_VAR", "hello")
    env = build_env()
    assert env.get("SOME_HARMLESS_VAR") == "hello"


def test_build_env_strips_secret_shaped_names(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("SOME_TOKEN", "also-should-not-leak")
    monkeypatch.setenv("MY_SECRET", "nor-this")
    monkeypatch.setenv("DB_PASSWORD", "nor-this-either")
    env = build_env()
    assert "ANTHROPIC_API_KEY" not in env
    assert "SOME_TOKEN" not in env
    assert "MY_SECRET" not in env
    assert "DB_PASSWORD" not in env


def test_run_claude_never_inherits_own_stdin(mock_claude_popen):
    """agent-bridge's own stdin is the MCP stdio pipe to the chat client — if
    inherited, claude waits ~3s for piped input, warns, and (per real-world
    reproduction) can fail. The prompt is always passed via -p, so stdin must
    be explicitly closed."""
    mock_claude_popen["proc"].stdout_val = '{"result": "ok"}'
    run_claude("claude", _inv())
    assert mock_claude_popen["last_kwargs"]["stdin"] == subprocess.DEVNULL


def test_run_claude_timeout_sends_sigterm_then_sigkill(monkeypatch, mock_claude_popen):
    killpg_calls = []
    monkeypatch.setattr(
        "agent_bridge.runner.os.killpg", lambda pid, sig: killpg_calls.append(sig)
    )

    def effect(call_number):
        if call_number == 1:
            return subprocess.TimeoutExpired(cmd="claude", timeout=30)
        if call_number == 2:
            return subprocess.TimeoutExpired(cmd="claude", timeout=10)
        return ("", "")

    mock_claude_popen["proc"]._effect = effect
    result = run_claude("claude", _inv(timeout_s=1))
    assert result.timed_out is True
    import signal

    assert killpg_calls == [signal.SIGTERM, signal.SIGKILL]


def test_run_claude_binary_not_found(mock_claude_popen):
    mock_claude_popen["proc"] = FileNotFoundError()
    with pytest.raises(ClaudeBinaryNotFoundError) as exc_info:
        run_claude("claude", _inv())
    assert "claude" in str(exc_info.value)
