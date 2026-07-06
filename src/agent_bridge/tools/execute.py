"""execute: run an approved plan, optionally inside an isolated git worktree."""

from __future__ import annotations

import subprocess
from pathlib import Path

from agent_bridge.concurrency import acquire_slot
from agent_bridge.config import Config, MAX_TIMEOUT_MIN, resolve_repo
from agent_bridge.envelope import NEXT_STEP_HINTS, make_envelope
from agent_bridge.errors import ApprovalNotGrantedError, BridgeError, NoPlanArtifactError
from agent_bridge.logging_writer import LogEntry, append_log
from agent_bridge.registry import SessionRegistry
from agent_bridge.runner import ClaudeInvocation, run_claude
from agent_bridge.worktree import create_worktree

TOOL_NAME = "execute"

INJECTED_CLAUSE = (
    "コミットは Conventional Commits で作成してよいが、push は行わない。"
    "完了時に変更ファイル一覧と要約を出力すること。"
)

STDERR_TAIL_CHARS = 2000


def _build_execute_prompt(instructions: str | None) -> str:
    base = instructions or "承認済みのプランを実行してください。"
    return f"{base}\n\n---\n{INJECTED_CLAUSE}"


def _git(args: list[str], cwd: Path) -> str:
    out = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30, check=False
    )
    return out.stdout


async def handle(arguments: dict, *, config: Config, registry: SessionRegistry) -> dict:
    approved = arguments.get("approved")
    if approved is not True:
        raise ApprovalNotGrantedError("`approved` must be literally true")

    session_id = arguments["session_id"]
    session = registry.require(session_id)
    if not session.has_plan:
        raise NoPlanArtifactError(
            f"session '{session_id}' has no prior plan() call; call plan first"
        )

    instructions = arguments.get("instructions")
    mode = arguments.get("mode", "acceptEdits")
    use_worktree = arguments.get("use_worktree", True)
    timeout_min = min(arguments.get("timeout_min", 30), MAX_TIMEOUT_MIN)

    repo = resolve_repo(config, session.repo)

    if use_worktree:
        cwd = create_worktree(repo.path, session.bridge_session_id)
        session = registry.update(session.bridge_session_id, worktree=str(cwd))
    else:
        cwd = repo.path

    base_commit = _git(["rev-parse", "HEAD"], cwd).strip()

    prompt = _build_execute_prompt(instructions)
    inv = ClaudeInvocation(
        prompt=prompt,
        cwd=cwd,
        permission_mode=mode,
        model=session.model,
        resume_backend_session_id=session.backend_session_id,
        timeout_s=timeout_min * 60,
    )
    registry.update(session.bridge_session_id, phase="executing")
    with acquire_slot():
        result = run_claude(config.claude_binary, inv)

    phase = "done" if (result.exit_code == 0 and not result.timed_out) else "failed"
    session = registry.update(
        session.bridge_session_id,
        phase=phase,
        cost_usd_total=session.cost_usd_total + (result.parsed.cost_usd or 0.0),
    )

    append_log(
        LogEntry(
            ts=session.created_at,
            tool=TOOL_NAME,
            backend=session.backend,
            model=session.model,
            repo=session.repo,
            bridge_session_id=session.bridge_session_id,
            duration_s=result.duration_s,
            usage=result.parsed.usage,
            cost_usd=result.parsed.cost_usd,
            exit_code=result.exit_code,
        )
    )

    changed_files = [
        line for line in _git(["diff", "--name-only", base_commit], cwd).splitlines() if line
    ]

    if result.exit_code != 0:
        raise BridgeError(
            f"claude exited {result.exit_code}: {result.stderr[-STDERR_TAIL_CHARS:]}"
        )

    return {
        "result_markdown": result.parsed.result_text,
        "changed_files": changed_files,
        "exit_code": result.exit_code,
        **make_envelope(
            bridge_session_id=session.bridge_session_id,
            backend=session.backend,
            model=session.model,
            usage=result.parsed.usage,
            cost_usd=result.parsed.cost_usd,
            duration_s=result.duration_s,
            warnings=result.parsed.warnings,
            next_step_hint=NEXT_STEP_HINTS["execute"],
        ),
    }
