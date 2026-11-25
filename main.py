"""GitPulse entry point. Starts the Discord bot and the webhook server in one process."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

from gitpulse.bot import GitPulse
from gitpulse.config import Config, ConfigError


def setup_logging() -> None:
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # discord.py is very chatty at DEBUG level
    logging.getLogger("discord").setLevel(max(level, logging.INFO))


async def run(config: Config) -> None:
    async with GitPulse(config) as bot:
        await bot.start(config.discord_token)


def main() -> None:
    load_dotenv()
    setup_logging()
    try:
        config = Config.from_env()
    except ConfigError as exc:
        logging.getLogger("gitpulse").critical("config error: %s", exc)
        sys.exit(1)

    try:
        asyncio.run(run(config))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
