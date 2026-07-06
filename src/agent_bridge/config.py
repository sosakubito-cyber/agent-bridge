"""Load and validate ~/.agent-bridge/config.json."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from agent_bridge import paths
from agent_bridge.errors import ConfigError, UnregisteredRepoError

# Hard ceiling regardless of what a config file claims — see SPEC §3.3 execute.timeout_min.
MAX_TIMEOUT_MIN = 120


@dataclass(frozen=True)
class RepoEntry:
    alias: str
    path: Path
    default_backend: str = "claude"
    sensitive: bool = False


@dataclass(frozen=True)
class Config:
    repos: dict[str, RepoEntry] = field(default_factory=dict)
    default_backend: str = "claude"
    default_models: dict[str, str] = field(default_factory=dict)
    concurrency_limit: int = 2
    default_timeout_min: int = 30
    claude_binary: str = "claude"
    cursor_binary: str = "agent"


def _validate_raw_path(alias: str, raw_path: str) -> None:
    if ".." in Path(raw_path).parts:
        raise ConfigError(
            f"repo '{alias}': path '{raw_path}' contains '..' — traversal-looking paths are rejected"
        )


def load_config(path: Path | None = None) -> Config:
    path = path or paths.CONFIG_PATH
    if not path.exists():
        raise ConfigError(
            f"config file not found at {path}. Copy config.example.json there and edit it."
        )
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ConfigError(f"config file at {path} is not valid JSON: {e}") from e

    repos: dict[str, RepoEntry] = {}
    for alias, entry in raw.get("repos", {}).items():
        raw_path = entry["path"]
        _validate_raw_path(alias, raw_path)
        repos[alias] = RepoEntry(
            alias=alias,
            path=Path(raw_path).expanduser().resolve(),
            default_backend=entry.get("default_backend", "claude"),
            sensitive=entry.get("sensitive", False),
        )

    defaults = raw.get("defaults", {})
    limits = raw.get("limits", {})
    binaries = raw.get("binaries", {})

    return Config(
        repos=repos,
        default_backend=defaults.get("backend", "claude"),
        default_models=defaults.get("model", {"claude": "claude-sonnet-5", "cursor": "auto"}),
        concurrency_limit=limits.get("concurrency", 2),
        default_timeout_min=limits.get("timeout_min", 30),
        claude_binary=binaries.get("claude", "claude"),
        cursor_binary=binaries.get("cursor", "agent"),
    )


def resolve_repo(config: Config, alias: str) -> RepoEntry:
    repo = config.repos.get(alias)
    if repo is None:
        raise UnregisteredRepoError(
            f"'{alias}' is not a registered repo alias. Call list_repos to see valid aliases; "
            "raw paths are never accepted."
        )
    return repo
