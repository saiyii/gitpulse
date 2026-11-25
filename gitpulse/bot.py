from __future__ import annotations

import asyncio
import logging
import pkgutil
from datetime import UTC, datetime
from typing import Any

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from . import cogs
from .config import Config
from .db import EVENT_TYPES, Database, Subscription
from .embeds import build_embed, should_announce_push
from .github.auth import GitHubAppAuth
from .github.client import GitHubClient, GitHubError, NotFound, NotInstalled, RateLimited
from .github.webhooks import WebhookServer
from .utils import UserError
from .website import add_site_routes

log = logging.getLogger(__name__)

# webhook event name -> subscription event type
_EVENT_TO_TYPE = {event: name for name, event in EVENT_TYPES.items()}

# Bot permissions: View Channels, Send Messages, Embed Links.
INVITE_PERMISSIONS = discord.Permissions(view_channel=True, send_messages=True, embed_links=True)


def log_marketplace_event(payload: dict[str, Any]) -> None:
    """GitHub Marketplace plan changes. GitPulse only has a free plan, so just record them."""
    purchase = payload.get("marketplace_purchase") or {}
    account = purchase.get("account") or {}
    plan = purchase.get("plan") or {}
    log.info(
        "marketplace: %s by %s %s, plan %r",
        payload.get("action", "?"),
        (account.get("type") or "account").lower(),
        account.get("login", "?"),
        plan.get("name"),
    )


class GitPulse(commands.Bot):
    session: aiohttp.ClientSession
    github: GitHubClient

    def __init__(self, config: Config) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
            allowed_mentions=discord.AllowedMentions.none(),
            activity=discord.Activity(type=discord.ActivityType.watching, name="GitHub repos"),
        )
        self.config = config
        self.db = Database(config.database_path)
        self.webhooks = WebhookServer(
            config.github_webhook_secret,
            self.handle_github_event,
            config.webhook_host,
            config.webhook_port,
        )
        add_site_routes(
            self.webhooks.app,
            install_url=lambda: self.install_url,
            invite_url=lambda: self.invite_url,
        )
        self.github_app: dict[str, Any] | None = None

    @property
    def install_url(self) -> str | None:
        if self.github_app is None:
            return None
        return f"{self.github_app['html_url']}/installations/new"

    @property
    def invite_url(self) -> str | None:
        if self.application_id is None:
            return None
        return discord.utils.oauth_url(
            self.application_id,
            permissions=INVITE_PERMISSIONS,
            scopes=("bot", "applications.commands"),
        )

    async def setup_hook(self) -> None:
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        auth = GitHubAppAuth(
            self.config.github_app_id, self.config.github_private_key, self.session
        )
        self.github = GitHubClient(self.session, auth, self.config.github_token)
        await self.db.connect()

        try:
            self.github_app = await self.github.get_app()
            log.info("authenticated as GitHub App %r", self.github_app["slug"])
        except (TimeoutError, GitHubError, aiohttp.ClientError) as exc:
            log.error("GitHub App authentication failed (%s), check GITHUB_APP_ID and the key", exc)

        for module in pkgutil.iter_modules(cogs.__path__, f"{cogs.__name__}."):
            await self.load_extension(module.name)
        self.tree.on_error = self.on_app_command_error

        await self.sync_commands()
        await self.webhooks.start()

    async def sync_commands(self) -> None:
        if self.config.discord_guild_id:
            guild = discord.Object(self.config.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("synced %d commands to guild %s", len(synced), guild.id)
        else:
            synced = await self.tree.sync()
            log.info("synced %d global commands (can take a while to show up)", len(synced))

    async def on_ready(self) -> None:
        assert self.user is not None
        log.info("logged in as %s, in %d servers", self.user, len(self.guilds))

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        await self.db.remove_guild(guild.id)

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        await self.db.remove_channel(channel.id)

    async def close(self) -> None:
        await self.webhooks.stop()
        await super().close()
        await self.db.close()
        if hasattr(self, "session"):
            await self.session.close()

    # -- GitHub events --------------------------------------------------------

    async def handle_github_event(self, event: str, payload: dict[str, Any]) -> None:
        if event == "marketplace_purchase":
            log_marketplace_event(payload)
            return
        if event in ("installation", "installation_repositories"):
            await self._handle_installation_change(event, payload)
            return

        event_type = _EVENT_TO_TYPE.get(event)
        repo = (payload.get("repository") or {}).get("full_name")
        if event_type is None or repo is None:
            return

        installation_id = (payload.get("installation") or {}).get("id")
        if installation_id:
            self.github.remember_installation(repo, installation_id)
            await self.db.set_installation(repo, installation_id)

        if event == "push" and not should_announce_push(payload, self.config.push_all_branches):
            return
        embed = build_embed(event, payload)
        if embed is None:
            return

        subscriptions = await self.db.subscribers(repo, event_type)
        log.info("%s on %s -> %d channel(s)", event, repo, len(subscriptions))
        if subscriptions:
            await self.wait_until_ready()
            await asyncio.gather(*(self._post(sub, embed) for sub in subscriptions))

    async def _handle_installation_change(self, event: str, payload: dict[str, Any]) -> None:
        installation_id: int = payload["installation"]["id"]
        action = payload.get("action")
        account = (payload["installation"].get("account") or {}).get("login", "?")

        if event == "installation" and action == "deleted":
            log.info("app uninstalled from %s (installation %s)", account, installation_id)
            self.github.forget_installation(installation_id)
            await self.db.clear_installation(installation_id)
        elif event == "installation" and action == "created":
            log.info("app installed on %s (installation %s)", account, installation_id)
        elif event == "installation_repositories" and action == "removed":
            repos = [r["full_name"] for r in payload.get("repositories_removed") or []]
            log.info("installation %s lost access to %s", installation_id, ", ".join(repos))
            for repo in repos:
                self.github.forget_repo(repo)
                await self.db.clear_repo_installation(repo)

    async def _post(self, sub: Subscription, embed: discord.Embed) -> None:
        channel = self.get_channel(sub.channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(sub.channel_id)
            except discord.NotFound:
                log.info("channel %s no longer exists, dropping its subscriptions", sub.channel_id)
                await self.db.remove_channel(sub.channel_id)
                return
            except discord.HTTPException as exc:
                log.warning("cannot fetch channel %s: %s", sub.channel_id, exc)
                return

        if not isinstance(channel, discord.abc.Messageable):
            return
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            log.warning(
                "no permission to post in channel %s (guild %s)", sub.channel_id, sub.guild_id
            )
        except discord.HTTPException:
            log.exception("failed to post %s update in channel %s", sub.repo, sub.channel_id)

    # -- errors ---------------------------------------------------------------

    def describe_error(self, error: Exception) -> str | None:
        if isinstance(error, UserError):
            return str(error)
        if isinstance(error, app_commands.NoPrivateMessage):
            return "This command only works in a server."
        if isinstance(error, (app_commands.MissingPermissions, app_commands.CheckFailure)):
            return "You don't have permission to use this command."
        if isinstance(error, NotInstalled):
            install = (
                f" [Install the GitHub App]({self.install_url}) on it first."
                if self.install_url
                else ""
            )
            return f"GitPulse isn't installed on `{error.repo}`.{install}"
        if isinstance(error, RateLimited):
            reset = datetime.fromtimestamp(error.reset_at, tz=UTC)
            return (
                f"GitHub's rate limit is reached. Try again {discord.utils.format_dt(reset, 'R')}."
            )
        if isinstance(error, NotFound):
            return (
                "Repository not found. If it's private, the GitPulse GitHub App needs to be "
                "installed on it."
            )
        if isinstance(error, GitHubError):
            return f"GitHub said no: {error.message}"
        if isinstance(error, (aiohttp.ClientError, asyncio.TimeoutError)):
            return "Couldn't reach GitHub. Try again in a minute."
        return None

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        original = error.original if isinstance(error, app_commands.CommandInvokeError) else error
        message = self.describe_error(original)
        if message is None:
            command = interaction.command.qualified_name if interaction.command else "?"
            log.error("error in /%s", command, exc_info=original)
            message = (
                "Something broke on my side. If it keeps happening, "
                f"email {self.config.support_email}."
            )

        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True, suppress_embeds=True)
            else:
                await interaction.response.send_message(
                    message, ephemeral=True, suppress_embeds=True
                )
        except discord.HTTPException:
            log.warning("could not send error message for interaction %s", interaction.id)
