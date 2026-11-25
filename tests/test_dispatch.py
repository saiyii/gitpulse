import json
from pathlib import Path

import pytest

from gitpulse.bot import GitPulse
from gitpulse.config import Config

FIXTURES = Path(__file__).parent / "fixtures"


class FakeGitHub:
    def __init__(self) -> None:
        self.installations: dict[str, int] = {}

    def remember_installation(self, repo: str, installation_id: int) -> None:
        self.installations[repo] = installation_id

    def forget_installation(self, installation_id: int) -> None:
        self.installations = {r: i for r, i in self.installations.items() if i != installation_id}

    def forget_repo(self, repo: str) -> None:
        self.installations.pop(repo, None)


@pytest.fixture
async def bot(tmp_path: Path, monkeypatch):
    config = Config(
        discord_token="x",
        discord_guild_id=None,
        github_app_id="1",
        github_private_key="x",
        github_webhook_secret="secret",
        github_token=None,
        webhook_host="127.0.0.1",
        webhook_port=0,
        admin_role_name="Admin",
        support_email="support@example.com",
        push_all_branches=False,
        database_path=tmp_path / "test.db",
        log_level="INFO",
    )
    instance = GitPulse(config)
    instance.github = FakeGitHub()  # type: ignore[assignment]
    await instance.db.connect()

    posted: list[tuple[int, str]] = []

    async def fake_post(sub, embed):
        posted.append((sub.channel_id, embed.title))

    async def ready():
        return None

    monkeypatch.setattr(instance, "_post", fake_post)
    monkeypatch.setattr(instance, "wait_until_ready", ready)
    instance.posted = posted  # type: ignore[attr-defined]
    yield instance
    await instance.db.close()


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


async def test_release_goes_to_subscribed_channels(bot):
    await bot.db.subscribe(1, 10, "saiyii/gitpulse", frozenset({"releases"}), None)
    await bot.db.subscribe(1, 11, "saiyii/gitpulse", frozenset({"push"}), None)
    await bot.db.subscribe(1, 12, "saiyii/other", frozenset({"releases"}), None)

    await bot.handle_github_event("release", load("release_published"))

    assert bot.posted == [(10, "saiyii/gitpulse v1.1.0")]
    # installation id from the payload is remembered
    assert bot.github.installations == {"saiyii/gitpulse": 51234567}
    [sub, *_] = await bot.db.guild_subscriptions(1)
    assert sub.installation_id == 51234567


async def test_push_on_other_branch_is_skipped(bot):
    await bot.db.subscribe(1, 10, "saiyii/gitpulse", frozenset({"push"}), None)
    payload = load("push")
    payload["ref"] = "refs/heads/dev"

    await bot.handle_github_event("push", payload)
    assert bot.posted == []

    await bot.handle_github_event("push", load("push"))
    assert len(bot.posted) == 1


async def test_unhandled_event_is_ignored(bot):
    await bot.handle_github_event("star", {"action": "created", "repository": {"full_name": "a/b"}})
    assert bot.posted == []


async def test_uninstall_clears_installation(bot):
    await bot.db.subscribe(1, 10, "saiyii/gitpulse", frozenset({"releases"}), 51234567)
    await bot.db.subscribe(1, 11, "saiyii/other", frozenset({"releases"}), 999)
    bot.github.remember_installation("saiyii/gitpulse", 51234567)

    await bot.handle_github_event(
        "installation",
        {"action": "deleted", "installation": {"id": 51234567, "account": {"login": "saiyii"}}},
    )

    subs = {s.repo: s.installation_id for s in await bot.db.guild_subscriptions(1)}
    assert subs == {"saiyii/gitpulse": None, "saiyii/other": 999}
    assert bot.github.installations == {}


async def test_repo_removed_from_installation(bot):
    await bot.db.subscribe(1, 10, "saiyii/gitpulse", frozenset({"releases"}), 51234567)
    await bot.handle_github_event(
        "installation_repositories",
        {
            "action": "removed",
            "installation": {"id": 51234567, "account": {"login": "saiyii"}},
            "repositories_removed": [{"full_name": "saiyii/gitpulse"}],
        },
    )
    [sub] = await bot.db.guild_subscriptions(1)
    assert sub.installation_id is None


async def test_marketplace_purchase_is_logged(bot, caplog):
    payload = {
        "action": "purchased",
        "marketplace_purchase": {
            "account": {"type": "Organization", "login": "octo-org"},
            "plan": {"name": "Free"},
        },
    }
    with caplog.at_level("INFO", logger="gitpulse.bot"):
        await bot.handle_github_event("marketplace_purchase", payload)
    assert "marketplace: purchased by organization octo-org, plan 'Free'" in caplog.text
    assert bot.posted == []
