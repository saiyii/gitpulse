from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import web

log = logging.getLogger(__name__)

EventHandler = Callable[[str, dict[str, Any]], Awaitable[None]]

# GitHub caps payloads at 25 MB, aiohttp's default limit is 1 MB.
MAX_BODY_SIZE = 25 * 1024 * 1024


def sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    return hmac.compare_digest(sign(secret, body), header)


class DeliveryLog:
    """Remembers recent delivery ids so redelivered events are only handled once."""

    def __init__(self, size: int = 2000) -> None:
        self._size = size
        self._seen: OrderedDict[str, None] = OrderedDict()

    def seen(self, delivery_id: str) -> bool:
        if delivery_id in self._seen:
            return True
        self._seen[delivery_id] = None
        if len(self._seen) > self._size:
            self._seen.popitem(last=False)
        return False


class WebhookServer:
    def __init__(self, secret: str, handler: EventHandler, host: str, port: int) -> None:
        self._secret = secret
        self._handler = handler
        self._host = host
        self._port = port
        self._deliveries = DeliveryLog()
        self._tasks: set[asyncio.Task[None]] = set()
        self._runner: web.AppRunner | None = None
        self.app = self._build_app()

    def _build_app(self) -> web.Application:
        app = web.Application(client_max_size=MAX_BODY_SIZE)
        app.router.add_post("/webhook", self._on_webhook)
        app.router.add_get("/health", self._on_health)
        return app

    async def start(self) -> None:
        self._runner = web.AppRunner(self.app, access_log=None)
        await self._runner.setup()
        await web.TCPSite(self._runner, self._host, self._port).start()
        log.info("webhook server listening on %s:%s", self._host, self._port)

    async def stop(self) -> None:
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=5)
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def _on_health(self, request: web.Request) -> web.Response:
        return web.Response(text="OK")

    async def _on_webhook(self, request: web.Request) -> web.Response:
        body = await request.read()
        if not verify_signature(self._secret, body, request.headers.get("X-Hub-Signature-256")):
            log.warning("rejected webhook with bad signature from %s", request.remote)
            return web.Response(status=401, text="invalid signature")

        event = request.headers.get("X-GitHub-Event")
        delivery = request.headers.get("X-GitHub-Delivery", "")
        if not event:
            return web.Response(status=400, text="missing X-GitHub-Event")

        if delivery and self._deliveries.seen(delivery):
            log.info("ignoring duplicate delivery %s", delivery)
            return web.Response(text="duplicate")

        try:
            payload = json.loads(body)
        except ValueError:
            return web.Response(status=400, text="invalid JSON")

        if event == "ping":
            log.info("ping from GitHub: %s", payload.get("zen"))
            return web.Response(text="pong")

        # GitHub gives up after 10 seconds, so answer now and post to Discord afterwards.
        task = asyncio.create_task(self._dispatch(event, delivery, payload))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return web.Response(status=202, text="accepted")

    async def _dispatch(self, event: str, delivery: str, payload: dict[str, Any]) -> None:
        try:
            await self._handler(event, payload)
        except Exception:
            log.exception("failed to handle %s event (delivery %s)", event, delivery)
