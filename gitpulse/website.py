"""The small public website served next to the webhook endpoint.

`/` is the landing page, `/privacy` and `/terms` are linked from the GitHub
Marketplace listing, and `/install` / `/invite` redirect to the GitHub App and
Discord invite links of the running instance.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from aiohttp import web

from . import REPO_URL

WEB_DIR = Path(__file__).resolve().parent / "web"

_PAGES = {
    "/": "index.html",
    "/privacy": "privacy.html",
    "/terms": "terms.html",
    "/style.css": "style.css",
    "/logo.svg": "logo.svg",
}
_HEADERS = {
    "Cache-Control": "public, max-age=300",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}

LinkGetter = Callable[[], str | None]


def _file_handler(name: str):
    path = WEB_DIR / name

    async def handler(request: web.Request) -> web.FileResponse:
        return web.FileResponse(path, headers=_HEADERS)

    return handler


def _redirect_handler(get_url: LinkGetter):
    async def handler(request: web.Request) -> web.Response:
        # fall back to the README (self-hosting instructions) if the link isn't known yet
        raise web.HTTPFound(get_url() or f"{REPO_URL}#self-hosting")

    return handler


def add_site_routes(
    app: web.Application, *, install_url: LinkGetter, invite_url: LinkGetter
) -> None:
    for route, name in _PAGES.items():
        app.router.add_get(route, _file_handler(name))
    app.router.add_get("/install", _redirect_handler(install_url))
    app.router.add_get("/invite", _redirect_handler(invite_url))
