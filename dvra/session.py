"""File-backed session store (CGI-safe; no in-process memory)."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any

from dvra.http import Response, parse_cookies
from dvra.paths import SESSIONS_DIR

COOKIE_NAME = "dvra_session"
SESSION_SUFFIX = ".json"


def _session_path(sid: str) -> Path:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return SESSIONS_DIR / f"{sid}{SESSION_SUFFIX}"


def _new_sid() -> str:
    return secrets.token_hex(16)


def load_session() -> tuple[str, dict[str, Any], bool]:
    """Return (session_id, data, is_new)."""
    cookies = parse_cookies()
    sid = cookies.get(COOKIE_NAME, "").strip()
    if sid and all(c in "0123456789abcdef" for c in sid) and len(sid) == 32:
        path = _session_path(sid)
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return sid, data, False
            except (OSError, json.JSONDecodeError):
                pass
    return _new_sid(), {}, True


def save_session(sid: str, data: dict[str, Any]) -> None:
    path = _session_path(sid)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
    tmp.replace(path)


def destroy_session(sid: str) -> None:
    path = _session_path(sid)
    try:
        path.unlink()
    except OSError:
        pass


def attach_session_cookie(response: Response, sid: str, *, clear: bool = False) -> None:
    https = os.environ.get("HTTPS", "").lower() not in ("", "off", "0")
    parts = [
        f"{COOKIE_NAME}={sid}",
        "Path=/",
        "HttpOnly",
        "SameSite=Lax",
    ]
    if https:
        parts.append("Secure")
    if clear:
        parts.append("Max-Age=0")
    else:
        parts.append("Max-Age=2592000")
    response.add_header("Set-Cookie", "; ".join(parts))
