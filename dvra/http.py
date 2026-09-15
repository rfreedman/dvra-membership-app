"""CGI request/response helpers (stdlib only; not a web framework)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from email.parser import BytesParser
from email.policy import default as email_default
from typing import Any
from urllib.parse import parse_qs, unquote


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def request_method() -> str:
    return env("REQUEST_METHOD", "GET").upper()


def script_name() -> str:
    return env("SCRIPT_NAME", "")


def path_info() -> str:
    raw = env("PATH_INFO", "")
    if raw == "":
        return "/"
    if not raw.startswith("/"):
        return "/" + raw
    return raw


def app_base() -> str:
    """Prefix for app URLs. Empty when SCRIPT_NAME is / or blank (pretty host mapping)."""
    name = script_name().rstrip("/")
    if name in ("", "/"):
        return ""
    return name


def url_for(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    base = app_base()
    if path == "/":
        return base + "/" if base else "/"
    return base + path


def query_params() -> dict[str, list[str]]:
    return parse_qs(env("QUERY_STRING", ""), keep_blank_values=True)


def cookie_header() -> str:
    return env("HTTP_COOKIE", "")


def parse_cookies(header: str | None = None) -> dict[str, str]:
    raw = cookie_header() if header is None else header
    out: dict[str, str] = {}
    if not raw:
        return out
    for part in raw.split(";"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip()] = unquote(v.strip())
    return out


def read_body() -> bytes:
    try:
        length = int(env("CONTENT_LENGTH", "0") or "0")
    except ValueError:
        length = 0
    if length <= 0:
        return b""
    return sys.stdin.buffer.read(length)


def parse_form(body: bytes | None = None) -> dict[str, Any]:
    method = request_method()
    if method not in ("POST", "PUT", "PATCH"):
        return {}
    raw = read_body() if body is None else body
    ctype = env("CONTENT_TYPE", "")
    if "multipart/form-data" in ctype.lower():
        return _parse_multipart(raw, ctype)
    text = raw.decode("utf-8", errors="replace")
    parsed = parse_qs(text, keep_blank_values=True)
    return {k: v[-1] if len(v) == 1 else v for k, v in parsed.items()}


def _parse_multipart(body: bytes, content_type: str) -> dict[str, Any]:
    header = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n"
    msg = BytesParser(policy=email_default).parsebytes(header.encode("utf-8") + body)
    out: dict[str, Any] = {}
    if not msg.is_multipart():
        return out
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            value = str(part.get_content())
        else:
            charset = part.get_content_charset() or "utf-8"
            value = payload.decode(charset, errors="replace")
        if name in out:
            existing = out[name]
            if isinstance(existing, list):
                existing.append(value)
            else:
                out[name] = [existing, value]
        else:
            out[name] = value
    return out


@dataclass
class Response:
    status: int = 200
    headers: list[tuple[str, str]] = field(default_factory=list)
    body: bytes = b""

    def set_header(self, name: str, value: str) -> None:
        self.headers = [(n, v) for n, v in self.headers if n.lower() != name.lower()]
        self.headers.append((name, value))

    def add_header(self, name: str, value: str) -> None:
        self.headers.append((name, value))


STATUS_TEXT = {
    200: "OK",
    204: "No Content",
    302: "Found",
    303: "See Other",
    400: "Bad Request",
    404: "Not Found",
    409: "Conflict",
    500: "Internal Server Error",
}


def html(body: str, status: int = 200, extra_headers: list[tuple[str, str]] | None = None) -> Response:
    r = Response(status=status, body=body.encode("utf-8"))
    r.set_header("Content-Type", "text/html; charset=utf-8")
    for n, v in extra_headers or []:
        r.add_header(n, v)
    return r


def text(body: str, status: int = 200, content_type: str = "text/plain; charset=utf-8") -> Response:
    r = Response(status=status, body=body.encode("utf-8"))
    r.set_header("Content-Type", content_type)
    return r


def empty(status: int = 204) -> Response:
    return Response(status=status, body=b"")


def redirect(location: str, status: int = 303) -> Response:
    r = Response(status=status, body=b"")
    r.set_header("Location", location)
    return r


def download(payload: bytes, content_type: str, filename: str) -> Response:
    safe = filename.replace('"', "").replace("\\", "")
    r = Response(status=200, body=payload)
    r.set_header("Content-Type", content_type)
    r.set_header("Content-Disposition", f'attachment; filename="{safe}"')
    return r


def write_cgi(response: Response) -> None:
    reason = STATUS_TEXT.get(response.status, "OK")
    sys.stdout.write(f"Status: {response.status} {reason}\r\n")
    has_type = any(n.lower() == "content-type" for n, _ in response.headers)
    if not has_type and response.body:
        sys.stdout.write("Content-Type: text/plain; charset=utf-8\r\n")
    for name, value in response.headers:
        sys.stdout.write(f"{name}: {value}\r\n")
    sys.stdout.write("\r\n")
    sys.stdout.flush()
    if response.body:
        sys.stdout.buffer.write(response.body)
        sys.stdout.buffer.flush()
