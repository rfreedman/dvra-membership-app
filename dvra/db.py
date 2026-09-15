"""SQLite connection helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dvra.settings import Settings


def sqlite_path_from_dsn(dsn: str) -> str:
    if dsn.startswith("sqlite:"):
        path = dsn[len("sqlite:") :]
        if path.startswith("///"):
            return path[3:] or ":memory:"
        if path.startswith("//"):
            return path[1:]
        return path or ":memory:"
    return dsn


def connect(settings: Settings) -> sqlite3.Connection:
    dsn = settings.get("DATABASE_DSN")
    path = sqlite_path_from_dsn(dsn)
    if path not in (":memory:", "") and not path.startswith("file:"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
