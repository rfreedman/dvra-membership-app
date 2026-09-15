"""Request bootstrap and route dispatch."""

from __future__ import annotations

import sqlite3
import traceback

from dvra import db as dbmod
from dvra import http as htt
from dvra import schema
from dvra import session as sess
from dvra.passwords import hash_password
from dvra.routes import dispatch
from dvra.settings import Settings


def ensure_bootstrap_admin(conn: sqlite3.Connection, settings: Settings) -> None:
    n = int(conn.execute("SELECT COUNT(*) AS c FROM admin_users").fetchone()[0])
    if n > 0:
        return
    conn.execute(
        "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
        (settings.admin_username, hash_password(settings.admin_password)),
    )
    conn.commit()


def handle_request(body: bytes | None = None) -> htt.Response:
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
