import json
from datetime import datetime, timezone

from agent_bridge import paths
from agent_bridge.tools import usage_report


def _write_log_entries(entries):
    paths.LOG_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_path = paths.LOG_DIR / f"{today}.jsonl"
    with open(log_path, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


async def test_usage_report_aggregates_by_model(tmp_bridge_home, fake_config):
    _write_log_entries(
        [
            {
                "tool": "plan",
                "model": "claude-sonnet-5",
                "backend": "claude",
                "repo": "sample",
                "usage": {"input_tokens": 100, "output_tokens": 50},
                "cost_usd": 0.01,
            },
            {
                "tool": "execute",
                "model": "claude-sonnet-5",
                "backend": "claude",
                "repo": "sample",
                "usage": {"input_tokens": 200, "output_tokens": 80},
                "cost_usd": 0.02,
            },
            {
                "tool": "plan",
                "model": "claude-fable-5",
                "backend": "claude",
                "repo": "sample",
                "usage": {"input_tokens": 10, "output_tokens": 5},
                "cost_usd": 0.001,
            },
        ]
    )

    result = await usage_report.handle(
        {"period": "today", "group_by": "model"}, config=fake_config, registry=None
    )
    assert result["total_calls"] == 3
    assert round(result["total_cost_usd"], 3) == round(0.01 + 0.02 + 0.001, 3)
    assert "claude-sonnet-5" in result["table_markdown"]
    assert "claude-fable-5" in result["table_markdown"]
    assert "推計値" in result["disclaimer"]
    assert "claude.ai" in result["disclaimer"]


async def test_usage_report_empty_log_does_not_crash(tmp_bridge_home, fake_config):
    result = await usage_report.handle({}, config=fake_config, registry=None)
    assert result["total_calls"] == 0
    assert result["total_cost_usd"] == 0
