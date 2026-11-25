"""Turns GitHub payloads into Discord embeds.

Everything here is pure (payload in, embed out) so it is easy to test against
recorded webhook payloads.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import discord
from discord.utils import escape_markdown, format_dt

GITHUB_ICON = "https://github.githubassets.com/favicons/favicon.png"

# Discord limits, https://discord.com/developers/docs/resources/message#embed-object-embed-limits
TITLE_LIMIT = 256
DESCRIPTION_LIMIT = 4096
FIELD_VALUE_LIMIT = 1024
MAX_FIELDS = 25
TOTAL_LIMIT = 6000

RELEASE_NOTES_LIMIT = 1500
BODY_PREVIEW_LIMIT = 400
MAX_COMMITS = 5
MAX_ASSETS = 5


class Color:
    # Roughly GitHub's own state colors.
    RELEASE = 0x2DA44E
    PRERELEASE = 0xBF8700
    PUSH = 0x0969DA
    OPEN = 0x1F883D
    CLOSED = 0xCF222E
    DONE = 0x8250DF  # merged PRs, completed issues
    MUTED = 0x6E7781  # drafts, "not planned"
    NEUTRAL = 0x24292F


_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_HTML_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>")


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def excerpt(text: str | None, limit: int, read_more_url: str | None = None) -> str:
    """Shorten markdown for an embed, cutting on a line break when possible."""
    text = _HTML_COMMENT.sub("", (text or "").replace("\r\n", "\n"))
    # GitHub renders inline HTML (<sub>, <details>, <img>...), Discord shows it as is
    text = _HTML_TAG.sub("", text).strip()
    if len(text) <= limit:
        return text

    link = f"\n\n[Read more]({read_more_url})" if read_more_url else ""
    room = limit - len(link) - 6  # leave space for "…" and a closing fence
    cut = text[:room]
    newline = cut.rfind("\n")
    if newline > room * 0.6:
        cut = cut[:newline]
    cut = cut.rstrip() + " …"
    if cut.count("```") % 2:
        cut += "\n```"
    return cut + link


def _time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _set_author(embed: discord.Embed, user: dict[str, Any] | None) -> None:
    if user:
        embed.set_author(
            name=user["login"], url=user.get("html_url"), icon_url=user.get("avatar_url")
        )


def _finish(embed: discord.Embed, repo: str) -> discord.Embed:
    embed.set_footer(text=f"{repo} • GitHub", icon_url=GITHUB_ICON)
    assert len(embed.fields) <= MAX_FIELDS
    overflow = len(embed) - TOTAL_LIMIT
    if overflow > 0 and embed.description:
        embed.description = truncate(embed.description, len(embed.description) - overflow)
    return embed


def _lines_field(lines: list[str], extra: int) -> str:
    """Join lines into a field value, dropping some if they would not fit."""
    value = ""
    for i, line in enumerate(lines):
        remaining = len(lines) - i + extra
        more = f"\n+{remaining} more"
        if len(value) + len(line) + 1 + len(more) > FIELD_VALUE_LIMIT:
            return value + more
        value += ("\n" if value else "") + line
    if extra:
        value += f"\n+{extra} more"
    return value


# -- releases ---------------------------------------------------------------


def release_embed(repo: str, release: dict[str, Any]) -> discord.Embed:
    tag = release["tag_name"]
    name = release.get("name") or tag
    prerelease = release.get("prerelease", False)

    embed = discord.Embed(
        title=truncate(f"{repo} {name}" if repo.lower() not in name.lower() else name, TITLE_LIMIT),
        url=release["html_url"],
        description=excerpt(release.get("body"), RELEASE_NOTES_LIMIT, release["html_url"])
        or "*No release notes.*",
        color=Color.PRERELEASE if prerelease else Color.RELEASE,
        timestamp=_time(release.get("published_at") or release.get("created_at")),
    )
    _set_author(embed, release.get("author"))
    embed.add_field(name="Tag", value=f"`{tag}`")
    if prerelease:
        embed.add_field(name="Type", value="Pre-release")

    assets = release.get("assets") or []
    if assets:
        lines = [
            f"[{escape_markdown(a['name'])}]({a['browser_download_url']}) ({_size(a['size'])})"
            for a in assets[:MAX_ASSETS]
        ]
        value = _lines_field(lines, len(assets) - MAX_ASSETS if len(assets) > MAX_ASSETS else 0)
        embed.add_field(name=f"Assets ({len(assets)})", value=value, inline=False)
    elif release.get("zipball_url"):
        source = f"[zip]({release['zipball_url']}) · [tar.gz]({release['tarball_url']})"
        embed.add_field(name="Source code", value=source, inline=False)

    return _finish(embed, repo)


# -- pushes -----------------------------------------------------------------


def push_branch(payload: dict[str, Any]) -> str | None:
    ref: str = payload.get("ref", "")
    return ref.removeprefix("refs/heads/") if ref.startswith("refs/heads/") else None


def should_announce_push(payload: dict[str, Any], all_branches: bool = False) -> bool:
    branch = push_branch(payload)
    if branch is None or payload.get("deleted") or not payload.get("commits"):
        return False
    return all_branches or branch == payload["repository"].get("default_branch")


def push_embed(payload: dict[str, Any]) -> discord.Embed | None:
    branch = push_branch(payload)
    commits: list[dict[str, Any]] = payload.get("commits") or []
    if branch is None or payload.get("deleted") or not commits:
        return None

    repo = payload["repository"]["full_name"]
    count = len(commits)
    lines = []
    for commit in commits[:MAX_COMMITS]:
        message = commit["message"].strip().splitlines()[0] if commit["message"].strip() else ""
        author = commit["author"].get("username") or commit["author"].get("name", "unknown")
        lines.append(
            f"[`{commit['id'][:7]}`]({commit['url']}) "
            f"{escape_markdown(truncate(message, 72))} - {escape_markdown(author)}"
        )
    if count > MAX_COMMITS:
        lines.append(f"+{count - MAX_COMMITS} more")
    if payload.get("forced"):
        lines.insert(0, "**Force-pushed**")

    head = payload.get("head_commit") or commits[-1]
    embed = discord.Embed(
        title=truncate(
            f"[{repo}:{branch}] {count} new commit{'s' if count != 1 else ''}", TITLE_LIMIT
        ),
        url=payload.get("compare"),
        description="\n".join(lines),
        color=Color.PUSH,
        timestamp=_time(head.get("timestamp")),
    )
    _set_author(embed, payload.get("sender"))
    return _finish(embed, repo)


# -- issues and pull requests -----------------------------------------------


def issue_embed(payload: dict[str, Any]) -> discord.Embed | None:
    action = payload.get("action")
    issue = payload["issue"]
    if action not in ("opened", "closed", "reopened") or "pull_request" in issue:
        return None

    repo = payload["repository"]["full_name"]
    color = Color.OPEN
    verb = action
    if action == "closed":
        if issue.get("state_reason") == "not_planned":
            verb, color = "closed as not planned", Color.MUTED
        else:
            color = Color.DONE

    embed = discord.Embed(
        title=truncate(f"[{repo}] Issue {verb}: #{issue['number']} {issue['title']}", TITLE_LIMIT),
        url=issue["html_url"],
        color=color,
        timestamp=_time(issue.get("closed_at") if action == "closed" else issue.get("updated_at")),
    )
    if action == "opened":
        embed.description = excerpt(issue.get("body"), BODY_PREVIEW_LIMIT, issue["html_url"])
        labels = [f"`{label['name']}`" for label in issue.get("labels") or []]
        if labels:
            embed.add_field(name="Labels", value=truncate(" ".join(labels), FIELD_VALUE_LIMIT))
    _set_author(embed, payload.get("sender"))
    return _finish(embed, repo)


def pull_request_embed(payload: dict[str, Any]) -> discord.Embed | None:
    action = payload.get("action")
    pr = payload["pull_request"]
    if action not in ("opened", "closed", "reopened"):
        return None

    repo = payload["repository"]["full_name"]
    if action == "closed" and pr.get("merged"):
        verb, color = "merged", Color.DONE
    elif action == "closed":
        verb, color = "closed", Color.CLOSED
    elif pr.get("draft"):
        verb, color = f"{action} as draft", Color.MUTED
    else:
        verb, color = action, Color.OPEN

    embed = discord.Embed(
        title=truncate(f"[{repo}] Pull request {verb}: #{pr['number']} {pr['title']}", TITLE_LIMIT),
        url=pr["html_url"],
        color=color,
        timestamp=_time(pr.get("merged_at") or pr.get("closed_at") or pr.get("updated_at")),
    )
    if action == "opened":
        embed.description = excerpt(pr.get("body"), BODY_PREVIEW_LIMIT, pr["html_url"])

    head, base = pr["head"]["ref"], pr["base"]["ref"]
    embed.add_field(name="Branches", value=f"`{head}` → `{base}`")
    if "additions" in pr:
        embed.add_field(
            name="Changes",
            value=f"+{pr['additions']} / -{pr['deletions']} in {pr['changed_files']} files",
        )
    _set_author(embed, payload.get("sender"))
    return _finish(embed, repo)


def build_embed(event: str, payload: dict[str, Any]) -> discord.Embed | None:
    if event == "release":
        if payload.get("action") != "published":
            return None
        return release_embed(payload["repository"]["full_name"], payload["release"])
    if event == "push":
        return push_embed(payload)
    if event == "issues":
        return issue_embed(payload)
    if event == "pull_request":
        return pull_request_embed(payload)
    return None


# -- slash command replies --------------------------------------------------


def repo_embed(repo: dict[str, Any], latest_release: dict[str, Any] | None) -> discord.Embed:
    description = escape_markdown(repo.get("description") or "") or "*No description.*"
    notes = []
    if repo.get("archived"):
        notes.append("Archived")
    if repo.get("fork") and repo.get("parent"):
        parent = repo["parent"]
        notes.append(f"Fork of [{parent['full_name']}]({parent['html_url']})")
    if notes:
        description = " · ".join(notes) + "\n\n" + description

    embed = discord.Embed(
        title=repo["full_name"],
        url=repo["html_url"],
        description=truncate(description, DESCRIPTION_LIMIT),
        color=Color.NEUTRAL,
    )
    embed.set_thumbnail(url=repo["owner"]["avatar_url"])
    embed.add_field(name="Stars", value=f"{repo['stargazers_count']:,}")
    embed.add_field(name="Forks", value=f"{repo['forks_count']:,}")
    embed.add_field(name="Language", value=repo.get("language") or "n/a")
    embed.add_field(name="Open issues & PRs", value=f"{repo['open_issues_count']:,}")

    if latest_release:
        tag = latest_release["tag_name"]
        embed.add_field(name="Latest release", value=f"[{tag}]({latest_release['html_url']})")
    else:
        embed.add_field(name="Latest release", value="none")

    pushed = _time(repo.get("pushed_at"))
    embed.add_field(name="Last push", value=format_dt(pushed, "R") if pushed else "never")

    license_ = (repo.get("license") or {}).get("spdx_id")
    if license_ and license_ != "NOASSERTION":
        embed.add_field(name="License", value=license_)
    embed.add_field(name="Default branch", value=f"`{repo['default_branch']}`")

    topics = repo.get("topics") or []
    if topics:
        embed.add_field(
            name="Topics",
            value=truncate(" ".join(f"`{t}`" for t in topics), FIELD_VALUE_LIMIT),
            inline=False,
        )
    return _finish(embed, repo["full_name"])
