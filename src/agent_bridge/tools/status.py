"""status: list all sessions, or return detail for a single session_id."""

from __future__ import annotations

from datetime import datetime, timezone

from agent_bridge import buildinfo
from agent_bridge.config import Config
from agent_bridge.registry import SessionRegistry

TOOL_NAME = "status"


def _elapsed_s(created_at: str) -> float:
    created = datetime.fromisoformat(created_at)
    return (datetime.now(timezone.utc) - created).total_seconds()


async def handle(arguments: dict, *, config: Config, registry: SessionRegistry) -> dict:
    session_id = arguments.get("session_id")
    stamp = {"bridge_build": buildinfo.BRIDGE_BUILD, "started_at": buildinfo.STARTED_AT}
    if session_id:
        session = registry.require(session_id)
        return {"session": session.to_dict(), "elapsed_s": _elapsed_s(session.created_at), **stamp}
    return {"sessions": [s.to_dict() for s in registry.list_all()], **stamp}
