"""get_diff: git diff (and changed-file list) for a session's worktree or repo."""

from __future__ import annotations

import subprocess
from pathlib import Path

from agent_bridge.config import Config, resolve_repo
from agent_bridge.envelope import NEXT_STEP_HINTS, make_envelope
from agent_bridge.registry import SessionRegistry

TOOL_NAME = "get_diff"


def _target_dir(config: Config, session) -> Path:
    if session.worktree:
        return Path(session.worktree)
    return resolve_repo(config, session.repo).path


async def handle(arguments: dict, *, config: Config, registry: SessionRegistry) -> dict:
    session_id = arguments["session_id"]
    stat_only = arguments.get("stat_only", False)
    session = registry.require(session_id)
    target_dir = _target_dir(config, session)

    diff_args = ["git", "diff"] + (["--stat"] if stat_only else [])
    diff = subprocess.run(
        diff_args, cwd=target_dir, capture_output=True, text=True, timeout=30, check=False
    )
    changed = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=target_dir,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    return {
        "diff": diff.stdout,
        "changed_files": [line for line in changed.stdout.splitlines() if line],
        **make_envelope(
            bridge_session_id=session.bridge_session_id,
            backend=session.backend,
            model=session.model,
            usage=None,
            cost_usd=None,
            duration_s=0.0,
            warnings=[],
            next_step_hint=NEXT_STEP_HINTS["get_diff"],
        ),
    }
