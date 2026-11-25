from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from .. import REPO_URL, __version__
from ..bot import GitPulse
from ..embeds import GITHUB_ICON, Color

COMMANDS = [
    ("/repo `owner/name`", "Stars, forks, language, latest release and last push."),
    ("/release `owner/name`", "Latest release with its notes and assets."),
    ("/subscribe `owner/name` `[events]`", "Post a repo's activity in this channel."),
    ("/unsubscribe `owner/name`", "Stop posting a repo in this channel."),
    ("/subscriptions", "Everything this server follows."),
    ("/issue create `owner/name` `title` `[body]`", "Open an issue on GitHub."),
    ("/about", "Links, support and version."),
]


class Info(commands.Cog):
    def __init__(self, bot: GitPulse) -> None:
        self.bot = bot

    @app_commands.command(name="help", description="List GitPulse commands")
    async def help_(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="GitPulse commands",
            description="\n".join(f"**{usage}**\n{text}" for usage, text in COMMANDS),
            color=Color.NEUTRAL,
        )
        embed.add_field(
            name="Events",
            value=(
                "`releases` (default), `push` (default branch only), `issues`, `pulls`, "
                "or `all`. Example: `/subscribe saiyii/gitpulse releases,push`"
            ),
            inline=False,
        )
        embed.set_footer(
            text="/subscribe, /unsubscribe need Manage Server. /issue create needs the "
            f"{self.bot.config.admin_role_name} role."
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(description="About GitPulse")
    async def about(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="GitPulse",
            url=REPO_URL,
            description=(
                "A Discord bot and GitHub App that posts releases, pushes, issues and pull "
                "requests from your repositories, and lets you look up repos or open issues "
                "from Discord.\n\n"
                "Built with the GitHub REST API and GitHub Apps: events come in through "
                "signed webhooks, and actions use short-lived installation tokens."
            ),
            color=Color.NEUTRAL,
        )
        links = [f"[Source code]({REPO_URL})"]
        if self.bot.install_url:
            links.append(f"[Install the GitHub App]({self.bot.install_url})")
        if self.bot.invite_url:
            links.append(f"[Add to Discord]({self.bot.invite_url})")
        embed.add_field(name="Links", value=" · ".join(links), inline=False)
        embed.add_field(name="Support", value=self.bot.config.support_email)
        embed.add_field(name="Version", value=__version__)
        embed.add_field(name="Servers", value=str(len(self.bot.guilds)))
        embed.set_footer(text="Works with GitHub", icon_url=GITHUB_ICON)
        await interaction.response.send_message(embed=embed)


async def setup(bot: GitPulse) -> None:
    await bot.add_cog(Info(bot))
