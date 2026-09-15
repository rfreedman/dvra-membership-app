"""Login and logout handlers."""

from __future__ import annotations

from dvra import auth
from dvra import http as htt
from dvra import view
from dvra.context import RequestCtx
from dvra.pages.common import html_page, need_login


def handle_login_get(ctx: RequestCtx) -> htt.Response:
    if auth.is_logged_in(ctx["session"]):
        return htt.redirect(htt.url_for("/"), status=302)
    inner = view.render("login.html", error=None, base=htt.app_base())
    return html_page(inner, "Login", ctx)


def handle_login_post(ctx: RequestCtx) -> htt.Response:
    if auth.is_logged_in(ctx["session"]):
        return htt.redirect(htt.url_for("/"), status=302)
    form = ctx["form"]
    user = str(form.get("username") or "").strip()
    password = str(form.get("password") or "")
    found = auth.authenticate(ctx["conn"], user, password)
    if found is not None:
        auth.apply_login(ctx["session"], found)
        return htt.redirect(htt.url_for("/"), status=303)
    inner = view.render("login.html", error="Invalid username or password.", base=htt.app_base())
    return html_page(inner, "Login", ctx)


def handle_logout(ctx: RequestCtx) -> htt.Response:
    ctx["session"].clear()
    ctx["session"]["_destroyed"] = True
    return htt.redirect(htt.url_for("/login"), status=303)


def require_login(ctx: RequestCtx) -> htt.Response | None:
    if auth.is_logged_in(ctx["session"]):
        return None
    return need_login()


def require_admin(ctx: RequestCtx) -> htt.Response | None:
    if auth.is_admin(ctx["session"]):
        return None
    if auth.is_logged_in(ctx["session"]):
        return htt.redirect(htt.url_for("/"), status=303)
    return need_login()
