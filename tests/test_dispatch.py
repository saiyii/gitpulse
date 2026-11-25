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
    await bot.db.subscribe(1, 10, "saiyii/nuclear-resource", frozenset({"releases"}), None)
    await bot.db.subscribe(1, 11, "saiyii/nuclear-resource", frozenset({"push"}), None)
    await bot.db.subscribe(1, 12, "saiyii/other", frozenset({"releases"}), None)

    await bot.handle_github_event("release", load("release_published"))

    assert bot.posted == [(10, "saiyii/nuclear-resource v2.3.0")]
    # installation id from the payload is remembered
    assert bot.github.installations == {"saiyii/nuclear-resource": 51234567}
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
