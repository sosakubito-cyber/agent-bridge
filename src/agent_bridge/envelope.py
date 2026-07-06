"""Common response envelope + A1 next_step_hint contract text."""

from __future__ import annotations

NEXT_STEP_HINTS = {
    "plan": (
        "Present the plan to the user for critique; wait for explicit approval "
        "(e.g. 'OK', 'go ahead') before calling execute."
    ),
    "execute": (
        "Call get_diff and present the diff for review before considering the task done."
    ),
    "get_diff": "Present this diff to the user for review.",
    "status": "Use this to check whether the session is safe to act on further.",
    "usage_report": (
        "This reflects only bridge-initiated headless usage, not chat-side (claude.ai) usage. "
        "cost_usd is a client-side estimate, not a billing source of truth."
    ),
}


def make_envelope(
    *,
    bridge_session_id: str,
    backend: str,
    model: str | None,
    usage: dict | None,
    cost_usd: float | None,
    duration_s: float,
    warnings: list[str],
    next_step_hint: str,
) -> dict:
    return {
        "bridge_session_id": bridge_session_id,
        "backend": backend,
        "model": model,
        "usage": usage,
        "cost_usd": cost_usd,
        "duration_s": duration_s,
        "warnings": warnings,
        "next_step_hint": next_step_hint,
    }
