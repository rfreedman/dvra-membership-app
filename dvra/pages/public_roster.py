"""Public current-member roster for WordPress (JSON API + iframe embed)."""

from __future__ import annotations

from datetime import datetime, timezone

from dvra import db as dbmod
from dvra import http as htt
from dvra import schema
from dvra import view
from dvra.app_settings import AppSettingsRepository
from dvra.reports import ReportsRepository
from dvra.settings import Settings


def _cors_headers(origin: str) -> list[tuple[str, str]]:
    return [
        ("Access-Control-Allow-Origin", origin),
        ("Access-Control-Allow-Methods", "GET, OPTIONS"),
        ("Access-Control-Allow-Headers", "Accept, Content-Type"),
        ("Cache-Control", "public, max-age=300"),
    ]


def _apply_cors(response: htt.Response, origin: str) -> htt.Response:
    for name, value in _cors_headers(origin):
        response.set_header(name, value)
    return response


def handle_roster_options() -> htt.Response:
    settings = Settings.load()
    return _apply_cors(htt.empty(204), settings.roster_cors_origin)


def _roster_payload(conn) -> dict:
    year = AppSettingsRepository(conn).get_current_membership_year()
    repo = ReportsRepository(conn)
    return {
        "membership_year": year,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "by_name": repo.roster_by_name(year),
        "by_callsign": repo.roster_by_callsign(year),
    }


def handle_roster_json() -> htt.Response:
    settings = Settings.load()
    conn = dbmod.connect(settings)
    try:
        schema.ensure(conn)
        payload = _roster_payload(conn)
    finally:
        conn.close()
    return _apply_cors(htt.json_body(payload), settings.roster_cors_origin)


def handle_roster_embed() -> htt.Response:
    settings = Settings.load()
    conn = dbmod.connect(settings)
    try:
        schema.ensure(conn)
        payload = _roster_payload(conn)
    finally:
        conn.close()

    body = view.render(
        "public_roster_embed.html",
        membership_year=int(payload["membership_year"]),
        by_name=payload["by_name"],
        by_callsign=payload["by_callsign"],
    )
    return _apply_cors(htt.html(body), settings.roster_cors_origin)


def try_handle_public_roster(method: str, path: str) -> htt.Response | None:
    """Return a response for public roster paths, or None if not matched."""
    if path == "/api/roster":
        if method == "OPTIONS":
            return handle_roster_options()
        if method in ("GET", "HEAD"):
            return handle_roster_json()
        return htt.text("Method not allowed", status=405)
    if path == "/api/roster/embed":
        if method == "OPTIONS":
            return handle_roster_options()
        if method in ("GET", "HEAD"):
            return handle_roster_embed()
        return htt.text("Method not allowed", status=405)
    return None
