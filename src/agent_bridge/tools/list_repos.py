"""list_repos: no args, returns configured repo aliases and defaults."""

from __future__ import annotations

from agent_bridge import buildinfo
from agent_bridge.config import Config

TOOL_NAME = "list_repos"


async def handle(arguments: dict, *, config: Config, registry=None) -> dict:
    return {
        "repos": [
            {
                "alias": r.alias,
                "path": str(r.path),
                "default_backend": r.default_backend,
            }
            for r in config.repos.values()
        ],
        "defaults": {
            "backend": config.default_backend,
            "model": config.default_models,
        },
        "bridge_build": buildinfo.BRIDGE_BUILD,
        "started_at": buildinfo.STARTED_AT,
    }
