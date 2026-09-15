from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from dvra.app import handle_request
from dvra.passwords import hash_password


def _run(
    method: str,
    path: str,
    body: str = "",
    cookie: str = "",
    dsn: str = "",
    *,
    script_name: str = "",
    request_uri: str = "",
    redirect_url: str = "",
) -> tuple[int, dict[str, str], bytes]:
    os.environ["REQUEST_METHOD"] = method
    os.environ["PATH_INFO"] = path
    os.environ["SCRIPT_NAME"] = script_name
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
    if request_uri:
        os.environ["REQUEST_URI"] = request_uri
    else:
        os.environ.pop("REQUEST_URI", None)
    if redirect_url:
        os.environ["REDIRECT_URL"] = redirect_url
    else:
        os.environ.pop("REDIRECT_URL", None)
    resp = handle_request(raw)
    headers = {n.lower(): v for n, v in resp.headers}
    return resp.status, headers, resp.body


def test_cgi_serves_static_path_info(tmp_path: Path):
    dsn = "sqlite:" + str(tmp_path / "t.sqlite")
    status, headers, body = _run("GET", "/static/style.css", dsn=dsn)
    assert status == 200
    assert "text/css" in headers.get("content-type", "")
    assert b"{" in body or b"." in body
    status, headers, body = _run("GET", "/static/../index.py", dsn=dsn)
    assert status == 404
    status, headers, body = _run("GET", "/static/no-such-file.css", dsn=dsn)
    assert status == 404


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
    assert b">Admin</a>" in body
    status, headers, body = _run("GET", "/admin", cookie=f"dvra_session={sid}", dsn=dsn)
    assert status == 200
    assert b"Admin" in body


def _session_id(headers: dict[str, str]) -> str:
    cookie = headers.get("set-cookie", "")
    assert "dvra_session=" in cookie
    return cookie.split("dvra_session=")[1].split(";")[0]


def test_manager_can_use_app_but_not_admin(tmp_path: Path):
    db = tmp_path / "t.sqlite"
    dsn = "sqlite:" + str(db)
    # /login goes through full bootstrap (schema); /health is a no-DB fast path.
    _run("GET", "/login", dsn=dsn)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO managers (username, password_hash) VALUES (?, ?)",
        ("mgr", hash_password("mgrpass")),
    )
    conn.commit()
    conn.close()

    status, headers, _ = _run("POST", "/login", body="username=mgr&password=mgrpass", dsn=dsn)
    assert status == 303
    sid = _session_id(headers)
    cookie = f"dvra_session={sid}"

    status, headers, body = _run("GET", "/", cookie=cookie, dsn=dsn)
    assert status == 200
    assert b"Members" in body
    assert b">Admin</a>" not in body

    status, headers, body = _run("GET", "/admin", cookie=cookie, dsn=dsn)
    assert status == 303
    assert headers.get("location", "").endswith("/")
    assert b"Current membership year" not in body
    assert b"Create manager" not in body

    # DreamHost-style: /admin hits index.py with empty PATH_INFO but REQUEST_URI=/admin
    status, headers, body = _run(
        "GET",
        "",
        cookie=cookie,
        dsn=dsn,
        script_name="/index.py",
        request_uri="/admin",
        redirect_url="/admin",
    )
    assert status == 303
    assert headers.get("location", "").endswith("/")
    assert b"Create manager" not in body

    status, headers, body = _run(
        "POST", "/managers/create", body="username=x&password=y", cookie=cookie, dsn=dsn
    )
    assert status == 303
    assert headers.get("location", "").endswith("/")
    assert "/admin" not in headers.get("location", "")


def test_admin_rejects_username_already_used_as_manager(tmp_path: Path):
    db = tmp_path / "t.sqlite"
    dsn = "sqlite:" + str(db)
    status, headers, _ = _run("POST", "/login", body="username=admin&password=admin123", dsn=dsn)
    assert status == 303
    sid = _session_id(headers)
    cookie = f"dvra_session={sid}"
    status, headers, _ = _run(
        "POST",
        "/managers/create",
        body="username=shareduser&password=secret1",
        cookie=cookie,
        dsn=dsn,
    )
    assert status == 303
    loc = headers.get("location", "")
    assert "/admin" in loc
    assert "error=" not in loc
    status, headers, _ = _run(
        "POST",
        "/admins/create",
        body="username=shareduser&password=secret2",
        cookie=cookie,
        dsn=dsn,
    )
    assert status == 303
    loc = headers.get("location", "")
    assert "error=" in loc
