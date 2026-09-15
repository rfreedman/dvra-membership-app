"""Login lookup and session roles (admin vs manager)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import sqlite3

from dvra.passwords import verify_password

Role = Literal["admin", "manager"]

ROLE_ADMIN: Role = "admin"
ROLE_MANAGER: Role = "manager"


@dataclass(frozen=True)
class AuthUser:
    role: Role
    user_id: int
    username: str


def authenticate(conn: sqlite3.Connection, username: str, password: str) -> AuthUser | None:
    """Prefer admin_users when the same username exists in both tables."""
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


def current_role(session: dict[str, Any]) -> Role | None:
    role = session.get("role")
    user_id = session.get("user_id")
    # Explicit manager role always wins (never elevate via legacy admin_id).
    if role == ROLE_MANAGER and user_id is not None:
        return ROLE_MANAGER
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
    )
