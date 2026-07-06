"""BridgeError hierarchy. Every error renders to an MCP isError tool result."""

from __future__ import annotations


class BridgeError(Exception):
    """Base class. Carries a short, corrective message for the calling chat model."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def to_tool_result(self) -> dict:
        return {"isError": True, "content": [{"type": "text", "text": self.message}]}


class ConfigError(BridgeError):
    """Missing/malformed ~/.agent-bridge/config.json, or a repo path containing '..'."""


class UnregisteredRepoError(BridgeError):
    """`repo` argument is not a known config alias (raw paths are always rejected)."""


class NoPlanArtifactError(BridgeError):
    """execute() called for a session with no prior successful plan() call."""


class ApprovalNotGrantedError(BridgeError):
    """execute() called without approved === true."""


class UnknownSessionError(BridgeError):
    """session_id does not exist in the registry."""


class ResumeFailedError(BridgeError):
    """--resume failed (e.g. expired backend session). Never silently starts a new one."""


class CursorNotImplementedError(BridgeError):
    """backend='cursor' requested; not implemented until v1."""


class SensitiveRepoGuardError(BridgeError):
    """Sensitive repo rejected backend=cursor or model=claude-fable-5 without override."""


class ClaudeBinaryNotFoundError(BridgeError):
    """subprocess spawn failed with ENOENT; message must include the configured path."""
