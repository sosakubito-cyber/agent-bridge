"""Sensitive-repo guardrail (SPEC §5-8): isolated so it is unit-testable without
depending on backend=cursor actually being implemented (it isn't, until v1) —
the check must already be correct on day one of v1's cursor support.
"""

from __future__ import annotations

from agent_bridge.config import RepoEntry
from agent_bridge.errors import SensitiveRepoGuardError

FABLE_MODEL = "claude-fable-5"


def check_sensitive_repo(
    repo: RepoEntry,
    *,
    backend: str,
    model: str,
    confirm_sensitive_model: bool = False,
) -> None:
    """Raises SensitiveRepoGuardError if a sensitive repo is used with backend=cursor
    or model=claude-fable-5 without an explicit override. Naming a model explicitly
    is not itself an override — confirm_sensitive_model must also be set.
    """
    if not repo.sensitive:
        return
    if backend == "cursor":
        raise SensitiveRepoGuardError(
            f"repo '{repo.alias}' is sensitive; backend=cursor is rejected by default "
            "(no override exists for backend — cursor is not implemented until v1)"
        )
    if model == FABLE_MODEL and not confirm_sensitive_model:
        raise SensitiveRepoGuardError(
            f"repo '{repo.alias}' is sensitive; model={FABLE_MODEL} requires "
            "confirm_sensitive_model=true in addition to naming the model explicitly"
        )
