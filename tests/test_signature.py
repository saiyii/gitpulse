import asyncio
import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from gitpulse.github.webhooks import DeliveryLog, WebhookServer, sign, verify_signature

SECRET = "It's a Secret to Everybody"
BODY = b"Hello, World!"


def test_known_signature():
    # Example from GitHub's "Validating webhook deliveries" docs.
    expected = "sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17"
    assert sign(SECRET, BODY) == expected
    assert verify_signature(SECRET, BODY, expected)


def test_wrong_secret():
    assert not verify_signature("other secret", BODY, sign(SECRET, BODY))


def test_tampered_body():
    assert not verify_signature(SECRET, BODY + b"!", sign(SECRET, BODY))


@pytest.mark.parametrize("header", [None, "", "sha1=abc", "757107ea0eb2509fc2"])
def test_missing_or_malformed_header(header):
    assert not verify_signature(SECRET, BODY, header)


def test_delivery_log():
    deliveries = DeliveryLog(size=2)
    assert not deliveries.seen("a")
    assert deliveries.seen("a")
    deliveries.seen("b")
    deliveries.seen("c")  # pushes "a" out
    assert not deliveries.seen("a")


@pytest.fixture
async def server():
    received: list[tuple[str, dict]] = []

    async def handler(event: str, payload: dict) -> None:
        received.append((event, payload))

    webhook = WebhookServer(SECRET, handler, "127.0.0.1", 0)
    async with TestClient(TestServer(webhook.app)) as client:
        yield client, received


def headers(body: bytes, event: str = "push", delivery: str = "1") -> dict[str, str]:
    return {
        "X-Hub-Signature-256": sign(SECRET, body),
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery,
        "Content-Type": "application/json",
    }


async def test_health(server):
    client, _ = server
    resp = await client.get("/health")
    assert resp.status == 200
    assert await resp.text() == "OK"


async def test_rejects_unsigned(server):
    client, received = server
    resp = await client.post("/webhook", data=b"{}", headers={"X-GitHub-Event": "push"})
    assert resp.status == 401
    assert received == []


async def test_rejects_bad_signature(server):
    client, received = server
    body = b'{"ref": "refs/heads/main"}'
    h = headers(body)
    h["X-Hub-Signature-256"] = sign("wrong", body)
    resp = await client.post("/webhook", data=body, headers=h)
    assert resp.status == 401
    assert received == []


async def test_accepts_signed_event_once(server):
    client, received = server
    body = json.dumps({"ref": "refs/heads/main"}).encode()

    first = await client.post("/webhook", data=body, headers=headers(body, delivery="abc"))
    again = await client.post("/webhook", data=body, headers=headers(body, delivery="abc"))
    await asyncio.sleep(0)  # let the dispatch task run

    assert first.status == 202
    assert again.status == 200
    assert received == [("push", {"ref": "refs/heads/main"})]


async def test_ping(server):
    client, received = server
    body = b'{"zen": "Keep it logically awesome."}'
    resp = await client.post("/webhook", data=body, headers=headers(body, event="ping"))
    assert resp.status == 200
    assert received == []
