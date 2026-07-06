"""MCP stdio entrypoint: registers the 6 v0 tools and wires shared dependencies.

Tool name/description/inputSchema are loaded from the repo's own tools.schema.json
(the canonical machine-readable tool contract) rather than re-declared in Python,
so the two never drift apart.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from agent_bridge import paths
from agent_bridge.concurrency import init_concurrency
from agent_bridge.config import Config, load_config
from agent_bridge.errors import BridgeError
from agent_bridge.registry import SessionRegistry
from agent_bridge.tools import execute, get_diff, list_repos, plan, status, usage_report

_TOOL_MODULES = [list_repos, plan, execute, get_diff, status, usage_report]
_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "tools.schema.json"


def _load_tool_definitions() -> list[types.Tool]:
    raw = json.loads(_SCHEMA_PATH.read_text())
    implemented = {mod.TOOL_NAME for mod in _TOOL_MODULES}
    return [
        types.Tool(name=t["name"], description=t["description"], inputSchema=t["inputSchema"])
        for t in raw["tools"]
        if t["name"] in implemented
    ]


def build_server(config: Config, registry: SessionRegistry) -> Server:
    server = Server("agent-bridge")
    dispatch = {mod.TOOL_NAME: mod.handle for mod in _TOOL_MODULES}

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return _load_tool_definitions()

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        handler = dispatch.get(name)
        if handler is None:
            error = {"isError": True, "content": [{"type": "text", "text": f"unknown tool '{name}'"}]}
            return [types.TextContent(type="text", text=json.dumps(error))]
        try:
            result = await handler(arguments, config=config, registry=registry)
        except BridgeError as e:
            return [types.TextContent(type="text", text=json.dumps(e.to_tool_result()))]
        return [types.TextContent(type="text", text=json.dumps(result, default=str))]

    return server


async def _main() -> None:
    paths.ensure_bridge_home()
    config = load_config()
    init_concurrency(config.concurrency_limit)
    registry = SessionRegistry()
    server = build_server(config, registry)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def run() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    run()
