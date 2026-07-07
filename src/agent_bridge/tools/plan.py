"""plan: ask the claude backend for a plan, without modifying files.

Creates the worktree here (not just in execute()) when use_worktree is on, and
runs the plan-mode claude invocation with cwd already inside it. execute()
then resumes the same backend session from that same cwd. Previously plan()
ran in repo.path while execute() resumed the same session from a worktree
cwd — claude's directory-scoped tool permissions are tied to the session's
working directory, so the resumed session found files from repo.path outside
its allowed scope and silently denied reads (e.g. "README.md 読み取りの権限が
まだ許可されていない"), even though the OS-level file permissions were fine.
"""

from __future__ import annotations

from pathlib import Path

from agent_bridge.config import Config, resolve_repo
from agent_bridge.concurrency import acquire_slot
from agent_bridge.envelope import NEXT_STEP_HINTS, make_envelope
from agent_bridge.errors import BridgeError, CursorNotImplementedError
from agent_bridge.guardrails import FABLE_MODEL, check_sensitive_repo
from agent_bridge.logging_writer import LogEntry, append_log
from agent_bridge.registry import SessionRegistry
from agent_bridge.runner import ClaudeInvocation, run_claude
from agent_bridge.worktree import create_worktree

TOOL_NAME = "plan"

STDERR_TAIL_CHARS = 2000


def _build_plan_prompt(task: str, context: str | None) -> str:
    if context:
        return f"{task}\n\n---\n追加文脈:\n{context}"
    return task


async def handle(arguments: dict, *, config: Config, registry: SessionRegistry) -> dict:
    backend = arguments.get("backend", "claude")
    if backend != "claude":
        raise CursorNotImplementedError("backend='cursor' is not implemented in v0")

    task = arguments["task"]
    repo_alias = arguments["repo"]
    context = arguments.get("context")
    session_id = arguments.get("session_id")
    confirm_sensitive_model = arguments.get("confirm_sensitive_model", False)

    model_arg = arguments.get("model")
    model = model_arg or config.default_models.get("claude", "claude-sonnet-5")
    if model == FABLE_MODEL and model_arg != FABLE_MODEL:
        raise BridgeError(
            "claude-fable-5 must be passed explicitly as `model`, never resolved from defaults"
        )

    repo = resolve_repo(config, repo_alias)
    check_sensitive_repo(
        repo, backend=backend, model=model, confirm_sensitive_model=confirm_sensitive_model
    )

    if session_id:
        session = registry.require(session_id)
    else:
        session = registry.create(backend="claude", repo=repo_alias, model=model)

    use_worktree = arguments.get("use_worktree", True)
    if session.worktree:
        cwd = Path(session.worktree)
    elif use_worktree:
        cwd = create_worktree(repo.path, session.bridge_session_id)
        session = registry.update(session.bridge_session_id, worktree=str(cwd))
    else:
        cwd = repo.path

    prompt = _build_plan_prompt(task, context)
    inv = ClaudeInvocation(
        prompt=prompt,
        cwd=cwd,
        permission_mode="plan",
        model=model,
        resume_backend_session_id=session.backend_session_id,
        timeout_s=config.default_timeout_min * 60,
    )
    with acquire_slot():
        result = run_claude(config.claude_binary, inv)

    new_backend_session_id = result.parsed.backend_session_id or session.backend_session_id
    success = result.exit_code == 0
    session = registry.update(
        session.bridge_session_id,
        phase="planned" if success else "failed",
        backend_session_id=new_backend_session_id,
        has_plan=success or session.has_plan,
        cost_usd_total=session.cost_usd_total + (result.parsed.cost_usd or 0.0),
    )

    append_log(
        LogEntry(
            ts=session.created_at,
            tool=TOOL_NAME,
            backend=backend,
            model=model,
            repo=repo_alias,
            bridge_session_id=session.bridge_session_id,
            duration_s=result.duration_s,
            usage=result.parsed.usage,
            cost_usd=result.parsed.cost_usd,
            exit_code=result.exit_code,
        )
    )

    if result.exit_code != 0:
        raise BridgeError(
            f"claude exited {result.exit_code}: {result.stderr[-STDERR_TAIL_CHARS:]}"
        )

    return {
        "plan_markdown": result.parsed.result_text,
        "backend_session_id": new_backend_session_id,
        **make_envelope(
            bridge_session_id=session.bridge_session_id,
            backend=backend,
            model=model,
            usage=result.parsed.usage,
            cost_usd=result.parsed.cost_usd,
            duration_s=result.duration_s,
            warnings=result.parsed.warnings,
            next_step_hint=NEXT_STEP_HINTS["plan"],
        ),
    }
