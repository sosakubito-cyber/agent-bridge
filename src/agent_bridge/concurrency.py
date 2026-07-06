"""Process-wide concurrency limit (SPEC §5-5: max concurrent executions).

A single in-process BoundedSemaphore suffices: agent-bridge is one stdio
process per Claude Desktop session, so it doesn't need cross-process
coordination (unlike the session registry file, which the semaphore is not a
substitute for).
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

_semaphore: threading.BoundedSemaphore | None = None


def init_concurrency(limit: int) -> None:
    global _semaphore
    _semaphore = threading.BoundedSemaphore(limit)


@contextmanager
def acquire_slot() -> Iterator[None]:
    if _semaphore is None:
        init_concurrency(2)
    assert _semaphore is not None
    _semaphore.acquire()
    try:
        yield
    finally:
        _semaphore.release()
