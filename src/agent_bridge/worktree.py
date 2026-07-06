"""git worktree lifecycle for execute()'s isolated sandbox.

Branches (rather than a detached checkout) so the diff/merge story stays
normal git: the user can `git log`, cherry-pick, or `git merge agent-bridge/b-...`
by hand later — merging into the main branch is always a manual human step
(SPEC §5-2), never automated here.

Cleanup (`remove_worktree`) is NOT called anywhere in v0; execute() creates
worktrees but never removes them — that's intentional (a future `gc` tool is
v1, explicitly deferred per SPEC §9 milestones).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from agent_bridge import paths


def _current_branch(repo_path: Path) -> str:
    out = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def create_worktree(repo_path: Path, bridge_session_id: str) -> Path:
    dest = paths.WORKTREES_DIR / bridge_session_id
    dest.parent.mkdir(parents=True, exist_ok=True)
    current_branch = _current_branch(repo_path)
    branch_name = f"agent-bridge/{bridge_session_id}"
    subprocess.run(
        ["git", "worktree", "add", "-b", branch_name, str(dest), current_branch],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
    return dest


def remove_worktree(repo_path: Path, worktree_path: Path) -> None:
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree_path)],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
