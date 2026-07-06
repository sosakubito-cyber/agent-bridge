"""usage_report (addendum A3): aggregate ~/.agent-bridge/log/*.jsonl by period/group_by.

Aggregates whatever numeric fields exist inside each log entry's `usage` dict
generically (no hardcoded token-field names) since the real claude usage JSON
shape is confirmed empirically per repo (see README.md) and this module
shouldn't need editing when that shape is refined.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from agent_bridge import paths
from agent_bridge.config import Config
from agent_bridge.envelope import NEXT_STEP_HINTS, make_envelope

TOOL_NAME = "usage_report"

DISCLAIMER = (
    "注記: cost_usd はヘッドレスCLIが同梱価格表からクライアント側で計算する推計値であり、"
    "請求の正とは乖離しうる。課金の正は claude.ai の設定 > 使用量、または Console / Usage and "
    "Cost API を参照。チャット側(claude.ai)の Fable 消費は bridge から観測不能。"
)


def _period_start(period: str, now: datetime) -> datetime | None:
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        return now - timedelta(days=7)
    if period == "month":
        return now - timedelta(days=30)
    return None  # "all"


def _iter_log_entries(now: datetime, period: str):
    if not paths.LOG_DIR.exists():
        return
    start = _period_start(period, now)
    for log_file in sorted(paths.LOG_DIR.glob("*.jsonl")):
        try:
            file_date = datetime.strptime(log_file.stem, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if start is not None and file_date < start.replace(hour=0, minute=0, second=0, microsecond=0):
            continue
        for line in log_file.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _to_markdown_table(groups: dict[str, dict]) -> str:
    if not groups:
        return "(該当ログなし)"
    numeric_keys: list[str] = []
    for g in groups.values():
        for k in g.get("usage_totals", {}):
            if k not in numeric_keys:
                numeric_keys.append(k)
    headers = ["group", "calls", *numeric_keys, "cost_usd"]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for name, g in sorted(groups.items()):
        row = [name, str(g["calls"])]
        row += [str(round(g["usage_totals"].get(k, 0), 3)) for k in numeric_keys]
        row.append(str(round(g["cost_usd"], 4)))
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


async def handle(arguments: dict, *, config: Config, registry=None) -> dict:
    period = arguments.get("period", "week")
    group_by = arguments.get("group_by", "model")

    now = datetime.now(timezone.utc)
    groups: dict[str, dict] = {}
    total_cost = 0.0
    total_calls = 0

    for entry in _iter_log_entries(now, period):
        key = entry.get(group_by) or "unknown"
        g = groups.setdefault(key, {"calls": 0, "usage_totals": {}, "cost_usd": 0.0})
        g["calls"] += 1
        total_calls += 1
        cost = entry.get("cost_usd") or 0.0
        g["cost_usd"] += cost
        total_cost += cost
        usage = entry.get("usage") or {}
        for k, v in usage.items():
            if isinstance(v, (int, float)):
                g["usage_totals"][k] = g["usage_totals"].get(k, 0) + v

    table = _to_markdown_table(groups)

    return {
        "period": period,
        "group_by": group_by,
        "table_markdown": table,
        "total_calls": total_calls,
        "total_cost_usd": round(total_cost, 4),
        "disclaimer": DISCLAIMER,
        **make_envelope(
            bridge_session_id="n/a",
            backend="claude",
            model=None,
            usage=None,
            cost_usd=round(total_cost, 4),
            duration_s=0.0,
            warnings=[],
            next_step_hint=NEXT_STEP_HINTS["usage_report"],
        ),
    }
