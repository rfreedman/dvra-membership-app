"""Jinja2 templates."""

from __future__ import annotations

from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from dvra.http import app_base, url_for
from dvra.paths import TEMPLATE_DIR

_env: Environment | None = None


def env() -> Environment:
    global _env
    if _env is None:
        _env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
        )
        _env.globals["url_for"] = url_for
    return _env


def render(name: str, **data: Any) -> str:
    return env().get_template(name).render(**data)


def wrap_html(
    content_html: str,
    title: str,
    *,
    authenticated: bool = False,
    active_nav: str = "",
    extra_head_html: str = "",
    extra_scripts_html: str = "",
    is_admin: bool = False,
) -> str:
    return render(
        "layout.html",
        title=title,
        content_html=content_html,
        authenticated=authenticated,
        is_admin=is_admin,
        active_nav=active_nav,
        extra_head_html=extra_head_html,
        extra_scripts_html=extra_scripts_html,
        base=app_base(),
    )
