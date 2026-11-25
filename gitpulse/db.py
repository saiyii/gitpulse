from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import aiosqlite

# Names users type in /subscribe, and the webhook event each one maps to.
EVENT_TYPES: dict[str, str] = {
    "releases": "release",
    "push": "push",
    "issues": "issues",
    "pulls": "pull_request",
}
DEFAULT_EVENTS = frozenset({"releases"})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS subscriptions (
    guild_id        INTEGER NOT NULL,
    channel_id      INTEGER NOT NULL,
    repo            TEXT    NOT NULL COLLATE NOCASE,
    events          TEXT    NOT NULL,
    installation_id INTEGER,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (channel_id, repo)
);
CREATE INDEX IF NOT EXISTS idx_subscriptions_repo ON subscriptions (repo);
CREATE INDEX IF NOT EXISTS idx_subscriptions_guild ON subscriptions (guild_id);
"""


@dataclass(frozen=True, slots=True)
class Subscription:
    guild_id: int
    channel_id: int
    repo: str
    events: frozenset[str]
    installation_id: int | None

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> Subscription:
        return cls(
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            repo=row["repo"],
            events=frozenset(filter(None, row["events"].split(","))),
            installation_id=row["installation_id"],
        )


class Database:
    def __init__(self, path: Path | str) -> None:
        self._path = str(path)
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("database is not connected")
        return self._conn

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def subscribe(
        self,
        guild_id: int,
        channel_id: int,
        repo: str,
        events: frozenset[str],
        installation_id: int | None,
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO subscriptions (guild_id, channel_id, repo, events, installation_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (channel_id, repo) DO UPDATE SET
                events = excluded.events,
                installation_id = COALESCE(excluded.installation_id, installation_id)
            """,
            (guild_id, channel_id, repo, ",".join(sorted(events)), installation_id),
        )
        await self.conn.commit()

    async def unsubscribe(self, channel_id: int, repo: str) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM subscriptions WHERE channel_id = ? AND repo = ?",
            (channel_id, repo),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def guild_subscriptions(self, guild_id: int) -> list[Subscription]:
        async with self.conn.execute(
            "SELECT * FROM subscriptions WHERE guild_id = ? ORDER BY repo, channel_id",
            (guild_id,),
        ) as cur:
            return [Subscription.from_row(row) async for row in cur]

    async def subscribers(self, repo: str, event_type: str) -> list[Subscription]:
        """Channels subscribed to `repo` for the given event type (e.g. "releases")."""
        async with self.conn.execute("SELECT * FROM subscriptions WHERE repo = ?", (repo,)) as cur:
            subs = [Subscription.from_row(row) async for row in cur]
        return [s for s in subs if event_type in s.events]

    async def set_installation(self, repo: str, installation_id: int) -> None:
        await self.conn.execute(
            "UPDATE subscriptions SET installation_id = ? WHERE repo = ? "
            "AND (installation_id IS NULL OR installation_id != ?)",
            (installation_id, repo, installation_id),
        )
        await self.conn.commit()

    async def clear_installation(self, installation_id: int) -> None:
        await self.conn.execute(
            "UPDATE subscriptions SET installation_id = NULL WHERE installation_id = ?",
            (installation_id,),
        )
        await self.conn.commit()

    async def clear_repo_installation(self, repo: str) -> None:
        await self.conn.execute(
            "UPDATE subscriptions SET installation_id = NULL WHERE repo = ?", (repo,)
        )
        await self.conn.commit()

    async def remove_channel(self, channel_id: int) -> None:
        await self.conn.execute("DELETE FROM subscriptions WHERE channel_id = ?", (channel_id,))
        await self.conn.commit()

    async def remove_guild(self, guild_id: int) -> None:
        await self.conn.execute("DELETE FROM subscriptions WHERE guild_id = ?", (guild_id,))
        await self.conn.commit()
