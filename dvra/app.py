"""Request bootstrap and route dispatch."""

from __future__ import annotations

import os
import sqlite3
import traceback
from typing import Any

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
    user = settings.get("DVRA_ADMIN_USERNAME")
    password = settings.get("DVRA_ADMIN_PASSWORD")
    conn.execute(
        "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
        (user, hash_password(password)),
    )
    conn.commit()


def handle_request(body: bytes | None = None) -> htt.Response:
    settings = Settings()
    sid, session_data, is_new = sess.load_session()
    conn = dbmod.connect(settings)
    try:
        schema.ensure(conn)
        ensure_bootstrap_admin(conn, settings)
        form = htt.parse_form(body)
        response = dispatch(conn, session_data, form)
    except Exception:
        if os.environ.get("DVRA_DISPLAY_ERRORS") == "1":
            response = htt.text(traceback.format_exc(), status=500)
        else:
            response = htt.text("Internal server error", status=500)
    finally:
        conn.close()

    if session_data.get("_destroyed"):
        sess.destroy_session(sid)
        sess.attach_session_cookie(response, sid, clear=True)
    else:
        sess.save_session(sid, {k: v for k, v in session_data.items() if k != "_destroyed"})
        sess.attach_session_cookie(response, sid)
    return response
