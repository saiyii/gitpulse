"""GitHub App authentication.

The app signs a short-lived JWT with its private key, then trades it for an
installation access token (valid for one hour) to act on a given installation.
See https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime

import aiohttp
import jwt

log = logging.getLogger(__name__)

API_URL = "https://api.github.com"
API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "GitPulse",
}

# GitHub refuses JWTs that live longer than 10 minutes.
_JWT_LIFETIME = 9 * 60
# Refresh tokens a bit before they actually expire.
_REFRESH_MARGIN = 120


class GitHubAuthError(RuntimeError):
    pass


@dataclass(slots=True)
class _CachedToken:
    token: str
    expires_at: float

    def is_fresh(self) -> bool:
        return time.time() < self.expires_at - _REFRESH_MARGIN


class GitHubAppAuth:
    def __init__(self, app_id: str, private_key: str, session: aiohttp.ClientSession) -> None:
        self.app_id = app_id
        self._private_key = private_key
        self._session = session
        self._jwt: _CachedToken | None = None
        self._tokens: dict[int, _CachedToken] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    def app_jwt(self) -> str:
        if self._jwt is None or not self._jwt.is_fresh():
            now = int(time.time())
            payload = {
                # backdate a little to tolerate clock drift between us and GitHub
                "iat": now - 60,
                "exp": now + _JWT_LIFETIME,
                "iss": self.app_id,
            }
            token = jwt.encode(payload, self._private_key, algorithm="RS256")
            self._jwt = _CachedToken(token, now + _JWT_LIFETIME)
        return self._jwt.token

    async def installation_token(self, installation_id: int) -> str:
        cached = self._tokens.get(installation_id)
        if cached and cached.is_fresh():
            return cached.token

        lock = self._locks.setdefault(installation_id, asyncio.Lock())
        async with lock:
            # another task may have refreshed it while we were waiting
            cached = self._tokens.get(installation_id)
            if cached and cached.is_fresh():
                return cached.token

            url = f"{API_URL}/app/installations/{installation_id}/access_tokens"
            headers = {**API_HEADERS, "Authorization": f"Bearer {self.app_jwt()}"}
            async with self._session.post(url, headers=headers) as resp:
                data = await resp.json(content_type=None)
                if resp.status != 201:
                    message = data.get("message") if isinstance(data, dict) else None
                    raise GitHubAuthError(
                        f"could not get a token for installation {installation_id}: "
                        f"{resp.status} {message or ''}".strip()
                    )

            expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
            self._tokens[installation_id] = _CachedToken(data["token"], expires_at.timestamp())
            log.debug("new token for installation %s, expires %s", installation_id, expires_at)
            return data["token"]

    def forget(self, installation_id: int) -> None:
        self._tokens.pop(installation_id, None)
