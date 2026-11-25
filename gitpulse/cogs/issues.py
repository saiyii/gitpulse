from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from .. import REPO_URL
from ..bot import GitPulse
from ..embeds import Color
from ..utils import UserError, parse_repo


class Issues(commands.Cog):
    issue = app_commands.Group(name="issue", description="Work with GitHub issues", guild_only=True)

    def __init__(self, bot: GitPulse) -> None:
        self.bot = bot

    def _check_role(self, interaction: discord.Interaction) -> None:
        member = interaction.user
        if not isinstance(member, discord.Member):
            raise app_commands.NoPrivateMessage()
        if member.guild_permissions.administrator:
            return
        role = self.bot.config.admin_role_name
        if not any(r.name == role for r in member.roles):
            raise UserError(f"You need the **{role}** role to open issues from Discord.")

    @issue.command(name="create", description="Open an issue on a GitHub repository")
    @app_commands.describe(
        repo="Repository, as owner/name (the GitPulse app must be installed on it)",
        title="Issue title",
        body="Issue description, markdown works",
    )
    async def create(
        self,
        interaction: discord.Interaction,
        repo: str,
        title: app_commands.Range[str, 1, 256],
        body: app_commands.Range[str, 1, 4000] | None = None,
    ) -> None:
        self._check_role(interaction)
        name = parse_repo(repo)
        await interaction.response.defer(thinking=True)

        signature = (
            f"<sub>Opened from Discord by {interaction.user.name} with [GitPulse]({REPO_URL})</sub>"
        )
        text = f"{body}\n\n{signature}" if body else signature
        issue = await self.bot.github.create_issue(name, title, text)

        embed = discord.Embed(
            title=f"#{issue['number']} {issue['title']}"[:256],
            url=issue["html_url"],
            description=f"Issue opened on [{name}](https://github.com/{name}).",
            color=Color.OPEN,
        )
        await interaction.followup.send(embed=embed)


async def setup(bot: GitPulse) -> None:
    await bot.add_cog(Issues(bot))
