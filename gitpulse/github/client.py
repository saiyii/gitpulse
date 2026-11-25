from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import aiohttp

from .auth import API_HEADERS, API_URL, GitHubAppAuth, GitHubAuthError

log = logging.getLogger(__name__)

# How long we remember whether a repo has the app installed.
_INSTALLATION_TTL = 10 * 60


class GitHubError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


class NotFound(GitHubError):
    pass


class RateLimited(GitHubError):
    def __init__(self, reset_at: int) -> None:
        super().__init__(403, "rate limit exceeded")
        self.reset_at = reset_at


class NotInstalled(Exception):
    def __init__(self, repo: str) -> None:
        super().__init__(f"the GitHub App is not installed on {repo}")
        self.repo = repo


@dataclass(slots=True)
class RateLimit:
    limit: int
    remaining: int
    reset_at: int

    @classmethod
    def from_headers(cls, headers: Any) -> RateLimit | None:
        try:
            return cls(
                limit=int(headers["X-RateLimit-Limit"]),
                remaining=int(headers["X-RateLimit-Remaining"]),
                reset_at=int(headers["X-RateLimit-Reset"]),
            )
        except (KeyError, ValueError):
            return None


class GitHubClient:
    """Small wrapper around the handful of REST endpoints GitPulse needs.

    Read calls try, in order: the repo's own installation token, a token from
    any installation of the app (it can read public repos), the optional
    personal access token, and finally an anonymous request.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        auth: GitHubAppAuth,
        fallback_token: str | None = None,
        base_url: str = API_URL,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self.auth = auth
        self._fallback_token = fallback_token
        self._installations: dict[str, tuple[int | None, float]] = {}
        self._any_installation: tuple[int | None, float] | None = None
        self.rate_limit: RateLimit | None = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None,
        json: Any = None,
    ) -> Any:
        headers = dict(API_HEADERS)
        if token:
            headers["Authorization"] = f"Bearer {token}"

        url = self._base_url + path
        async with self._session.request(method, url, headers=headers, json=json) as resp:
            limit = RateLimit.from_headers(resp.headers)
            if limit:
                self.rate_limit = limit
                if limit.remaining < max(10, limit.limit // 20):
                    log.warning("GitHub rate limit low: %s/%s left", limit.remaining, limit.limit)

            if resp.status == 204:
                return None
            data = await resp.json(content_type=None) if resp.content_length != 0 else None

            if resp.status < 400:
                return data

            message = data.get("message", resp.reason) if isinstance(data, dict) else resp.reason
            if resp.status in (403, 429) and limit and limit.remaining == 0:
                raise RateLimited(limit.reset_at)
            if resp.status == 404:
                raise NotFound(404, message or "Not Found")
            raise GitHubError(resp.status, message or "request failed")

    # -- app level ----------------------------------------------------------

    async def get_app(self) -> dict[str, Any]:
        return await self._request("GET", "/app", token=self.auth.app_jwt())

    async def repo_installation(self, repo: str) -> int | None:
        key = repo.lower()
        cached = self._installations.get(key)
        if cached and cached[1] > time.monotonic():
            return cached[0]

        try:
            data = await self._request(
                "GET", f"/repos/{repo}/installation", token=self.auth.app_jwt()
            )
            installation_id: int | None = data["id"]
        except NotFound:
            installation_id = None

        self._installations[key] = (installation_id, time.monotonic() + _INSTALLATION_TTL)
        return installation_id

    def remember_installation(self, repo: str, installation_id: int) -> None:
        self._installations[repo.lower()] = (installation_id, time.monotonic() + _INSTALLATION_TTL)

    async def _some_installation(self) -> int | None:
        if self._any_installation and self._any_installation[1] > time.monotonic():
            return self._any_installation[0]
        data = await self._request(
            "GET", "/app/installations?per_page=1", token=self.auth.app_jwt()
        )
        installation_id = data[0]["id"] if data else None
        self._any_installation = (installation_id, time.monotonic() + _INSTALLATION_TTL)
        return installation_id

    async def _read_token(self, repo: str) -> str | None:
        try:
            installation_id = await self.repo_installation(repo)
            if installation_id is None:
                installation_id = await self._some_installation()
            if installation_id is not None:
                return await self.auth.installation_token(installation_id)
        except (GitHubError, GitHubAuthError) as exc:
            log.warning("falling back from app auth for %s: %s", repo, exc)
        return self._fallback_token

    # -- repositories -------------------------------------------------------

    async def get_repo(self, repo: str) -> dict[str, Any]:
        return await self._request("GET", f"/repos/{repo}", token=await self._read_token(repo))

    async def get_latest_release(self, repo: str) -> dict[str, Any] | None:
        try:
            return await self._request(
                "GET", f"/repos/{repo}/releases/latest", token=await self._read_token(repo)
            )
        except NotFound:
            return None

    async def create_issue(self, repo: str, title: str, body: str | None) -> dict[str, Any]:
        installation_id = await self.repo_installation(repo)
        if installation_id is None:
            raise NotInstalled(repo)
        token = await self.auth.installation_token(installation_id)
        payload: dict[str, Any] = {"title": title}
        if body:
            payload["body"] = body
        return await self._request("POST", f"/repos/{repo}/issues", token=token, json=payload)
