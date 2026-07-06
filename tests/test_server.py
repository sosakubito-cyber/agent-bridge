import mcp.types as types
import pytest

from agent_bridge.registry import SessionRegistry
from agent_bridge.server import build_server


@pytest.fixture
def call_tool(fake_config, tmp_bridge_home):
    registry = SessionRegistry()
    server = build_server(fake_config, registry)
    handler = server.request_handlers[types.CallToolRequest]

    async def _call(name: str, arguments: dict) -> types.CallToolResult:
        req = types.CallToolRequest(
            method="tools/call",
            params=types.CallToolRequestParams(name=name, arguments=arguments),
        )
        return (await handler(req)).root

    return _call


async def test_successful_call_sets_structured_content_and_no_error(call_tool):
    result = await call_tool("list_repos", {})
    assert result.isError is False
    assert result.structuredContent is not None
    assert "repos" in result.structuredContent
    assert len(result.content) == 1
    assert result.content[0].type == "text"


async def test_unknown_tool_sets_protocol_level_error(call_tool):
    result = await call_tool("nonexistent-tool", {})
    assert result.isError is True
    assert "nonexistent-tool" in result.content[0].text


async def test_bridge_error_sets_protocol_level_error(call_tool):
    result = await call_tool("get_diff", {"session_id": "no-such-session"})
    assert result.isError is True
    assert "no-such-session" in result.content[0].text
