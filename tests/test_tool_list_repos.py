from agent_bridge.tools import list_repos


async def test_list_repos_happy_path(fake_config):
    result = await list_repos.handle({}, config=fake_config, registry=None)
    aliases = {r["alias"] for r in result["repos"]}
    assert aliases == {"sample", "sensitive-repo"}
    assert result["defaults"]["backend"] == "claude"
    sample = next(r for r in result["repos"] if r["alias"] == "sample")
    assert sample["default_backend"] == "claude"
