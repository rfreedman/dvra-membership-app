"""Keyholders + year-scoped rosters + new members."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import Any

from dvra import join_extension
from dvra import membership_year as myear
from dvra.member_list import DATE_PAID_SUBQUERY
from dvra.sort_toggle import next_sort_choice, normalize_sort

KEYHOLDERS_SORT_FIELDS = ["name", "call_sign", "key_number", "email"]
NEW_MEMBERS_SORT_FIELDS = [
    "name",
    "call_sign",
    "license_class",
    "membership_type",
    "city",
    "state",
    "date_paid",
    "paid_through",
]


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


def default_new_members_since(today: date | None = None) -> str:
    d = today or date.today()
    return date(d.year, d.month, 1).isoformat()


def _optional_iso_date(text: str) -> str | None:
    if text == "":
        return None
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d")
        iso = parsed.strftime("%Y-%m-%d")
        return iso if iso == text else None
    except ValueError:
        return None


def parse_new_members_query(qp: dict[str, Any], *, today: date | None = None) -> dict[str, str]:
    raw = str(qp.get("since") or "").strip()
    since = _optional_iso_date(raw) or default_new_members_since(today)
    sort_by, sort_dir = normalize_sort(
        str(qp.get("sort_by", "name")).strip(),
        str(qp.get("sort_dir", "asc")).strip(),
        NEW_MEMBERS_SORT_FIELDS,
        "name",
    )
    return {"since": since, "sort_by": sort_by, "sort_dir": sort_dir}


def next_new_members_sort_choice(
    current_sort_by: str, current_sort_dir: str, clicked_field: str
) -> tuple[str, str]:
    return next_sort_choice(
        current_sort_by,
        current_sort_dir,
        clicked_field,
        desc_first=("date_paid", "paid_through"),
    )


def parse_year_memberships_query(qp: dict[str, Any], fallback_year: int) -> dict[str, Any]:
    year = myear.parse_year_input(qp.get("membership_year"), fallback_year)
    if year is None:
        year = fallback_year
    sort_by, sort_dir = normalize_sort(
        str(qp.get("sort_by", "name")).strip(),
        str(qp.get("sort_dir", "asc")).strip(),
        NEW_MEMBERS_SORT_FIELDS,
        "name",
    )
    return {"membership_year": year, "sort_by": sort_by, "sort_dir": sort_dir}


def sql_exists_paid_through_on(alias: str = "p") -> str:
    return f"""EXISTS (
        SELECT 1 FROM payments {alias}
        WHERE {alias}.member_id = m.id
          AND date({alias}.paid_through) = date(?)
    )"""


def sql_exists_paid_for_membership_year(alias: str = "p") -> str:
    """Payment covers Y-12-31 and membership_year is Y or Y-1 (late-join extension)."""
    return f"""EXISTS (
        SELECT 1 FROM payments {alias}
        WHERE {alias}.member_id = m.id
          AND {alias}.membership_year IN (?, ?)
          AND date({alias}.paid_through) >= date(?)
    )"""


_MEMBER_DETAIL_SELECT = f"""
            SELECT m.id AS id,
                   m.last_name AS last_name,
                   m.first_name AS first_name,
                   m.call_sign AS call_sign,
                   m.address_city AS address_city,
                   m.address_state AS address_state,
                   lc.name AS license_class,
                   mt.name AS membership_type,
                   {DATE_PAID_SUBQUERY} AS date_paid,
                   m.paid_through AS paid_through
            FROM members m
            LEFT JOIN license_classes lc ON m.license_class_id = lc.id
            LEFT JOIN membership_types mt ON m.membership_type_id = mt.id
"""


def _new_members_order_by(sort_by: str, sort_dir: str) -> str:
    d = "DESC" if sort_dir == "desc" else "ASC"
    tie = "m.last_name ASC, m.first_name ASC, m.id ASC"
    if sort_by == "call_sign":
        return f"(m.call_sign) IS NULL, m.call_sign {d}, {tie}"
    if sort_by == "license_class":
        return f"(lc.name) IS NULL, lc.name {d}, {tie}"
    if sort_by == "membership_type":
        return f"(mt.name) IS NULL, mt.name {d}, {tie}"
    if sort_by == "city":
        return f"(m.address_city) IS NULL, m.address_city {d}, {tie}"
    if sort_by == "state":
        return f"(m.address_state) IS NULL, m.address_state {d}, {tie}"
    if sort_by == "date_paid":
        return f"({DATE_PAID_SUBQUERY}) IS NULL, {DATE_PAID_SUBQUERY} {d}, {tie}"
    if sort_by == "paid_through":
        return f"(m.paid_through) IS NULL, m.paid_through {d}, {tie}"
    return f"m.last_name {d}, m.first_name {d}, m.id ASC"


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

    def list_new_members(
        self, since: str, sort_by: str = "name", sort_dir: str = "asc"
    ) -> list[dict]:
        parsed = parse_new_members_query({"sort_by": sort_by, "sort_dir": sort_dir, "since": since})
        where = f"""{DATE_PAID_SUBQUERY} IS NOT NULL
              AND date({DATE_PAID_SUBQUERY}) >= date(?)"""
        return self._list_member_detail_rows(where, (parsed["since"],), parsed["sort_by"], parsed["sort_dir"])

    def list_paid_memberships(
        self, membership_year: int, sort_by: str = "name", sort_dir: str = "asc"
    ) -> list[dict]:
        cutoff = myear.paid_through_iso(membership_year)
        where = sql_exists_paid_for_membership_year("pay")
        return self._list_member_detail_rows(
            where, (membership_year, membership_year - 1, cutoff), sort_by, sort_dir
        )

    def list_unpaid_memberships(
        self, membership_year: int, sort_by: str = "name", sort_dir: str = "asc"
    ) -> list[dict]:
        prior = myear.paid_through_iso(membership_year - 1)
        selected = myear.paid_through_iso(membership_year)
        where = (
            sql_exists_paid_through_on("prior_pay")
            + " AND NOT "
            + sql_exists_paid_for_membership_year("sel_pay")
        )
        return self._list_member_detail_rows(
            where,
            (prior, membership_year, membership_year - 1, selected),
            sort_by,
            sort_dir,
        )

    def _list_member_detail_rows(
        self, where_sql: str, bind: tuple[Any, ...], sort_by: str, sort_dir: str
    ) -> list[dict]:
        sort_by, sort_dir = normalize_sort(sort_by, sort_dir, NEW_MEMBERS_SORT_FIELDS, "name")
        order = _new_members_order_by(sort_by, sort_dir)
        rows = self.conn.execute(
            f"""
            {_MEMBER_DETAIL_SELECT}
            WHERE {where_sql}
            ORDER BY {order}
            """,
            bind,
        ).fetchall()
        return self._map_member_detail(rows)

    @staticmethod
    def _map_member_detail(rows: list[sqlite3.Row]) -> list[dict]:
        out = []
        for r in rows:
            cs = str(r["call_sign"]).upper().strip() if r["call_sign"] is not None else ""
            out.append(
                {
                    "id": int(r["id"]),
                    "last_name": str(r["last_name"] or ""),
                    "first_name": str(r["first_name"] or ""),
                    "call_sign": cs,
                    "license_class": str(r["license_class"] or "").strip(),
                    "membership_type": str(r["membership_type"] or "").strip(),
                    "city": str(r["address_city"] or ""),
                    "state": str(r["address_state"] or ""),
                    "date_paid": str(r["date_paid"] or ""),
                    "paid_through": str(r["paid_through"] or ""),
                }
            )
        return out

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
