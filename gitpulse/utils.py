from __future__ import annotations

import re

from discord import app_commands

from .db import DEFAULT_EVENTS, EVENT_TYPES

# GitHub logins: alphanumerics and single hyphens, 39 chars max.
_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$")

_EVENT_ALIASES = {
    "release": "releases",
    "pushes": "push",
    "commits": "push",
    "issue": "issues",
    "pull": "pulls",
    "pr": "pulls",
    "prs": "pulls",
    "pull_request": "pulls",
    "pull_requests": "pulls",
}


class UserError(app_commands.AppCommandError):
    """Error whose message is shown to the user as is."""


def parse_repo(value: str) -> str:
    """Accept `owner/name` or a github.com URL and return `owner/name`."""
    value = value.strip()
    value = re.sub(r"^(https?://)?(www\.)?github\.com/", "", value, flags=re.IGNORECASE)
    parts = [p for p in value.split("/") if p]
    if len(parts) >= 2:
        value = f"{parts[0]}/{parts[1].removesuffix('.git')}"

    if not _REPO_RE.match(value) or value.endswith("/.") or value.endswith("/.."):
        shown = value.replace("`", "")[:100]
        raise UserError(
            f"`{shown}` doesn't look like a repository. Use `owner/name`, like `saiyii/gitpulse`."
        )
    return value


def parse_events(raw: str | None) -> frozenset[str]:
    if not raw or not raw.strip():
        return DEFAULT_EVENTS

    events: set[str] = set()
    for item in re.split(r"[,\s]+", raw.strip().lower()):
        if not item:
            continue
        if item == "all":
            return frozenset(EVENT_TYPES)
        item = _EVENT_ALIASES.get(item, item)
        if item not in EVENT_TYPES:
            valid = ", ".join(f"`{name}`" for name in EVENT_TYPES)
            raise UserError(f"Unknown event `{item[:30]}`. Pick from {valid} or `all`.")
        events.add(item)
    return frozenset(events)
