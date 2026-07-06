"""JSON-parsing seam for `claude -p --output-format json` stdout.

This is the ONLY module that knows claude's real JSON shape. Field names below
are placeholder guesses pending empirical verification (SPEC §2, §6) — update
ONLY here once confirmed; nothing else in the codebase should reach into raw
claude JSON directly. See README.md "実測結果" section once filled in.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class ParsedClaudeOutput:
    raw_output: str
    result_text: str | None
    usage: dict | None
    cost_usd: float | None
    backend_session_id: str | None
    warnings: list[str] = field(default_factory=list)
    parse_ok: bool = True


def parse_claude_json(stdout: str) -> ParsedClaudeOutput:
    try:
        obj = json.loads(stdout)
    except json.JSONDecodeError:
        return ParsedClaudeOutput(
            raw_output=stdout,
            result_text=None,
            usage=None,
            cost_usd=None,
            backend_session_id=None,
            warnings=["failed to parse claude stdout as JSON; returning raw text"],
            parse_ok=False,
        )

    # PLACEHOLDER key names — confirm against a real
    # `claude -p --output-format json` run and adjust ONLY here.
    result_text = obj.get("result") or obj.get("response") or obj.get("content")
    usage = obj.get("usage")  # passed through verbatim, never fabricated
    cost_usd = obj.get("cost_usd")
    if cost_usd is None:
        cost_usd = obj.get("total_cost_usd")
    backend_session_id = obj.get("session_id") or obj.get("backend_session_id")

    warnings: list[str] = []
    if usage is None:
        warnings.append("no usage field found in claude output")
    if backend_session_id is None:
        warnings.append("no session_id field found in claude output")

    return ParsedClaudeOutput(
        raw_output=stdout,
        result_text=result_text,
        usage=usage,
        cost_usd=cost_usd,
        backend_session_id=backend_session_id,
        warnings=warnings,
        parse_ok=True,
    )
