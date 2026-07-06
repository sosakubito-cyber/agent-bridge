"""Subprocess runner: spawns `claude -p ...`, enforces a timeout via
SIGTERM -> grace period -> SIGKILL, and hands stdout to adapter.parse_claude_json().

Does not know about MCP tool semantics — pure "run claude, get a structured result".
"""

from __future__ import annotations

import os
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path
from subprocess import DEVNULL, PIPE, Popen, TimeoutExpired
from typing import Literal

from agent_bridge import adapter
from agent_bridge.errors import ClaudeBinaryNotFoundError
from agent_bridge.logging_writer import is_secret_env_name

GRACE_PERIOD_S = 10.0

# SPEC §5-6 originally allowlisted just PATH/HOME/LANG/LC_ALL/TERM for
# subprocess env, on the theory that a minimal environment is safer. In
# practice this broke claude's OAuth/keychain-based auth (the "claude.ai"
# login method used by Pro/Max subscriptions): `claude auth status` reported
# loggedIn:false even with HOME set, because macOS Keychain access needs
# something closer to the caller's real login-session environment (USER was
# the minimum needed to reproduce a fix, but Keychain's actual requirements
# aren't fully enumerable without inspecting credential internals, which we
# deliberately avoid). Switched to a BLOCKLIST: inherit the full parent
# environment, but drop anything whose name looks like a secret — reusing
# the same API_KEY/TOKEN/SECRET/PASSWORD heuristic logging_writer.py already
# uses to decide what never gets logged (e.g. ANTHROPIC_API_KEY is dropped).


@dataclass
class ClaudeInvocation:
    prompt: str
    cwd: Path
    permission_mode: Literal["plan", "acceptEdits", "default"]
    model: str
    resume_backend_session_id: str | None = None
    extra_args: list[str] = field(default_factory=list)
    timeout_s: int = 1800


@dataclass
class ClaudeRunResult:
    exit_code: int | None
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool
    parsed: adapter.ParsedClaudeOutput


def build_env(passthrough: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not is_secret_env_name(k)}
    if passthrough:
        env.update(passthrough)
    return env


def build_argv(binary: str, inv: ClaudeInvocation) -> list[str]:
    argv = [
        binary,
        "-p",
        inv.prompt,
        "--permission-mode",
        inv.permission_mode,
        "--model",
        inv.model,
        "--output-format",
        "json",
    ]
    if inv.resume_backend_session_id:
        argv += ["--resume", inv.resume_backend_session_id]
    argv += inv.extra_args
    return argv


def run_claude(binary: str, inv: ClaudeInvocation) -> ClaudeRunResult:
    argv = build_argv(binary, inv)
    start = time.monotonic()
    try:
        proc = Popen(
            argv,
            cwd=inv.cwd,
            env=build_env(),
            stdin=DEVNULL,  # never inherit agent-bridge's own stdin (the MCP stdio
            # pipe to the chat client) — claude waits ~3s for piped stdin data
            # otherwise, warns, and proceeds; the prompt is always passed via -p.
            stdout=PIPE,
            stderr=PIPE,
            text=True,
            start_new_session=True,  # own process group, so timeout kill reaches children too
        )
    except FileNotFoundError as e:
        raise ClaudeBinaryNotFoundError(
            f"claude binary '{binary}' not found (ENOENT). Check config.json's "
            f"binaries.claude setting — configured value: '{binary}'."
        ) from e

    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=inv.timeout_s)
    except TimeoutExpired:
        timed_out = True
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            stdout, stderr = proc.communicate(timeout=GRACE_PERIOD_S)
        except TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()

    duration_s = time.monotonic() - start
    parsed = adapter.parse_claude_json(stdout)
    return ClaudeRunResult(
        exit_code=proc.returncode,
        stdout=stdout,
        stderr=stderr,
        duration_s=duration_s,
        timed_out=timed_out,
        parsed=parsed,
    )
