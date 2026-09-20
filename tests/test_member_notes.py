from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from urllib.parse import urlencode

from dvra.app import handle_request
from dvra.schema import SCHEMA_USER_VERSION, ensure, sqlite_table_has_column
from tests.conftest import ensure_member_form_reference_data, insert_member, member_create_form, memory_db


def _run(
    method: str,
    path: str,
    body: str = "",
    cookie: str = "",
    dsn: str = "",
) -> tuple[int, dict[str, str], bytes]:
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
    os.environ.pop("REQUEST_URI", None)
    os.environ.pop("REDIRECT_URL", None)
    resp = handle_request(raw)
    headers = {n.lower(): v for n, v in resp.headers}
    return resp.status, headers, resp.body


def _session_id(headers: dict[str, str]) -> str:
    cookie = headers.get("set-cookie", "")
    assert "dvra_session=" in cookie
    return cookie.split("dvra_session=")[1].split(";")[0]


def _login_admin(dsn: str) -> str:
    status, headers, _ = _run("POST", "/login", body="username=admin&password=admin123", dsn=dsn)
    assert status == 303
    return f"dvra_session={_session_id(headers)}"


def test_schema_adds_members_notes_column():
    conn = memory_db()
    assert sqlite_table_has_column(conn, "members", "notes")
    assert sqlite_table_has_column(conn, "members", "nickname")
    assert sqlite_table_has_column(conn, "members", "qrz_email")
    assert sqlite_table_has_column(conn, "members", "family_primary_member_id")
    assert sqlite_table_has_column(conn, "members", "deceased")
    assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == SCHEMA_USER_VERSION
    conn.close()


def test_schema_migrates_legacy_members_without_notes(tmp_path: Path):
    db = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    # Minimal pre-v4 members table (notes missing); include columns required by schema indexes.
    conn.execute(
        """
        CREATE TABLE members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            last_name VARCHAR(128) NOT NULL,
            first_name VARCHAR(128) NOT NULL,
            call_sign VARCHAR(32),
            email VARCHAR(320),
            phone VARCHAR(64),
            address_street TEXT,
            address_city TEXT,
            address_state VARCHAR(16),
            address_zip VARCHAR(16),
            license_class_id INTEGER,
            membership_type_id INTEGER,
            arrl_member INTEGER NOT NULL DEFAULT 0,
            key_number INTEGER,
            paid_through TEXT,
            created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
        )
        """
    )
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    assert not sqlite_table_has_column(conn, "members", "notes")
    ensure(conn)
    assert sqlite_table_has_column(conn, "members", "notes")
    assert sqlite_table_has_column(conn, "members", "family_primary_member_id")
    assert sqlite_table_has_column(conn, "members", "deceased")
    assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == SCHEMA_USER_VERSION
    conn.close()


def test_member_note_get_post_clear(tmp_path: Path):
    db = tmp_path / "t.sqlite"
    dsn = "sqlite:" + str(db)
    cookie = _login_admin(dsn)
    conn = sqlite3.connect(db)
    mid = insert_member(conn, "Note", "Owner")
    conn.close()

    status, headers, body = _run("GET", f"/members/{mid}/note", cookie=cookie, dsn=dsn)
    assert status == 200
    assert "application/json" in headers.get("content-type", "")
    payload = json.loads(body.decode("utf-8"))
    assert payload["notes"] == ""
    assert payload["has_note"] is False
    assert "Note, Owner" in payload["label"]

    status, headers, body = _run(
        "POST",
        f"/members/{mid}/note",
        body="notes=Hello+world",
        cookie=cookie,
        dsn=dsn,
    )
    assert status == 200
    payload = json.loads(body.decode("utf-8"))
    assert payload["ok"] is True
    assert payload["has_note"] is True
    assert payload["notes"] == "Hello world"

    status, headers, body = _run("GET", f"/members/{mid}/note", cookie=cookie, dsn=dsn)
    assert status == 200
    payload = json.loads(body.decode("utf-8"))
    assert payload["notes"] == "Hello world"
    assert payload["has_note"] is True

    status, headers, body = _run(
        "POST",
        f"/members/{mid}/note",
        body="notes=",
        cookie=cookie,
        dsn=dsn,
    )
    assert status == 200
    payload = json.loads(body.decode("utf-8"))
    assert payload["has_note"] is False
    assert payload["notes"] == ""

    conn = sqlite3.connect(db)
    row = conn.execute("SELECT notes FROM members WHERE id = ?", (mid,)).fetchone()
    assert row[0] is None
    conn.close()


def test_member_detail_edit_saves_notes(tmp_path: Path):
    db = tmp_path / "t.sqlite"
    dsn = "sqlite:" + str(db)
    cookie = _login_admin(dsn)
    conn = sqlite3.connect(db)
    ensure_member_form_reference_data(conn)
    mid = insert_member(conn, "Detail", "Notes")
    edit_body = urlencode(
        member_create_form(
            conn,
            last_name="Detail",
            first_name="Notes",
            notes="Saved on detail",
        )
    )
    conn.close()

    status, headers, body = _run("GET", f"/members/{mid}/view", cookie=cookie, dsn=dsn)
    assert status == 200
    assert b'name="notes"' in body
    assert b"<textarea" in body

    status, headers, _ = _run(
        "POST",
        f"/members/{mid}/edit",
        body=edit_body,
        cookie=cookie,
        dsn=dsn,
    )
    assert status == 303

    conn = sqlite3.connect(db)
    row = conn.execute("SELECT notes FROM members WHERE id = ?", (mid,)).fetchone()
    assert row[0] == "Saved on detail"
    conn.close()


def test_members_list_includes_has_note_flag(tmp_path: Path):
    db = tmp_path / "t.sqlite"
    dsn = "sqlite:" + str(db)
    cookie = _login_admin(dsn)
    conn = sqlite3.connect(db)
    mid = insert_member(conn, "Flag", "HasNote")
    conn.execute("UPDATE members SET notes = ? WHERE id = ?", ("present", mid))
    conn.execute(
        """
        INSERT INTO payments (member_id, payment_date, paid_through, membership_year, created_at)
        VALUES (?, '2026-01-01', '2026-12-31', 2026, CURRENT_TIMESTAMP)
        """,
        (mid,),
    )
    conn.commit()
    conn.close()

    status, headers, body = _run("GET", "/", cookie=cookie, dsn=dsn)
    assert status == 200
    assert b'"has_note": true' in body or b'"has_note":true' in body
    assert b"members-note-btn" in body
    assert b'id="member-note-dialog"' in body


def test_payment_page_uses_notes_textarea(tmp_path: Path):
    db = tmp_path / "t.sqlite"
    dsn = "sqlite:" + str(db)
    cookie = _login_admin(dsn)
    conn = sqlite3.connect(db)
    mid = insert_member(conn)
    conn.execute(
        """
        INSERT INTO payments (member_id, payment_date, paid_through, membership_year, notes, created_at)
        VALUES (?, '2026-01-01', '2026-12-31', 2026, 'pay note', CURRENT_TIMESTAMP)
        """,
        (mid,),
    )
    conn.commit()
    conn.close()

    status, headers, body = _run("GET", f"/members/{mid}/payments", cookie=cookie, dsn=dsn)
    assert status == 200
    assert b'name="notes"' in body
    assert b"payment-notes-input" in body
    assert b"<textarea" in body
    assert b"pay note" in body
