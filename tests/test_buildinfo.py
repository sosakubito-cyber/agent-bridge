import re
from datetime import datetime

from agent_bridge import buildinfo


def test_bridge_build_is_short_sha_or_unknown():
    assert buildinfo.BRIDGE_BUILD == "unknown" or re.fullmatch(
        r"[0-9a-f]{4,40}", buildinfo.BRIDGE_BUILD
    )


def test_started_at_is_iso8601():
    datetime.fromisoformat(buildinfo.STARTED_AT)
