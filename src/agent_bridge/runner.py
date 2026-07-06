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
from subprocess import PIPE, Popen, TimeoutExpired
from typing import Literal

from agent_bridge import adapter
from agent_bridge.errors import ClaudeBinaryNotFoundError

GRACE_PERIOD_S = 10.0

# claude needs its own auth/config state; if it reads other env vars (e.g. a
# CLAUDE_CONFIG_DIR-style var), add here once confirmed empirically — this
# constant is the single edit point (mirrors adapter.py's seam pattern).
MINIMAL_ENV_ALLOWLIST = ("PATH", "HOME", "LANG", "LC_ALL", "TERM")


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
    env = {k: os.environ[k] for k in MINIMAL_ENV_ALLOWLIST if k in os.environ}
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
