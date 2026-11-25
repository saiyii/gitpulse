import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from gitpulse.github.client import GitHubClient, NotFound, NotInstalled, RateLimited


class FakeAuth:
    def app_jwt(self) -> str:
        return "app-jwt"

    async def installation_token(self, installation_id: int) -> str:
        return f"inst-{installation_id}"


def rate_headers(remaining: int) -> dict[str, str]:
    return {
        "X-RateLimit-Limit": "5000",
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": "1700000000",
    }


@pytest.fixture
async def github():
    seen: list[tuple[str, str | None]] = []

    async def installation(request: web.Request):
        if request.match_info["name"] == "installed":
            return web.json_response({"id": 7})
        return web.json_response({"message": "Not Found"}, status=404)

    async def installations(request: web.Request):
        return web.json_response([{"id": 1}])

    async def repo(request: web.Request):
        seen.append((request.path, request.headers.get("Authorization")))
        name = request.match_info["name"]
        if name == "missing":
            return web.json_response({"message": "Not Found"}, status=404)
        if name == "limited":
            return web.json_response(
                {"message": "API rate limit exceeded"}, status=403, headers=rate_headers(0)
            )
        return web.json_response({"full_name": f"o/{name}"}, headers=rate_headers(4999))

    app = web.Application()
    app.router.add_get("/repos/o/{name}/installation", installation)
    app.router.add_get("/app/installations", installations)
    app.router.add_get("/repos/o/{name}", repo)

    server = TestServer(app)
    await server.start_server()
    async with aiohttp.ClientSession() as session:
        base_url = str(server.make_url(""))
        client = GitHubClient(session, FakeAuth(), base_url=base_url)  # type: ignore[arg-type]
        yield client, seen
    await server.close()


async def test_uses_repo_installation_token(github):
    client, seen = github
    assert (await client.get_repo("o/installed"))["full_name"] == "o/installed"
    assert seen[-1] == ("/repos/o/installed", "Bearer inst-7")
    assert client.rate_limit and client.rate_limit.remaining == 4999


async def test_falls_back_to_any_installation(github):
    client, seen = github
    await client.get_repo("o/public")
    assert seen[-1] == ("/repos/o/public", "Bearer inst-1")


async def test_not_found(github):
    client, _ = github
    with pytest.raises(NotFound):
        await client.get_repo("o/missing")


async def test_rate_limited(github):
    client, _ = github
    with pytest.raises(RateLimited) as exc:
        await client.get_repo("o/limited")
    assert exc.value.reset_at == 1700000000


async def test_create_issue_needs_installation(github):
    client, _ = github
    with pytest.raises(NotInstalled):
        await client.create_issue("o/public", "title", None)
