import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from gitpulse import REPO_URL
from gitpulse.website import add_site_routes


@pytest.fixture
async def client():
    links = {"install": "https://github.com/apps/gitpulse/installations/new", "invite": None}
    app = web.Application()
    add_site_routes(app, install_url=lambda: links["install"], invite_url=lambda: links["invite"])
    async with TestClient(TestServer(app)) as test_client:
        yield test_client


@pytest.mark.parametrize(
    "path, content_type, needle",
    [
        ("/", "text/html", "Install the GitHub App"),
        ("/privacy", "text/html", "Privacy policy"),
        ("/terms", "text/html", "Terms of service"),
        ("/style.css", "text/css", "--accent"),
        ("/logo.svg", "image/svg+xml", "<svg"),
    ],
)
async def test_pages(client, path, content_type, needle):
    resp = await client.get(path)
    assert resp.status == 200
    assert resp.content_type == content_type
    assert needle in await resp.text()


async def test_install_redirect(client):
    resp = await client.get("/install", allow_redirects=False)
    assert resp.status == 302
    assert resp.headers["Location"] == "https://github.com/apps/gitpulse/installations/new"


async def test_unknown_link_falls_back_to_readme(client):
    resp = await client.get("/invite", allow_redirects=False)
    assert resp.status == 302
    assert resp.headers["Location"] == f"{REPO_URL}#self-hosting"


async def test_unknown_page(client):
    resp = await client.get("/nope")
    assert resp.status == 404
