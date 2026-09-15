#!/usr/bin/env python3
"""Local development server (stdlib). Serves static files and the CGI app.

Pretty URLs (http://127.0.0.1:8089/login) work the same as CGI PATH_INFO
under index.py (http://127.0.0.1:8089/index.py/login).
"""

from __future__ import annotations

import argparse
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dvra.app import handle_request  # noqa: E402
from dvra.http import STATUS_TEXT  # noqa: E402
from dvra.paths import STATIC_DIR  # noqa: E402

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8089


def _split_cgi_path(path: str) -> tuple[str, str]:
    """Return (SCRIPT_NAME, PATH_INFO) for a request path without query string."""
    if path in ("", "/"):
        return "", "/"
    if path == "/index.py" or path.startswith("/index.py/"):
        rest = path[len("/index.py") :] or "/"
        if not rest.startswith("/"):
            rest = "/" + rest
        return "/index.py", rest
    return "", path


class DevHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def do_HEAD(self) -> None:
        self._handle()

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _handle(self) -> None:
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        if path.startswith("/static/"):
            self._serve_static(path)
            return
        if path in ("/favicon.ico",):
            icon = STATIC_DIR / "w2zq-site-icon-gold.png"
            if icon.is_file():
                self._send_file(icon, "image/png")
                return
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length > 0 else b""
        script_name, path_info = _split_cgi_path(path)

        env_keys = [
            "REQUEST_METHOD",
            "PATH_INFO",
            "SCRIPT_NAME",
            "QUERY_STRING",
            "CONTENT_TYPE",
            "CONTENT_LENGTH",
            "HTTP_COOKIE",
            "HTTPS",
        ]
        saved = {k: os.environ.get(k) for k in env_keys}
        try:
            os.environ["REQUEST_METHOD"] = self.command
            os.environ["PATH_INFO"] = path_info
            os.environ["SCRIPT_NAME"] = script_name
            os.environ["QUERY_STRING"] = parsed.query
            os.environ["CONTENT_TYPE"] = self.headers.get("Content-Type", "")
            os.environ["CONTENT_LENGTH"] = str(length)
            cookie = self.headers.get("Cookie", "")
            if cookie:
                os.environ["HTTP_COOKIE"] = cookie
            else:
                os.environ.pop("HTTP_COOKIE", None)
            os.environ.pop("HTTPS", None)
            response = handle_request(body)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        reason = STATUS_TEXT.get(response.status, "OK")
        self.send_response(response.status, reason)
        sent_type = False
        for name, value in response.headers:
            self.send_header(name, value)
            if name.lower() == "content-type":
                sent_type = True
        if not sent_type and response.body:
            self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(response.body)))
        self.end_headers()
        if self.command != "HEAD" and response.body:
            self.wfile.write(response.body)

    def _serve_static(self, path: str) -> None:
        rel = path[len("/static/") :]
        target = (STATIC_DIR / rel).resolve()
        try:
            target.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self.send_error(404)
            return
        if not target.is_file():
            self.send_error(404)
            return
        ctype = "application/octet-stream"
        if target.suffix == ".css":
            ctype = "text/css; charset=utf-8"
        elif target.suffix == ".png":
            ctype = "image/png"
        elif target.suffix == ".js":
            ctype = "text/javascript; charset=utf-8"
        self._send_file(target, ctype)

    def _send_file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DVRA Membership Manager locally.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), DevHandler)
    print(f"DVRA Membership Manager  http://{args.host}:{args.port}/", flush=True)
    print(f"Login: http://{args.host}:{args.port}/login   (CGI-style: /index.py/login)", flush=True)
    print("Ctrl+C to stop.", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
