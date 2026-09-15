"""Request context passed to page handlers."""

from __future__ import annotations

from typing import Any, TypedDict

import sqlite3


class RequestCtx(TypedDict):
    conn: sqlite3.Connection
    session: dict[str, Any]
    form: dict[str, Any]
    query: dict[str, str]
