from pathlib import Path

import pytest

from gitpulse.db import Database


@pytest.fixture
async def db(tmp_path: Path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


async def test_subscribe_and_lookup(db: Database):
    await db.subscribe(1, 10, "saiyii/gitpulse", frozenset({"releases", "push"}), None)
    await db.subscribe(1, 11, "saiyii/gitpulse", frozenset({"issues"}), None)

    assert [s.channel_id for s in await db.subscribers("saiyii/gitpulse", "push")] == [10]
    assert [s.channel_id for s in await db.subscribers("saiyii/gitpulse", "issues")] == [11]
    assert await db.subscribers("saiyii/gitpulse", "pulls") == []


async def test_repo_name_is_case_insensitive(db: Database):
    await db.subscribe(1, 10, "Saiyii/GitPulse", frozenset({"releases"}), None)
    assert len(await db.subscribers("saiyii/gitpulse", "releases")) == 1


async def test_resubscribe_updates_events(db: Database):
    await db.subscribe(1, 10, "saiyii/gitpulse", frozenset({"releases"}), 42)
    await db.subscribe(1, 10, "saiyii/gitpulse", frozenset({"push"}), None)

    [sub] = await db.guild_subscriptions(1)
    assert sub.events == {"push"}
    # a later subscribe without installation id must not wipe the known one
    assert sub.installation_id == 42


async def test_unsubscribe(db: Database):
    await db.subscribe(1, 10, "saiyii/gitpulse", frozenset({"releases"}), None)
    assert await db.unsubscribe(10, "saiyii/gitpulse") is True
    assert await db.unsubscribe(10, "saiyii/gitpulse") is False
    assert await db.guild_subscriptions(1) == []


async def test_set_installation(db: Database):
    await db.subscribe(1, 10, "saiyii/gitpulse", frozenset({"releases"}), None)
    await db.set_installation("saiyii/gitpulse", 99)
    [sub] = await db.guild_subscriptions(1)
    assert sub.installation_id == 99
