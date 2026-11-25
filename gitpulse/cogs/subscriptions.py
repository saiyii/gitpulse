from __future__ import annotations

from collections import defaultdict

import discord
from discord import app_commands
from discord.ext import commands

from ..bot import GitPulse
from ..utils import UserError, parse_events, parse_repo


class Subscriptions(commands.Cog):
    def __init__(self, bot: GitPulse) -> None:
        self.bot = bot

    @app_commands.command(description="Post activity from a GitHub repository in this channel")
    @app_commands.describe(
        repo="Repository, as owner/name",
        events="releases, push, issues, pulls or all. Comma separated, default: releases",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def subscribe(
        self, interaction: discord.Interaction, repo: str, events: str | None = None
    ) -> None:
        assert interaction.guild is not None and interaction.channel is not None
        name = parse_repo(repo)
        wanted = parse_events(events)

        perms = interaction.channel.permissions_for(interaction.guild.me)  # type: ignore[union-attr]
        if not (perms.send_messages and perms.embed_links):
            raise UserError("I need **Send Messages** and **Embed Links** in this channel first.")

        await interaction.response.defer(thinking=True)
        data = await self.bot.github.get_repo(name)
        full_name: str = data["full_name"]
        installation_id = await self.bot.github.repo_installation(full_name)

        await self.bot.db.subscribe(
            interaction.guild.id, interaction.channel.id, full_name, wanted, installation_id
        )

        message = (
            f"Done. This channel will get **{', '.join(sorted(wanted))}** "
            f"from [{full_name}]({data['html_url']})."
        )
        if installation_id is None:
            message += (
                "\n\n:warning: The GitPulse GitHub App isn't installed on this repository, "
                "so GitHub won't send anything yet."
            )
            if self.bot.install_url:
                message += f" [Install it here]({self.bot.install_url}) (needs admin access)."
        await interaction.followup.send(message, suppress_embeds=True)

    @app_commands.command(description="Stop posting a repository's activity in this channel")
    @app_commands.describe(repo="Repository, as owner/name")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def unsubscribe(self, interaction: discord.Interaction, repo: str) -> None:
        assert interaction.channel is not None
        name = parse_repo(repo)
        removed = await self.bot.db.unsubscribe(interaction.channel.id, name)
        if not removed:
            raise UserError(f"This channel isn't subscribed to `{name}`.")
        await interaction.response.send_message(f"Unsubscribed from `{name}`.")

    @unsubscribe.autocomplete("repo")
    async def _unsubscribe_repo(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        if interaction.guild is None or interaction.channel is None:
            return []
        subs = await self.bot.db.guild_subscriptions(interaction.guild.id)
        repos = sorted(
            {s.repo for s in subs if s.channel_id == interaction.channel.id},
            key=str.lower,
        )
        current = current.lower()
        return [app_commands.Choice(name=r, value=r) for r in repos if current in r.lower()][:25]

    @app_commands.command(description="List the repositories this server follows")
    @app_commands.guild_only()
    async def subscriptions(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        subs = await self.bot.db.guild_subscriptions(interaction.guild.id)
        if not subs:
            await interaction.response.send_message(
                "No subscriptions yet. Use `/subscribe owner/name` in a channel to add one.",
                ephemeral=True,
            )
            return

        by_channel: dict[int, list[str]] = defaultdict(list)
        for sub in subs:
            flag = "" if sub.installation_id else " (app not installed)"
            by_channel[sub.channel_id].append(
                f"`{sub.repo}`: {', '.join(sorted(sub.events))}{flag}"
            )

        embed = discord.Embed(title="Subscriptions", color=0x24292F)
        for i, (channel_id, lines) in enumerate(by_channel.items()):
            if i == 24 and len(by_channel) > 25:
                embed.add_field(name="…", value=f"+{len(by_channel) - 24} more channels")
                break
            value = "\n".join(lines)
            if len(value) > 1024:
                value = value[:1000].rsplit("\n", 1)[0] + "\n…"
            embed.add_field(name="​", value=f"<#{channel_id}>\n{value}", inline=False)
        embed.set_footer(text=f"{len(subs)} subscription{'s' if len(subs) != 1 else ''}")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: GitPulse) -> None:
    await bot.add_cog(Subscriptions(bot))
