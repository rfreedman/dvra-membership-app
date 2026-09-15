"""App settings (current membership year)."""

from __future__ import annotations

import sqlite3

from dvra import membership_year as myear


KEY_CURRENT_MEMBERSHIP_YEAR = "current_membership_year"


class AppSettingsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get_current_membership_year(self) -> int:
        row = self.conn.execute(
            "SELECT value FROM app_settings WHERE key = ? LIMIT 1",
            (KEY_CURRENT_MEMBERSHIP_YEAR,),
        ).fetchone()
        if row is None or row["value"] is None or str(row["value"]).strip() == "":
            return myear.calendar_year()
        parsed = myear.parse_year_input(row["value"])
        if parsed is None:
            return myear.calendar_year()
        return parsed

    def set_current_membership_year(self, year: int) -> None:
        if not myear.is_valid(year):
            raise ValueError("Invalid membership year.")
        self.conn.execute(
            """
            INSERT INTO app_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (KEY_CURRENT_MEMBERSHIP_YEAR, str(year)),
        )
        self.conn.commit()
