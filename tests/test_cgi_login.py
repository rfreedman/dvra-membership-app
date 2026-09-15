from __future__ import annotations

import os
from pathlib import Path

from dvra.app import handle_request


def _run(method: str, path: str, body: str = "", cookie: str = "", dsn: str = "") -> tuple[int, dict[str, str], bytes]:
    os.environ["REQUEST_METHOD"] = method
    os.environ["PATH_INFO"] = path
    os.environ["SCRIPT_NAME"] = ""
    os.environ["QUERY_STRING"] = ""
    os.environ["CONTENT_TYPE"] = "application/x-www-form-urlencoded"
    raw = body.encode("utf-8")
    os.environ["CONTENT_LENGTH"] = str(len(raw))
    if dsn:
        os.environ["DATABASE_DSN"] = dsn
    if cookie:
        os.environ["HTTP_COOKIE"] = cookie
    else:
        os.environ.pop("HTTP_COOKIE", None)
    resp = handle_request(raw)
    headers = {n.lower(): v for n, v in resp.headers}
    return resp.status, headers, resp.body


def test_health_and_login_roundtrip(tmp_path: Path):
    dsn = "sqlite:" + str(tmp_path / "t.sqlite")
    status, headers, body = _run("GET", "/health", dsn=dsn)
    assert status == 200
    assert body == b"OK"

    status, headers, body = _run("GET", "/login", dsn=dsn)
    assert status == 200
    assert b"Sign in" in body

    status, headers, body = _run(
        "POST",
        "/login",
        body="username=admin&password=admin123",
        dsn=dsn,
    )
    assert status == 303
    assert headers.get("location", "").endswith("/")
    cookie = headers.get("set-cookie", "")
    assert "dvra_session=" in cookie
    sid = cookie.split("dvra_session=")[1].split(";")[0]
    status, headers, body = _run("GET", "/", cookie=f"dvra_session={sid}", dsn=dsn)
    assert status == 200
    assert b"Members" in body
