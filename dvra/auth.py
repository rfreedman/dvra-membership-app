"""Login lookup and session roles (admin, manager, readonly)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import sqlite3

from dvra.passwords import verify_password

Role = Literal["admin", "manager", "readonly"]

ROLE_ADMIN: Role = "admin"
ROLE_MANAGER: Role = "manager"
ROLE_READONLY: Role = "readonly"


@dataclass(frozen=True)
class AuthUser:
    role: Role
    user_id: int
    username: str


def authenticate(conn: sqlite3.Connection, username: str, password: str) -> AuthUser | None:
    """Prefer admin_users, then managers, then readonly_users for the same username."""
    user = username.strip()
    if user == "" or password == "":
        return None
    admin = conn.execute(
        "SELECT id, password_hash FROM admin_users WHERE username = ? LIMIT 1",
        (user,),
    ).fetchone()
    if admin is not None and verify_password(password, str(admin["password_hash"])):
        return AuthUser(ROLE_ADMIN, int(admin["id"]), user)
    manager = conn.execute(
        "SELECT id, password_hash FROM managers WHERE username = ? LIMIT 1",
        (user,),
    ).fetchone()
    if manager is not None and verify_password(password, str(manager["password_hash"])):
        return AuthUser(ROLE_MANAGER, int(manager["id"]), user)
    readonly = conn.execute(
        "SELECT id, password_hash FROM readonly_users WHERE username = ? LIMIT 1",
        (user,),
    ).fetchone()
    if readonly is not None and verify_password(password, str(readonly["password_hash"])):
        return AuthUser(ROLE_READONLY, int(readonly["id"]), user)
    return None


def apply_login(session: dict[str, Any], user: AuthUser) -> None:
    session.clear()
    session["role"] = user.role
    session["user_id"] = user.user_id
    session["username"] = user.username


def is_logged_in(session: dict[str, Any]) -> bool:
    return current_role(session) is not None


def is_admin(session: dict[str, Any]) -> bool:
    return current_role(session) == ROLE_ADMIN


def is_read_only(session: dict[str, Any]) -> bool:
    return current_role(session) == ROLE_READONLY


def current_role(session: dict[str, Any]) -> Role | None:
    role = session.get("role")
    user_id = session.get("user_id")
    # Explicit non-admin roles always win (never elevate via legacy admin_id).
    if role == ROLE_MANAGER and user_id is not None:
        return ROLE_MANAGER
    if role == ROLE_READONLY and user_id is not None:
        return ROLE_READONLY
    if role == ROLE_ADMIN and user_id is not None:
        return ROLE_ADMIN
    # Pre-role sessions stored only admin_id (no role key).
    if role is None and session.get("admin_id") is not None:
        return ROLE_ADMIN
    return None


def is_admin_path(path: str) -> bool:
    return (
        path == "/admin"
        or path.startswith("/admin/")
        or path.startswith("/admins/")
        or path.startswith("/managers/")
        or path.startswith("/readonly-users/")
    )


def is_read_only_allowed(method: str, path: str) -> bool:
    """True when a read-only session may perform this request."""
    if method == "GET":
        return path != "/members/new"
    if method != "POST":
        return False
    return path in (
        "/",
        "/members/session-touch",
        "/reports/payments",
        "/reports/keyholders",
        "/reports/roster-by-name",
        "/reports/roster-by-callsign",
        "/reports/new-members",
        "/reports/paid-memberships",
        "/reports/unpaid-memberships",
    )
