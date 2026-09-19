"""App settings (current membership year, late-join thresholds)."""

from __future__ import annotations

import sqlite3

from dvra import join_extension
from dvra import membership_year as myear

KEY_CURRENT_MEMBERSHIP_YEAR = "current_membership_year"
KEY_NEW_MEMBER_EXTENSION_START = "new_member_extension_start"
KEY_NEW_HAM_EXTENSION_START = "new_ham_extension_start"

DEFAULT_NEW_MEMBER_EXTENSION_START = "08-01"
DEFAULT_NEW_HAM_EXTENSION_START = "11-01"


class AppSettingsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _get_raw(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM app_settings WHERE key = ? LIMIT 1",
            (key,),
        ).fetchone()
        if row is None or row["value"] is None:
            return None
        text = str(row["value"]).strip()
        return text if text else None

    def _set_raw(self, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO app_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        self.conn.commit()

    def get_current_membership_year(self) -> int:
        raw = self._get_raw(KEY_CURRENT_MEMBERSHIP_YEAR)
        if raw is None:
            return myear.calendar_year()
        parsed = myear.parse_year_input(raw)
        if parsed is None:
            return myear.calendar_year()
        return parsed

    def set_current_membership_year(self, year: int) -> None:
        if not myear.is_valid(year):
            raise ValueError("Invalid membership year.")
        self._set_raw(KEY_CURRENT_MEMBERSHIP_YEAR, str(year))

    def get_new_member_extension_start(self) -> str:
        raw = self._get_raw(KEY_NEW_MEMBER_EXTENSION_START)
        if raw is None:
            return DEFAULT_NEW_MEMBER_EXTENSION_START
        try:
            m, d = join_extension.parse_threshold_mmdd(raw)
        except ValueError:
            return DEFAULT_NEW_MEMBER_EXTENSION_START
        return join_extension.format_threshold_mmdd(m, d)

    def set_new_member_extension_start(self, mm_dd: str) -> None:
        m, d = join_extension.parse_threshold_mmdd(mm_dd)
        self._set_raw(KEY_NEW_MEMBER_EXTENSION_START, join_extension.format_threshold_mmdd(m, d))

    def get_new_ham_extension_start(self) -> str:
        raw = self._get_raw(KEY_NEW_HAM_EXTENSION_START)
        if raw is None:
            return DEFAULT_NEW_HAM_EXTENSION_START
        try:
            m, d = join_extension.parse_threshold_mmdd(raw)
        except ValueError:
            return DEFAULT_NEW_HAM_EXTENSION_START
        return join_extension.format_threshold_mmdd(m, d)

    def set_new_ham_extension_start(self, mm_dd: str) -> None:
        m, d = join_extension.parse_threshold_mmdd(mm_dd)
        self._set_raw(KEY_NEW_HAM_EXTENSION_START, join_extension.format_threshold_mmdd(m, d))
