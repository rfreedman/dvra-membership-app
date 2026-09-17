from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from dvra.app import handle_request
from dvra.app_settings import AppSettingsRepository
from dvra.passwords import hash_password
from dvra.payments import PaymentRepository
from dvra.schema import ensure


def _run(
    method: str,
    path: str,
    body: str = "",
    cookie: str = "",
    dsn: str = "",
    *,
    cors_origin: str | None = None,
    request_origin: str | None = None,
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
    if request_origin is not None:
        os.environ["HTTP_ORIGIN"] = request_origin
    else:
        os.environ.pop("HTTP_ORIGIN", None)
    if cors_origin is not None:
        os.environ["DVRA_ROSTER_CORS_ORIGIN"] = cors_origin
    else:
        os.environ.pop("DVRA_ROSTER_CORS_ORIGIN", None)
    resp = handle_request(raw)
    headers = {n.lower(): v for n, v in resp.headers}
    return resp.status, headers, resp.body


def _seed_roster_db(db_path: Path, year: int = 2026) -> str:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure(conn)
    AppSettingsRepository(conn).set_current_membership_year(year)

    def add(last: str, first: str, call: str | None) -> int:
        cur = conn.execute(
            """
            INSERT INTO members (
                last_name, first_name, call_sign, arrl_member, created_at, updated_at
            ) VALUES (?, ?, ?, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (last, first, call),
        )
        conn.commit()
        return int(cur.lastrowid)

    a = add("Able", "Ann", "W2AAA")
    b = add("Baker", "Bob", "K2BBB")
    c = add("Charlie", "Chris", None)
    d = add("Delta", "Dana", "N2DDD")  # unpaid for current year

    pay = PaymentRepository(conn)
    for mid in (a, b, c):
        pay.insert_payment(
            mid,
            {
                "payment_date": f"{year}-01-15",
                "membership_year": year,
                "membership_type_id": None,
                "notes": None,
                "form_number": None,
            },
        )
    # Prior-year payment only — must not appear on current roster
    pay.insert_payment(
        d,
        {
            "payment_date": f"{year - 1}-01-15",
            "membership_year": year - 1,
            "membership_type_id": None,
            "notes": None,
            "form_number": None,
        },
    )
    conn.close()
    return "sqlite:" + str(db_path)


def test_public_roster_json_unauthenticated(tmp_path: Path):
    dsn = _seed_roster_db(tmp_path / "roster.sqlite", year=2026)
    status, headers, body = _run("GET", "/api/roster", dsn=dsn)
    assert status == 200
    assert "application/json" in headers.get("content-type", "")
    assert "set-cookie" not in headers
    assert headers.get("access-control-allow-origin") == "https://w2zq.com"
    assert headers.get("access-control-allow-methods") == "GET, OPTIONS"
    assert headers.get("cache-control") == "public, max-age=300"

    data = json.loads(body.decode("utf-8"))
    assert data["membership_year"] == 2026
    assert "generated_at" in data
    assert data["generated_at"].endswith("Z")

    by_name = data["by_name"]
    assert [r["last_name"] for r in by_name] == ["Able", "Baker", "Charlie"]
    assert by_name[0] == {"last_name": "Able", "first_name": "Ann", "call_sign": "W2AAA"}
    assert by_name[2]["call_sign"] == ""
    assert "Delta" not in {r["last_name"] for r in by_name}

    by_cs = data["by_callsign"]
    assert [r["call_sign"] for r in by_cs] == ["K2BBB", "W2AAA", ""]
    assert [r["last_name"] for r in by_cs] == ["Baker", "Able", "Charlie"]


def test_public_roster_cors_options_and_custom_origin(tmp_path: Path):
    dsn = _seed_roster_db(tmp_path / "roster.sqlite")
    status, headers, body = _run(
        "OPTIONS",
        "/api/roster",
        dsn=dsn,
        cors_origin="https://example.org",
    )
    assert status == 204
    assert body == b""
    assert headers.get("access-control-allow-origin") == "https://example.org"
    assert "set-cookie" not in headers

    status, headers, _ = _run(
        "GET",
        "/api/roster",
        dsn=dsn,
        cors_origin="https://example.org",
    )
    assert status == 200
    assert headers.get("access-control-allow-origin") == "https://example.org"


def test_public_roster_embed_html(tmp_path: Path):
    dsn = _seed_roster_db(tmp_path / "roster.sqlite", year=2026)
    status, headers, body = _run("GET", "/api/roster/embed", dsn=dsn)
    assert status == 200
    assert "text/html" in headers.get("content-type", "")
    assert "set-cookie" not in headers
    assert headers.get("access-control-allow-origin") == "https://w2zq.com"
    text = body.decode("utf-8")
    assert "By Name" in text
    assert "By Callsign" in text
    assert "Able" in text and "Ann" in text and "W2AAA" in text
    assert "Baker" in text and "K2BBB" in text
    assert "Charlie" in text
    assert "Delta" not in text
    assert "membership year 2026" in text
    assert "postMessage" in text
    assert "dvra-roster" in text
    assert "scrollHeight" in text
    assert "allowedOrigins" in text
    assert "overflow: auto" in text
    assert "https://w2zq.com" in text
    assert "https://www.w2zq.com" in text
    name_html = text[text.find('id="panel-name"') : text.find('id="panel-call"')]
    call_html = text[text.find('id="panel-call"') :]
    assert name_html.index("Last name") < name_html.index("First name") < name_html.index("Call sign")
    assert call_html.index("Call sign") < call_html.index("Last name") < call_html.index("First name")
    assert '<td class="row-num">1</td>' in name_html
    assert '<td class="row-num">1</td>' in call_html


def test_public_roster_cors_allows_www_counterpart(tmp_path: Path):
    dsn = _seed_roster_db(tmp_path / "roster.sqlite")
    status, headers, _ = _run(
        "GET",
        "/api/roster",
        dsn=dsn,
        request_origin="https://www.w2zq.com",
    )
    assert status == 200
    assert headers.get("access-control-allow-origin") == "https://www.w2zq.com"

    status, headers, _ = _run(
        "GET",
        "/api/roster",
        dsn=dsn,
        request_origin="https://evil.example",
    )
    assert status == 200
    assert headers.get("access-control-allow-origin") == "https://w2zq.com"


def test_allowed_roster_origins_pairs_www_and_apex():
    from dvra.pages.public_roster import allowed_roster_origins

    assert allowed_roster_origins("https://w2zq.com") == [
        "https://w2zq.com",
        "https://www.w2zq.com",
    ]
    assert allowed_roster_origins("https://www.w2zq.com") == [
        "https://www.w2zq.com",
        "https://w2zq.com",
    ]
    assert allowed_roster_origins("http://localhost:8089") == ["http://localhost:8089"]


def test_public_roster_does_not_require_login(tmp_path: Path):
    dsn = _seed_roster_db(tmp_path / "roster.sqlite")
    # Bootstrap an admin so a login session would work if created — roster must still skip it.
    conn = sqlite3.connect(str(tmp_path / "roster.sqlite"))
    conn.execute(
        "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
        ("admin", hash_password("admin123")),
    )
    conn.commit()
    conn.close()

    status, headers, body = _run("GET", "/api/roster", dsn=dsn)
    assert status == 200
    assert json.loads(body.decode("utf-8"))["membership_year"] == 2026
    assert "set-cookie" not in headers
    assert "location" not in headers
