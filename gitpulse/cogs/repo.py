from __future__ import annotations

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from ..bot import GitPulse
from ..embeds import release_embed, repo_embed
from ..utils import UserError, parse_repo


class Repo(commands.Cog):
    def __init__(self, bot: GitPulse) -> None:
        self.bot = bot

    @app_commands.command(description="Show information about a GitHub repository")
    @app_commands.describe(repo="Repository, as owner/name")
    async def repo(self, interaction: discord.Interaction, repo: str) -> None:
        name = parse_repo(repo)
        await interaction.response.defer(thinking=True)
        data, latest = await asyncio.gather(
            self.bot.github.get_repo(name),
            self.bot.github.get_latest_release(name),
        )
        await interaction.followup.send(embed=repo_embed(data, latest))

    @app_commands.command(description="Show the latest release of a GitHub repository")
    @app_commands.describe(repo="Repository, as owner/name")
    async def release(self, interaction: discord.Interaction, repo: str) -> None:
        name = parse_repo(repo)
        await interaction.response.defer(thinking=True)
        # fetch the repo too, so a typo gives "not found" instead of "no releases"
        data, latest = await asyncio.gather(
            self.bot.github.get_repo(name),
            self.bot.github.get_latest_release(name),
        )
        if latest is None:
            raise UserError(f"`{data['full_name']}` has no published release yet.")
        await interaction.followup.send(embed=release_embed(data["full_name"], latest))


async def setup(bot: GitPulse) -> None:
    await bot.add_cog(Repo(bot))
