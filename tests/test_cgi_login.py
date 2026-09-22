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


def _login_readonly(tmp_path: Path, username: str = "viewer", password: str = "viewpass") -> tuple[str, str, Path]:
    db = tmp_path / "t.sqlite"
    dsn = "sqlite:" + str(db)
    _run("GET", "/login", dsn=dsn)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO readonly_users (username, password_hash) VALUES (?, ?)",
        (username, hash_password(password)),
    )
    conn.commit()
    conn.close()
    status, headers, _ = _run(
        "POST", "/login", body=f"username={username}&password={password}", dsn=dsn
    )
    assert status == 303
    sid = _session_id(headers)
    return f"dvra_session={sid}", dsn, db


def test_readonly_can_use_app_but_not_admin(tmp_path: Path):
    cookie, dsn, _ = _login_readonly(tmp_path)

    status, headers, body = _run("GET", "/", cookie=cookie, dsn=dsn)
    assert status == 200
    assert b"Members" in body
    assert b">Admin</a>" not in body
    assert b"New member" not in body

    status, headers, body = _run("GET", "/admin", cookie=cookie, dsn=dsn)
    assert status == 303
    assert headers.get("location", "").endswith("/")
    assert b"Create read-only user" not in body

    status, headers, body = _run("GET", "/reports", cookie=cookie, dsn=dsn)
    assert status == 200
    assert b"Reports" in body

    status, headers, body = _run("GET", "/reports/payments", cookie=cookie, dsn=dsn)
    assert status == 200

    status, headers, body = _run("GET", "/members/new", cookie=cookie, dsn=dsn)
    assert status == 303
    assert headers.get("location", "").endswith("/")


def test_readonly_can_view_member_and_payments(tmp_path: Path):
    cookie, dsn, db = _login_readonly(tmp_path)
    conn = sqlite3.connect(db)
    cur = conn.execute(
        """
        INSERT INTO members (last_name, first_name, arrl_member, created_at, updated_at)
        VALUES ('View', 'Only', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
    )
    member_id = int(cur.lastrowid)
    conn.commit()
    conn.close()

    status, headers, body = _run("GET", f"/members/{member_id}/view", cookie=cookie, dsn=dsn)
    assert status == 200
    assert b"View" in body
    assert b"Save member" not in body
    assert b"Delete member" not in body
    assert b"View payments" in body

    status, headers, body = _run("GET", f"/members/{member_id}/payments", cookie=cookie, dsn=dsn)
    assert status == 200
    assert b"Payments" in body
    assert b"Add Payment" not in body


def test_readonly_writes_are_forbidden(tmp_path: Path):
    cookie, dsn, db = _login_readonly(tmp_path)
    conn = sqlite3.connect(db)
    cur = conn.execute(
        """
        INSERT INTO members (last_name, first_name, notes, arrl_member, created_at, updated_at)
        VALUES ('Guard', 'Rails', 'keep me', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
    )
    member_id = int(cur.lastrowid)
    conn.commit()
    conn.close()

    status, headers, body = _run(
        "POST",
        f"/members/{member_id}/edit",
        body="last_name=Hacked&first_name=User",
        cookie=cookie,
        dsn=dsn,
    )
    assert status == 403
    assert b"Read-only accounts cannot change records." in body

    status, headers, body = _run(
        "POST",
        f"/members/{member_id}/note",
        body="notes=should-not-save",
        cookie=cookie,
        dsn=dsn,
    )
    assert status == 403

    status, headers, body = _run(
        "POST",
        f"/members/{member_id}/payments/new",
        body="payment_date=2026-01-15&membership_year=2026",
        cookie=cookie,
        dsn=dsn,
    )
    assert status == 403

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT last_name, notes FROM members WHERE id = ?", (member_id,)
    ).fetchone()
    payment_count = int(
        conn.execute("SELECT COUNT(*) FROM payments WHERE member_id = ?", (member_id,)).fetchone()[0]
    )
    conn.close()
    assert row[0] == "Guard"
    assert row[1] == "keep me"
    assert payment_count == 0


def test_admin_can_create_readonly_user_and_rejects_taken_username(tmp_path: Path):
    db = tmp_path / "t.sqlite"
    dsn = "sqlite:" + str(db)
    status, headers, _ = _run("POST", "/login", body="username=admin&password=admin123", dsn=dsn)
    assert status == 303
    sid = _session_id(headers)
    cookie = f"dvra_session={sid}"

    status, headers, body = _run("GET", "/admin", cookie=cookie, dsn=dsn)
    assert status == 200
    assert b"Read-only users" in body

    status, headers, _ = _run(
        "POST",
        "/readonly-users/create",
        body="username=rouser&password=secret1&display_name=Viewer",
        cookie=cookie,
        dsn=dsn,
    )
    assert status == 303
    loc = headers.get("location", "")
    assert "/admin" in loc
    assert "error=" not in loc

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT username, display_name FROM readonly_users WHERE username = ?", ("rouser",)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "rouser"
    assert row[1] == "Viewer"

    status, headers, _ = _run(
        "POST",
        "/managers/create",
        body="username=takenname&password=secret1",
        cookie=cookie,
        dsn=dsn,
    )
    assert status == 303
    assert "error=" not in headers.get("location", "")

    status, headers, _ = _run(
        "POST",
        "/readonly-users/create",
        body="username=takenname&password=secret2",
        cookie=cookie,
        dsn=dsn,
    )
    assert status == 303
    assert "error=" in headers.get("location", "")


def test_readonly_create_with_duplicate_password_fields_still_logs_in(tmp_path: Path):
    """Password managers sometimes POST password twice; hashing str(list) must not occur."""
    db = tmp_path / "t.sqlite"
    dsn = "sqlite:" + str(db)
    status, headers, _ = _run("POST", "/login", body="username=admin&password=admin123", dsn=dsn)
    assert status == 303
    cookie = f"dvra_session={_session_id(headers)}"

    status, headers, _ = _run(
        "POST",
        "/readonly-users/create",
        body="username=dupro&password=RealPass99&password=RealPass99&display_name=Dup",
        cookie=cookie,
        dsn=dsn,
    )
    assert status == 303
    assert "error=" not in headers.get("location", "")

    _run("POST", "/logout", cookie=cookie, dsn=dsn)
    status, headers, body = _run(
        "POST", "/login", body="username=dupro&password=RealPass99", dsn=dsn
    )
    assert status == 303
    assert headers.get("location", "").endswith("/")
    assert b"Invalid" not in body

    sid = _session_id(headers)
    status, headers, body = _run("GET", "/", cookie=f"dvra_session={sid}", dsn=dsn)
    assert status == 200
    assert b"Members" in body
    assert b">Admin</a>" not in body
    assert b"New member" not in body
