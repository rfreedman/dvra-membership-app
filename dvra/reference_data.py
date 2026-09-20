"""License classes and membership types."""

from __future__ import annotations

import sqlite3

from dvra.new_ham import CANNOT_DELETE_NEW_HAM, CANNOT_RENAME_NEW_HAM, is_protected_type_id

DEFAULT_MEMBERSHIP_TYPE_NAME = "Individual"

HIDDEN_LICENSE_CLASS = "That license class is hidden and cannot be newly attached."
HIDDEN_MEMBERSHIP_TYPE = "That membership type is hidden and cannot be newly attached."
CANNOT_DELETE_REFERENCED_LICENSE = (
    "Cannot delete a license class that is used by members. Hide it instead."
)
CANNOT_DELETE_REFERENCED_TYPE = (
    "Cannot delete a membership type that is still in use. Hide it instead."
)

_REFERENCE_TABLES = frozenset({"license_classes", "membership_types"})


def find_default_membership_type_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute(
        """
        SELECT id FROM membership_types
         WHERE name = ? AND COALESCE(hidden, 0) = 0
         LIMIT 1
        """,
        (DEFAULT_MEMBERSHIP_TYPE_NAME,),
    ).fetchone()
    if row is None:
        return None
    return int(row[0])


class ReferenceDataRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _map_rows(self, rows: list[sqlite3.Row]) -> list[dict]:
        out: list[dict] = []
        for r in rows:
            hidden = 0
            try:
                hidden = int(r["hidden"] or 0)
            except (IndexError, KeyError):
                hidden = 0
            out.append(
                {
                    "id": int(r["id"]),
                    "name": str(r["name"]) if r["name"] is not None else None,
                    "hidden": bool(hidden),
                }
            )
        return out

    def _list_rows(
        self,
        table: str,
        *,
        include_hidden: bool,
        include_ids: list[int] | None,
    ) -> list[dict]:
        if table not in _REFERENCE_TABLES:
            raise ValueError(f"Unknown reference table: {table}")
        extra_ids: list[int] = []
        for raw in include_ids or []:
            if raw is None:
                continue
            extra_ids.append(int(raw))
        if include_hidden:
            sql = f"SELECT id, name, hidden FROM {table} ORDER BY name ASC"
            rows = self.conn.execute(sql).fetchall()
        elif extra_ids:
            placeholders = ",".join("?" * len(extra_ids))
            sql = (
                f"SELECT id, name, hidden FROM {table} "
                f"WHERE COALESCE(hidden, 0) = 0 OR id IN ({placeholders}) "
                f"ORDER BY name ASC"
            )
            rows = self.conn.execute(sql, extra_ids).fetchall()
        else:
            sql = (
                f"SELECT id, name, hidden FROM {table} "
                f"WHERE COALESCE(hidden, 0) = 0 ORDER BY name ASC"
            )
            rows = self.conn.execute(sql).fetchall()
        return self._map_rows(rows)

    def list_license_classes(
        self,
        *,
        include_hidden: bool = True,
        include_ids: list[int] | None = None,
    ) -> list[dict]:
        return self._list_rows(
            "license_classes", include_hidden=include_hidden, include_ids=include_ids
        )

    def list_membership_types(
        self,
        *,
        include_hidden: bool = True,
        include_ids: list[int] | None = None,
    ) -> list[dict]:
        return self._list_rows(
            "membership_types", include_hidden=include_hidden, include_ids=include_ids
        )

    def create_license_class(self, name: str) -> None:
        self.conn.execute("INSERT INTO license_classes (name) VALUES (?)", (name.strip(),))
        self.conn.commit()

    def update_license_class(self, id_: int, name: str) -> None:
        self.conn.execute("UPDATE license_classes SET name = ? WHERE id = ?", (name.strip(), id_))
        self.conn.commit()

    def license_class_is_referenced(self, id_: int) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM members WHERE license_class_id = ? LIMIT 1",
            (id_,),
        ).fetchone()
        return row is not None

    def set_license_class_hidden(self, id_: int, hidden: bool) -> None:
        self.conn.execute(
            "UPDATE license_classes SET hidden = ? WHERE id = ?",
            (1 if hidden else 0, id_),
        )
        self.conn.commit()

    def is_hidden_license_class(self, id_: int | None) -> bool:
        if id_ is None:
            return False
        row = self.conn.execute(
            "SELECT hidden FROM license_classes WHERE id = ?",
            (int(id_),),
        ).fetchone()
        return row is not None and bool(int(row["hidden"] or 0))

    def delete_license_class_or_fail(self, id_: int) -> None:
        if self.license_class_is_referenced(id_):
            raise RuntimeError(CANNOT_DELETE_REFERENCED_LICENSE)
        self.conn.execute("DELETE FROM license_classes WHERE id = ?", (id_,))
        self.conn.commit()

    def create_membership_type(self, name: str) -> None:
        self.conn.execute("INSERT INTO membership_types (name) VALUES (?)", (name.strip(),))
        self.conn.commit()

    def update_membership_type(self, id_: int, name: str) -> None:
        if is_protected_type_id(self.conn, id_):
            raise RuntimeError(CANNOT_RENAME_NEW_HAM)
        self.conn.execute("UPDATE membership_types SET name = ? WHERE id = ?", (name.strip(), id_))
        self.conn.commit()

    def membership_type_is_referenced(self, id_: int) -> bool:
        member_row = self.conn.execute(
            "SELECT 1 FROM members WHERE membership_type_id = ? LIMIT 1",
            (id_,),
        ).fetchone()
        if member_row is not None:
            return True
        # Payments store their own type; deleting would SET NULL and hide history.
        payment_row = self.conn.execute(
            "SELECT 1 FROM payments WHERE membership_type_id = ? LIMIT 1",
            (id_,),
        ).fetchone()
        return payment_row is not None

    def set_membership_type_hidden(self, id_: int, hidden: bool) -> None:
        self.conn.execute(
            "UPDATE membership_types SET hidden = ? WHERE id = ?",
            (1 if hidden else 0, id_),
        )
        self.conn.commit()

    def is_hidden_membership_type(self, id_: int | None) -> bool:
        if id_ is None:
            return False
        row = self.conn.execute(
            "SELECT hidden FROM membership_types WHERE id = ?",
            (int(id_),),
        ).fetchone()
        return row is not None and bool(int(row["hidden"] or 0))

    def hidden_membership_type_attach_error(
        self,
        membership_type_id: int | None,
        *,
        existing_id: int | None = None,
    ) -> str | None:
        if membership_type_id is None:
            return None
        if existing_id is not None and int(membership_type_id) == int(existing_id):
            return None
        if self.is_hidden_membership_type(membership_type_id):
            return HIDDEN_MEMBERSHIP_TYPE
        return None

    def delete_membership_type_or_fail(self, id_: int) -> None:
        if is_protected_type_id(self.conn, id_):
            raise RuntimeError(CANNOT_DELETE_NEW_HAM)
        if self.membership_type_is_referenced(id_):
            raise RuntimeError(CANNOT_DELETE_REFERENCED_TYPE)
        self.conn.execute("DELETE FROM membership_types WHERE id = ?", (id_,))
        self.conn.commit()
