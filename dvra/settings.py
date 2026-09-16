"""Typed application settings from the environment (optional .env in the repo root)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from dvra.paths import DEFAULT_SQLITE_PATH, ROOT_DIR


def _nz(value: str | None, default: str) -> str:
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in ("1", "true", "yes", "on")


def _load_optional_dotenv() -> None:
    env_path = ROOT_DIR / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)


@dataclass(frozen=True)
class Settings:
    database_dsn: str
    admin_username: str
    admin_password: str
    display_errors: bool
    session_cookie_name: str
    session_max_age: int
    roster_cors_origin: str

    @classmethod
    def load(cls) -> Settings:
        _load_optional_dotenv()
        dsn = os.environ.get("DATABASE_DSN") or f"sqlite:{DEFAULT_SQLITE_PATH}"
        try:
            max_age = int(_nz(os.environ.get("DVRA_SESSION_MAX_AGE"), "2592000"))
        except ValueError:
            max_age = 2592000
        if max_age < 0:
            max_age = 2592000
        return cls(
            database_dsn=dsn.strip(),
            admin_username=_nz(os.environ.get("DVRA_ADMIN_USERNAME"), "admin"),
            admin_password=_nz(os.environ.get("DVRA_ADMIN_PASSWORD"), "admin123"),
            display_errors=_truthy(os.environ.get("DVRA_DISPLAY_ERRORS")),
            session_cookie_name=_nz(os.environ.get("DVRA_SESSION_COOKIE"), "dvra_session"),
            session_max_age=max_age,
            roster_cors_origin=_nz(os.environ.get("DVRA_ROSTER_CORS_ORIGIN"), "https://w2zq.com"),
        )
