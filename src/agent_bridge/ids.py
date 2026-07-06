"""bridge_session_id generation: b-YYYYMMDD-<4 hex>."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone


def new_bridge_session_id(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"b-{now:%Y%m%d}-{secrets.token_hex(2)}"
