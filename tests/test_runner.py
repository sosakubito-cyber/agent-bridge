import subprocess
from pathlib import Path

import pytest

from agent_bridge.errors import ClaudeBinaryNotFoundError
from agent_bridge.runner import ClaudeInvocation, build_argv, run_claude


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
