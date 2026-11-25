from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    pass


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _required(name: str) -> str:
    value = _get(name)
    if not value:
        raise ConfigError(f"{name} is not set (see .env.example)")
    return value


def _int_or_none(name: str) -> int | None:
    value = _get(name)
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        raise ConfigError(f"{name} must be a number, got {value!r}") from None


def _bool(name: str, default: bool = False) -> bool:
    value = _get(name).lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Config:
    discord_token: str
    discord_guild_id: int | None
    github_app_id: str
    github_private_key: str
    github_webhook_secret: str
    github_token: str | None
    webhook_host: str
    webhook_port: int
    admin_role_name: str
    support_email: str
    push_all_branches: bool
    database_path: Path
    log_level: str

    @classmethod
    def from_env(cls) -> Config:
        load_dotenv()

        key_path = Path(_get("GITHUB_APP_PRIVATE_KEY_PATH", "./private-key.pem"))
        if not key_path.is_file():
            raise ConfigError(f"GitHub App private key not found at {key_path}")

        # Pterodactyl exposes the allocated port as SERVER_PORT.
        port = _int_or_none("WEBHOOK_PORT") or _int_or_none("SERVER_PORT") or 8080

        return cls(
            discord_token=_required("DISCORD_TOKEN"),
            discord_guild_id=_int_or_none("DISCORD_GUILD_ID"),
            github_app_id=_required("GITHUB_APP_ID"),
            github_private_key=key_path.read_text(encoding="utf-8"),
            github_webhook_secret=_required("GITHUB_WEBHOOK_SECRET"),
            github_token=_get("GITHUB_TOKEN") or None,
            webhook_host=_get("WEBHOOK_HOST", "0.0.0.0"),
            webhook_port=port,
            admin_role_name=_get("ADMIN_ROLE_NAME", "Admin"),
            support_email=_get("SUPPORT_EMAIL", "support@saiyiidev.com"),
            push_all_branches=_bool("PUSH_ALL_BRANCHES"),
            database_path=Path(_get("DATABASE_PATH", "./gitpulse.db")),
            log_level=_get("LOG_LEVEL", "INFO").upper(),
        )
