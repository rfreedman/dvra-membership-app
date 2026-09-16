"""Request bootstrap and route dispatch."""

from __future__ import annotations

import sqlite3
import traceback

from dvra import db as dbmod
from dvra import http as htt
from dvra import schema
from dvra import session as sess
from dvra.auth import is_logged_in
from dvra.list_params import members_merge_client_sort
from dvra.passwords import hash_password
from dvra.settings import Settings
from dvra.static_files import serve_static


def ensure_bootstrap_admin(conn: sqlite3.Connection, settings: Settings) -> None:
    n = int(conn.execute("SELECT COUNT(*) AS c FROM admin_users").fetchone()[0])
    if n > 0:
        return
    conn.execute(
        "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
        (settings.admin_username, hash_password(settings.admin_password)),
    )
    conn.commit()


def _handle_session_touch(body: bytes | None) -> htt.Response:
    """Sort persist for the members grid: session only, no DB or heavy imports."""
    settings = Settings.load()
    sid, session_data, _ = sess.load_session(settings.session_cookie_name)
    if not is_logged_in(session_data):
        response = htt.redirect(htt.url_for("/login"), status=302)
    else:
        form = htt.parse_form(body)
        members_merge_client_sort(session_data, form)
        response = htt.empty(204)
    sess.save_session(sid, {k: v for k, v in session_data.items() if k != "_destroyed"})
    sess.attach_session_cookie(
        response,
        sid,
        cookie_name=settings.session_cookie_name,
        max_age=settings.session_max_age,
    )
    return response


def handle_request(body: bytes | None = None) -> htt.Response:
    # CGI PATH_INFO under /index.py/static/... (or ErrorDocument → index.py).
    # Serve files without opening the DB or touching sessions.
    method = htt.request_method()
    path = htt.request_path()
    if method in ("GET", "HEAD") and path.startswith("/static/"):
        return serve_static(path)

    if method == "GET" and path == "/health":
        return htt.text("OK")

    # Public WordPress roster — no session files on every embed/API hit.
    if path == "/api/roster" or path == "/api/roster/embed":
        from dvra.pages.public_roster import try_handle_public_roster

        roster = try_handle_public_roster(method, path)
        if roster is not None:
            return roster

    # Members grid sort beacon — keep this path free of DB + export/page imports.
    if method == "POST" and path == "/members/session-touch":
        return _handle_session_touch(body)

    # Deferred so static + session-touch avoid loading pages/exports/jinja.
    from dvra.routes import dispatch

    settings = Settings.load()
    sid, session_data, _ = sess.load_session(settings.session_cookie_name)
    conn = dbmod.connect(settings)
    try:
        schema.ensure(conn)
        ensure_bootstrap_admin(conn, settings)
        form = htt.parse_form(body)
        response = dispatch(conn, session_data, form)
    except Exception:
        if settings.display_errors:
            response = htt.text(traceback.format_exc(), status=500)
        else:
            response = htt.text("Internal server error", status=500)
    finally:
        conn.close()

    if session_data.get("_destroyed"):
        sess.destroy_session(sid)
        sess.attach_session_cookie(
            response,
            sid,
            cookie_name=settings.session_cookie_name,
            max_age=settings.session_max_age,
            clear=True,
        )
    else:
        sess.save_session(sid, {k: v for k, v in session_data.items() if k != "_destroyed"})
        sess.attach_session_cookie(
            response,
            sid,
            cookie_name=settings.session_cookie_name,
            max_age=settings.session_max_age,
        )
    return response
