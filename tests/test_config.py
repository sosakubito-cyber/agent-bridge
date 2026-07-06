import json

import pytest

from agent_bridge.config import load_config, resolve_repo
from agent_bridge.errors import ConfigError, UnregisteredRepoError


def test_load_config_happy_path(fake_config):
    assert "sample" in fake_config.repos
    assert "sensitive-repo" in fake_config.repos
    assert fake_config.repos["sensitive-repo"].sensitive is True
    assert fake_config.repos["sample"].sensitive is False
    assert fake_config.default_backend == "claude"
    assert fake_config.default_models["claude"] == "claude-sonnet-5"


def test_load_config_missing_file(tmp_bridge_home):
    with pytest.raises(ConfigError):
        load_config()


def test_load_config_malformed_json(tmp_bridge_home):
    from agent_bridge import paths

    paths.CONFIG_PATH.write_text("{not valid json")
    with pytest.raises(ConfigError):
        load_config()


def test_load_config_rejects_dotdot_path(tmp_bridge_home):
    from agent_bridge import paths

    paths.CONFIG_PATH.write_text(
        json.dumps({"repos": {"evil": {"path": "/tmp/../etc"}}})
    )
    with pytest.raises(ConfigError):
        load_config()


def test_resolve_repo_unregistered_alias(fake_config):
    with pytest.raises(UnregisteredRepoError):
        resolve_repo(fake_config, "not-a-real-alias")


def test_resolve_repo_happy_path(fake_config):
    repo = resolve_repo(fake_config, "sample")
    assert repo.alias == "sample"
