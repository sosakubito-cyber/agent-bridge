"""Append-only JSONL log writer: ~/.agent-bridge/log/YYYY-MM-DD.jsonl.

One line per tool call. Secrets (env var values) are never logged — only argv
(minus the prompt text, which SPEC §6 explicitly says IS logged as ts/tool
level detail) and the parsed usage/cost/exit_code.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from agent_bridge import paths

_SECRET_NAME_RE = re.compile(r"(API_KEY|TOKEN|SECRET|PASSWORD)", re.IGNORECASE)


@dataclass
class LogEntry:
    ts: str
    tool: str
    backend: str
    model: str | None
    repo: str | None
    bridge_session_id: str | None
    duration_s: float
    usage: dict | None
    cost_usd: float | None
    exit_code: int | None


def append_log(entry: LogEntry) -> None:
    paths.LOG_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_path = paths.LOG_DIR / f"{today}.jsonl"
    line = json.dumps(asdict(entry), default=str)
    with open(log_path, "a") as f:
        f.write(line + "\n")


def is_secret_env_name(name: str) -> bool:
    """Used defensively if env ever needs to be logged for debugging — default
    behavior is to not log env at all."""
    return bool(_SECRET_NAME_RE.search(name))
