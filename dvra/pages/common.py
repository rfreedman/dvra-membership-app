"""Shared HTML/export helpers for CGI page handlers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from dvra import auth
from dvra import http as htt
from dvra import view
from dvra.context import RequestCtx

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def html_page(
    inner: str,
    title: str,
    ctx: RequestCtx | None = None,
    *,
    extra_head: str = "",
    extra_scripts: str = "",
    status: int = 200,
    active_nav: str = "",
) -> htt.Response:
    session: dict[str, Any] = ctx["session"] if ctx is not None else {}
    body = view.wrap_html(
        inner,
        title,
        authenticated=auth.is_logged_in(session),
        is_admin=auth.is_admin(session),
        active_nav=active_nav,
        extra_head_html=extra_head,
        extra_scripts_html=extra_scripts,
    )
    return htt.html(body, status=status)


def need_login() -> htt.Response:
    return htt.redirect(htt.url_for("/login"), status=302)


def admin_redirect(error: str | None = None) -> htt.Response:
    loc = htt.url_for("/admin")
    if error:
        loc += "?error=" + quote(error)
    return htt.redirect(loc)


def ref_write_error(exc: Exception) -> str | None:
    msg = str(exc)
    if "UNIQUE constraint" in msg or "username already exists" in msg:
        return "That name already exists."
    if "FOREIGN KEY constraint" in msg:
        return "Cannot delete item while records still reference it."
    return None


def download_export(
    fmt: str,
    stem: str,
    *,
    csv_bytes: Callable[[], bytes],
    xlsx_bytes: Callable[[], bytes],
    pdf_bytes: Callable[[], bytes],
) -> htt.Response:
    if fmt == "csv":
        return htt.download(csv_bytes(), "text/csv; charset=utf-8", f"{stem}.csv")
    if fmt == "xlsx":
        return htt.download(xlsx_bytes(), XLSX_TYPE, f"{stem}.xlsx")
    if fmt == "pdf":
        return htt.download(pdf_bytes(), "application/pdf", f"{stem}.pdf")
    return htt.text("Not found", status=404)


def member_not_found(ctx: RequestCtx) -> htt.Response:
    return html_page(
        '<div class="standard-page-scroll"><p class="error">Member not found.</p></div>',
        "Not found",
        ctx,
        status=404,
        active_nav="members",
    )
