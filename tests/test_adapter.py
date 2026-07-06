import json

from agent_bridge.adapter import parse_claude_json


def test_parse_happy_path():
    stdout = json.dumps(
        {
            "result": "# Plan\n1. do the thing",
            "session_id": "sess-abc123",
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "cost_usd": 0.0123,
        }
    )
    parsed = parse_claude_json(stdout)
    assert parsed.parse_ok is True
    assert parsed.result_text == "# Plan\n1. do the thing"
    assert parsed.usage == {"input_tokens": 100, "output_tokens": 50}
    assert parsed.cost_usd == 0.0123
    assert parsed.backend_session_id == "sess-abc123"
    assert parsed.warnings == []


def test_parse_malformed_json_does_not_raise():
    parsed = parse_claude_json("not json at all {{{")
    assert parsed.parse_ok is False
    assert parsed.result_text is None
    assert parsed.raw_output == "not json at all {{{"
    assert any("failed to parse" in w for w in parsed.warnings)


def test_parse_missing_usage_warns_but_does_not_fabricate():
    stdout = json.dumps({"result": "ok", "session_id": "s1"})
    parsed = parse_claude_json(stdout)
    assert parsed.parse_ok is True
    assert parsed.usage is None
    assert any("usage" in w for w in parsed.warnings)
