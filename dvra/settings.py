"""Environment-style settings."""

from __future__ import annotations

import os

from dvra.paths import DEFAULT_SQLITE_PATH


def _nz(value: str | None, default: str) -> str:
    if value is None or value.strip() == "":
        return default
    return value.strip()


class Settings:
    def __init__(self) -> None:
        dsn = os.environ.get("DATABASE_DSN") or f"sqlite:{DEFAULT_SQLITE_PATH}"
        self.data = {
            "DATABASE_DSN": dsn,
            "DVRA_ADMIN_USERNAME": _nz(os.environ.get("DVRA_ADMIN_USERNAME"), "admin"),
            "DVRA_ADMIN_PASSWORD": _nz(os.environ.get("DVRA_ADMIN_PASSWORD"), "admin123"),
        }

    def get(self, key: str) -> str:
        return self.data.get(key, "")
