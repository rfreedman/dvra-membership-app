"""Keyholders + year-scoped rosters."""

from __future__ import annotations

import sqlite3
from typing import Any

from dvra import join_extension
from dvra.sort_toggle import next_sort_choice, normalize_sort

KEYHOLDERS_SORT_FIELDS = ["name", "call_sign", "key_number", "email"]


def parse_keyholders_query(qp: dict[str, Any]) -> dict[str, str]:
    sort_by, sort_dir = normalize_sort(
        str(qp.get("sort_by", "name")).strip(),
        str(qp.get("sort_dir", "asc")).strip(),
        KEYHOLDERS_SORT_FIELDS,
        "name",
    )
    return {"sort_by": sort_by, "sort_dir": sort_dir}


def next_keyholders_sort_choice(current_sort_by: str, current_sort_dir: str, clicked_field: str) -> tuple[str, str]:
    return next_sort_choice(current_sort_by, current_sort_dir, clicked_field)


def _keyholders_order_by(sort_by: str, sort_dir: str) -> str:
    d = "DESC" if sort_dir == "desc" else "ASC"
    tie = "m.last_name ASC, m.first_name ASC, m.id ASC"
    if sort_by == "call_sign":
        return f"(m.call_sign) IS NULL, m.call_sign {d}, {tie}"
    if sort_by == "key_number":
        return f"m.key_number {d}, {tie}"
    if sort_by == "email":
        return f"(m.email IS NULL OR trim(coalesce(m.email, '')) = ''), m.email COLLATE NOCASE {d}, {tie}"
    return f"m.last_name {d}, m.first_name {d}, m.id ASC"


class ReportsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def list_keyholders(self, sort_by: str = "name", sort_dir: str = "asc") -> list[dict]:
        parsed = parse_keyholders_query({"sort_by": sort_by, "sort_dir": sort_dir})
        order = _keyholders_order_by(parsed["sort_by"], parsed["sort_dir"])
        rows = self.conn.execute(
            f"""
            SELECT m.id AS id, m.key_number AS key_number, m.call_sign AS call_sign,
                   m.last_name AS last_name, m.first_name AS first_name, m.email AS email
            FROM members m
            WHERE m.key_number IS NOT NULL
            ORDER BY {order}
            """
        ).fetchall()
        out = []
        for r in rows:
            cs = str(r["call_sign"]).upper().strip() if r["call_sign"] is not None else ""
            out.append(
                {
                    "id": int(r["id"]),
                    "key_number": int(r["key_number"]),
                    "call_sign": cs,
                    "last_name": str(r["last_name"] or ""),
                    "first_name": str(r["first_name"] or ""),
                    "email": str(r["email"] or ""),
                }
            )
        return out

    def roster_by_name(self, membership_year: int) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT m.last_name AS last_name, m.first_name AS first_name, m.call_sign AS call_sign
            FROM members m
            WHERE """
            + join_extension.sql_exists_payment_current_for_year("p")
            + """
            ORDER BY m.last_name ASC, m.first_name ASC
            """,
            (membership_year, membership_year),
        ).fetchall()
        return self._map_roster(rows)

    def roster_by_callsign(self, membership_year: int) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT m.call_sign AS call_sign, m.last_name AS last_name, m.first_name AS first_name
            FROM members m
            WHERE """
            + join_extension.sql_exists_payment_current_for_year("p")
            + """
            ORDER BY (m.call_sign IS NULL), m.call_sign ASC, m.last_name ASC, m.first_name ASC
            """,
            (membership_year, membership_year),
        ).fetchall()
        return self._map_roster(rows)

    @staticmethod
    def _map_roster(rows: list[sqlite3.Row]) -> list[dict]:
        out = []
        for r in rows:
            cs = str(r["call_sign"]).upper().strip() if r["call_sign"] is not None else ""
            out.append(
                {
                    "last_name": str(r["last_name"] or ""),
                    "first_name": str(r["first_name"] or ""),
                    "call_sign": cs,
                }
            )
        return out
