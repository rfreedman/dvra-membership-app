"""Admin and manager account CRUD."""

from __future__ import annotations

import sqlite3

from dvra.passwords import hash_password


class AdminAccountRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def list_admin_users(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, username FROM admin_users ORDER BY username ASC"
        ).fetchall()
        return [{"id": int(r["id"]), "username": str(r["username"])} for r in rows]

    def username_taken(self, username: str) -> bool:
        name = username.strip()
        if name == "":
            return False
        admin = self.conn.execute(
            "SELECT 1 FROM admin_users WHERE username = ? LIMIT 1", (name,)
        ).fetchone()
        if admin is not None:
            return True
        manager = self.conn.execute(
            "SELECT 1 FROM managers WHERE username = ? LIMIT 1", (name,)
        ).fetchone()
        return manager is not None

    def create_admin_user(self, username: str, raw_password: str) -> None:
        if self.username_taken(username):
            raise sqlite3.IntegrityError("username already exists")
        self.conn.execute(
            "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
            (username.strip(), hash_password(raw_password)),
        )
        self.conn.commit()

    def update_admin_password(self, user_id: int, raw_password: str) -> None:
        self.conn.execute(
            "UPDATE admin_users SET password_hash = ? WHERE id = ?",
            (hash_password(raw_password), user_id),
        )
        self.conn.commit()

    def delete_admin_user_or_fail(self, user_id: int) -> None:
        cnt = int(self.conn.execute("SELECT COUNT(*) FROM admin_users").fetchone()[0])
        if cnt <= 1:
            raise RuntimeError("Cannot delete the only administrator account.")
        self.conn.execute("DELETE FROM admin_users WHERE id = ?", (user_id,))
        self.conn.commit()

    def list_managers(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, username, display_name FROM managers ORDER BY username ASC"
        ).fetchall()
        out = []
        for r in rows:
            dn = r["display_name"]
            out.append(
                {
                    "id": int(r["id"]),
                    "username": str(r["username"]),
                    "display_name": str(dn) if dn else None,
                }
            )
        return out

    def create_manager(self, username: str, raw_password: str, display_name: str | None) -> None:
        if self.username_taken(username):
            raise sqlite3.IntegrityError("username already exists")
        dn = display_name.strip() if display_name and display_name.strip() else None
        self.conn.execute(
            "INSERT INTO managers (username, password_hash, display_name) VALUES (?, ?, ?)",
            (username.strip(), hash_password(raw_password), dn),
        )
        self.conn.commit()

    def update_manager_password(self, manager_id: int, raw_password: str) -> None:
        self.conn.execute(
            "UPDATE managers SET password_hash = ? WHERE id = ?",
            (hash_password(raw_password), manager_id),
        )
        self.conn.commit()

    def update_manager_profile(self, manager_id: int, display_name: str | None) -> None:
        dn = display_name.strip() if display_name and display_name.strip() else None
        self.conn.execute(
            "UPDATE managers SET display_name = ? WHERE id = ?",
            (dn, manager_id),
        )
        self.conn.commit()

    def delete_manager(self, manager_id: int) -> None:
        self.conn.execute("DELETE FROM managers WHERE id = ?", (manager_id,))
        self.conn.commit()
