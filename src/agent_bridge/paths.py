"""Single source of truth for ~/.agent-bridge/* locations.

Kept in its own module (rather than inlined in config.py etc.) so tests can
monkeypatch BRIDGE_HOME to a tmp_path without touching the real directory.
"""

from pathlib import Path

BRIDGE_HOME = Path.home() / ".agent-bridge"
CONFIG_PATH = BRIDGE_HOME / "config.json"
SESSIONS_PATH = BRIDGE_HOME / "sessions.json"
LOG_DIR = BRIDGE_HOME / "log"
WORKTREES_DIR = BRIDGE_HOME / "worktrees"


def ensure_bridge_home() -> None:
    BRIDGE_HOME.mkdir(mode=0o700, parents=True, exist_ok=True)
    LOG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    WORKTREES_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
