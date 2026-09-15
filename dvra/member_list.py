"""Members list query + filter (year-scoped current members)."""

from __future__ import annotations

import html
import json
import sqlite3
from typing import Any

from dvra import membership_year as myear
from dvra.http import url_for

SORT_FIELDS = [
    "last_name",
    "first_name",
    "call_sign",
    "email",
    "phone",
    "address_street",
    "address_city",
    "address_state",
    "address_zip",
    "license_class",
    "membership_type",
    "arrl_member",
    "paid_through",
]


def parse_list_query(qp: dict[str, Any]) -> dict[str, Any]:
    search = str(qp.get("search", "")).strip() if qp.get("search") is not None else ""
    sort_by_raw = str(qp.get("sort_by", "last_name"))
    sort_dir_raw = str(qp.get("sort_dir", "asc"))
    sort_by, sort_dir = _normalize_sort(sort_by_raw, sort_dir_raw)

    mid_raw = qp.get("membership_type_id", "")
    membership_type_id = None
    if mid_raw is not None and not isinstance(mid_raw, (list, dict)):
        t = str(mid_raw).strip()
        if t != "":
            try:
                membership_type_id = int(t)
            except ValueError:
                membership_type_id = None

    arrl = str(qp.get("arrl", "")).strip() if qp.get("arrl") is not None else ""
    co = qp.get("current_only")
    if isinstance(co, (list, tuple)):
        co = co[-1] if co else "yes"
    current_only = str(co) if co not in (None, "") else "yes"
    if current_only not in ("yes", "no"):
        current_only = "yes"

    return {
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "search": search,
        "membership_type_id": membership_type_id,
        "arrl": arrl if arrl in ("yes", "no") else "",
        "current_only": current_only,
        "membership_year": myear.parse_year_input(qp.get("membership_year")),
    }


def list_params_to_query_input(p: dict[str, Any]) -> dict[str, Any]:
    q: dict[str, Any] = {
        "sort_by": p["sort_by"],
        "sort_dir": p["sort_dir"],
        "current_only": p["current_only"],
        "search": p["search"],
        "arrl": p["arrl"],
    }
    if p.get("membership_type_id") is not None:
        q["membership_type_id"] = p["membership_type_id"]
    if p.get("membership_year") is not None:
        q["membership_year"] = int(p["membership_year"])
    return q


def _escape_like(needle: str) -> str:
    return needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _normalize_sort(sort_by: str, sort_dir: str) -> tuple[str, str]:
    sb = sort_by if sort_by in SORT_FIELDS else "last_name"
    sd = "desc" if sort_dir.lower() == "desc" else "asc"
    return sb, sd


def _order_by_sql(sort_by: str, sort_dir: str) -> str:
    desc = sort_dir == "desc"
    direction = "DESC" if desc else "ASC"
    tail = ", m.id ASC"
    mapping = {
        "last_name": f"m.last_name {direction}{tail}",
        "first_name": f"m.first_name {direction}{tail}",
        "call_sign": f"(m.call_sign) IS NULL, m.call_sign {direction}{tail}",
        "email": f"(m.email) IS NULL, m.email {direction}{tail}",
        "phone": f"(m.phone) IS NULL, m.phone {direction}{tail}",
        "address_street": f"(m.address_street) IS NULL, m.address_street {direction}{tail}",
        "address_city": f"(m.address_city) IS NULL, m.address_city {direction}{tail}",
        "address_state": f"(m.address_state) IS NULL, m.address_state {direction}{tail}",
        "address_zip": f"(m.address_zip) IS NULL, m.address_zip {direction}{tail}",
        "paid_through": f"(m.paid_through) IS NULL, m.paid_through {direction}{tail}",
        "membership_type": f"(mt.name) IS NULL, mt.name {direction}{tail}",
        "license_class": f"(lc.name) IS NULL, lc.name {direction}{tail}",
        "arrl_member": f"m.arrl_member {direction}{tail}",
    }
    return mapping.get(sort_by, f"m.last_name {direction}{tail}")


def _filter_clause(f: dict[str, Any]) -> tuple[str, list]:
    parts = ["1 = 1"]
    bind: list = []
    search = f.get("search") or ""
    if search:
        needle = "%" + _escape_like(search) + "%"
        like_cols = [
            "COALESCE(m.last_name, '')",
            "COALESCE(m.first_name, '')",
            "COALESCE(m.call_sign, '')",
            "COALESCE(m.email, '')",
        ]
        sub = []
        for expr in like_cols:
            sub.append(f"LOWER({expr}) LIKE LOWER(?) ESCAPE '\\'")
            bind.append(needle)
        parts.append("(" + " OR ".join(sub) + ")")
    mtid = f.get("membership_type_id")
    if mtid is not None:
        parts.append("m.membership_type_id = ?")
        bind.append(mtid)
    arrl = f.get("arrl") or ""
    if arrl == "yes":
        parts.append("m.arrl_member = 1")
    elif arrl == "no":
        parts.append("m.arrl_member = 0")
    current_only_flag = str(f.get("current_only") or "yes").strip().lower()
    if current_only_flag != "no":
        year = int(f.get("membership_year") or 0)
        parts.append(
            """EXISTS (
                SELECT 1 FROM payments pay
                WHERE pay.member_id = m.id AND pay.membership_year = ?
            )"""
        )
        bind.append(year)
    return " AND ".join(parts), bind


class MemberListRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def list_membership_types(self) -> list[dict]:
        rows = self.conn.execute("SELECT id, name FROM membership_types ORDER BY name ASC").fetchall()
        return [{"id": int(r["id"]), "name": str(r["name"]) if r["name"] is not None else None} for r in rows]

    def count_members(self, f: dict[str, Any]) -> int:
        where, bind = _filter_clause(f)
        row = self.conn.execute(f"SELECT COUNT(*) FROM members m WHERE {where}", bind).fetchone()
        return int(row[0])

    def list_rows_for_tabulator(self, p: dict[str, Any]) -> list[dict]:
        rows = self._fetch_filtered(p)
        out = []
        for r in rows:
            mapped = self._map_joined(r)
            mapped["actions_html"] = _actions_html(int(r["id"]))
            out.append(mapped)
        return out

    def list_rows_for_export(self, p: dict[str, Any]) -> list[dict]:
        return [self._map_joined(r) for r in self._fetch_filtered(p)]

    def _fetch_filtered(self, p: dict[str, Any]) -> list:
        where, bind = _filter_clause(
            {
                "search": p["search"],
                "membership_type_id": p["membership_type_id"],
                "arrl": p["arrl"],
                "current_only": p["current_only"],
                "membership_year": p["membership_year"],
            }
        )
        order = _order_by_sql(p["sort_by"], p["sort_dir"])
        sql = f"""
            SELECT m.id AS id,
                   m.last_name AS last_name,
                   m.first_name AS first_name,
                   m.call_sign AS call_sign,
                   m.email AS email,
                   m.phone AS phone,
                   m.address_street AS address_street,
                   m.address_city AS address_city,
                   m.address_state AS address_state,
                   m.address_zip AS address_zip,
                   m.arrl_member AS arrl_member,
                   m.key_number AS key_number,
                   m.paid_through AS paid_through,
                   lc.name AS lc_name,
                   mt.name AS mt_name
            FROM members m
            LEFT JOIN license_classes lc ON m.license_class_id = lc.id
            LEFT JOIN membership_types mt ON m.membership_type_id = mt.id
            WHERE {where}
            ORDER BY {order}
        """
        return self.conn.execute(sql, bind).fetchall()

    @staticmethod
    def _map_joined(r) -> dict:
        call = str(r["call_sign"]) if r["call_sign"] is not None else ""
        return {
            "id": int(r["id"]),
            "call_sign": call.upper().strip(),
            "last_name": str(r["last_name"] or ""),
            "first_name": str(r["first_name"] or ""),
            "email": str(r["email"] or ""),
            "phone": str(r["phone"] or ""),
            "address_street": str(r["address_street"] or ""),
            "address_city": str(r["address_city"] or ""),
            "address_state": str(r["address_state"] or ""),
            "address_zip": str(r["address_zip"] or ""),
            "license_class": str(r["lc_name"] or "").strip(),
            "membership_type": str(r["mt_name"] or "").strip(),
            "arrl_member": bool(r["arrl_member"]),
            "key_number": int(r["key_number"]) if r["key_number"] is not None else None,
            "paid_through": str(r["paid_through"] or ""),
        }


def tabulator_json_from_rows(rows: list[dict]) -> str:
    return json.dumps(rows, ensure_ascii=False)


def _actions_html(member_id: int) -> str:
    view = html.escape(url_for(f"/members/{member_id}/view"), quote=True)
    pay = html.escape(url_for(f"/members/{member_id}/payments"), quote=True)
    return f'<a href="{view}">Edit</a><span aria-hidden="true"> · </span><a href="{pay}">Payments</a>'
