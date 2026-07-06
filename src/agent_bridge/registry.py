"""Session registry: ~/.agent-bridge/sessions.json, guarded by an exclusive file lock.

POSIX-only locking (fcntl). This targets Mac usage per SPEC; Windows callers get
no cross-process safety (fcntl is unavailable there) — not solved further, see
README v1 TODO.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

from agent_bridge import paths
from agent_bridge.errors import UnknownSessionError
from agent_bridge.ids import new_bridge_session_id

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

Phase = Literal["planned", "executing", "done", "failed"]


@dataclass
class SessionRecord:
    bridge_session_id: str
    backend: str
    backend_session_id: str | None
    repo: str
    worktree: str | None
    model: str
    created_at: str
    phase: Phase
    has_plan: bool
    cost_usd_total: float

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SessionRecord":
        return cls(**data)


class SessionRegistry:
    def __init__(self, path: Path | None = None):
        self.path = path or paths.SESSIONS_PATH

    @contextmanager
    def _locked(self) -> Iterator[dict[str, dict]]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX)
            raw = b""
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                raw += chunk
            data: dict[str, dict] = json.loads(raw) if raw.strip() else {}
            yield data
            serialized = json.dumps(data, indent=2, default=str).encode()
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            os.write(fd, serialized)
        finally:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def create(self, *, backend: str, repo: str, model: str) -> SessionRecord:
        with self._locked() as data:
            record = SessionRecord(
                bridge_session_id=new_bridge_session_id(),
                backend=backend,
                backend_session_id=None,
                repo=repo,
                worktree=None,
                model=model,
                created_at=datetime.now(timezone.utc).isoformat(),
                phase="planned",
                has_plan=False,
                cost_usd_total=0.0,
            )
            data[record.bridge_session_id] = record.to_dict()
            return record

    def get(self, bridge_session_id: str) -> SessionRecord | None:
        with self._locked() as data:
            raw = data.get(bridge_session_id)
            return SessionRecord.from_dict(raw) if raw is not None else None

    def require(self, bridge_session_id: str) -> SessionRecord:
        record = self.get(bridge_session_id)
        if record is None:
            raise UnknownSessionError(f"unknown session_id '{bridge_session_id}'")
        return record

    def update(self, bridge_session_id: str, **fields) -> SessionRecord:
        with self._locked() as data:
            raw = data.get(bridge_session_id)
            if raw is None:
                raise UnknownSessionError(f"unknown session_id '{bridge_session_id}'")
            raw.update(fields)
            data[bridge_session_id] = raw
            return SessionRecord.from_dict(raw)

    def list_all(self) -> list[SessionRecord]:
        with self._locked() as data:
            return [SessionRecord.from_dict(v) for v in data.values()]
