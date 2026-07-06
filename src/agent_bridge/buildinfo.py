"""Server build/staleness identification.

The MCP server is a long-running process started once when Claude Desktop
launches it; it does not hot-reload on source edits (see README "運用注意").
Stamping the running process with the commit it was started from and its
start time lets a caller (list_repos/status) tell, in a single call, whether
they're talking to a server that has picked up a given fix yet.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _git_short_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    sha = result.stdout.strip()
    return sha if result.returncode == 0 and sha else "unknown"


# Computed once, at first import (i.e. server process startup) — not per-call.
BRIDGE_BUILD: str = _git_short_sha()
STARTED_AT: str = datetime.now(timezone.utc).isoformat()
