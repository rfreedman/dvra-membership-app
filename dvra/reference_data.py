"""License classes and membership types."""

from __future__ import annotations

import sqlite3


class ReferenceDataRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _map_rows(self, rows: list[sqlite3.Row]) -> list[dict]:
        return [
            {"id": int(r["id"]), "name": str(r["name"]) if r["name"] is not None else None}
            for r in rows
        ]

    def list_license_classes(self) -> list[dict]:
        return self._map_rows(
            self.conn.execute("SELECT id, name FROM license_classes ORDER BY name ASC").fetchall()
        )

    def list_membership_types(self) -> list[dict]:
        return self._map_rows(
            self.conn.execute("SELECT id, name FROM membership_types ORDER BY name ASC").fetchall()
        )

    def create_license_class(self, name: str) -> None:
        self.conn.execute("INSERT INTO license_classes (name) VALUES (?)", (name.strip(),))
        self.conn.commit()

    def update_license_class(self, id_: int, name: str) -> None:
        self.conn.execute("UPDATE license_classes SET name = ? WHERE id = ?", (name.strip(), id_))
        self.conn.commit()

    def delete_license_class(self, id_: int) -> None:
        self.conn.execute("DELETE FROM license_classes WHERE id = ?", (id_,))
        self.conn.commit()

    def create_membership_type(self, name: str) -> None:
        self.conn.execute("INSERT INTO membership_types (name) VALUES (?)", (name.strip(),))
        self.conn.commit()

    def update_membership_type(self, id_: int, name: str) -> None:
        self.conn.execute("UPDATE membership_types SET name = ? WHERE id = ?", (name.strip(), id_))
        self.conn.commit()

    def membership_type_blocked_by_payments(self, membership_type_id: int, current_year: int) -> bool:
        row = self.conn.execute(
            """
            SELECT 1 FROM payments
             WHERE membership_type_id = ?
             AND (
               membership_year >= ?
               OR CAST(strftime('%Y', payment_date) AS INTEGER) >= ?
               OR CAST(strftime('%Y', paid_through) AS INTEGER) >= ?
             )
             LIMIT 1
            """,
            (membership_type_id, current_year, current_year, current_year),
        ).fetchone()
        return row is not None

    def delete_membership_type_or_fail(self, id_: int, current_year: int) -> None:
        if self.membership_type_blocked_by_payments(id_, current_year):
            raise RuntimeError(
                "Cannot delete membership type referenced by payments in the current or future membership years."
            )
        self.conn.execute("DELETE FROM membership_types WHERE id = ?", (id_,))
        self.conn.commit()
