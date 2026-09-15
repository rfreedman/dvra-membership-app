"""Serve files from static/ when CGI receives PATH_INFO under /static/."""

from __future__ import annotations

from pathlib import Path

from dvra import http as htt
from dvra.paths import STATIC_DIR

_CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".svg": "image/svg+xml",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


def serve_static(path_info: str) -> htt.Response:
    """Return a Response for PATH_INFO like /static/style.css, or 404."""
    raw = path_info
    if not raw.startswith("/static/"):
        return htt.text("Not found", status=404)
    rel = raw[len("/static/") :]
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        return htt.text("Not found", status=404)
    target = (STATIC_DIR / rel).resolve()
    try:
        target.relative_to(STATIC_DIR.resolve())
    except ValueError:
        return htt.text("Not found", status=404)
    if not target.is_file():
        return htt.text("Not found", status=404)
    ctype = _CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
    body = target.read_bytes()
    r = htt.Response(status=200, body=body)
    r.set_header("Content-Type", ctype)
    r.set_header("Content-Length", str(len(body)))
    r.set_header("Cache-Control", "public, max-age=3600")
    return r
