"""Payment report query."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from dvra import membership_year as myear
from dvra import normalizer
from dvra.sort_toggle import next_sort_choice as _next_sort_choice
from dvra.sort_toggle import normalize_sort

ORDER_SQL_REPORT_DEFAULT_BASE = (
    "m.last_name ASC, m.first_name ASC, (p.paid_through) IS NULL ASC, p.paid_through DESC"
)
SORT_FIELDS = [
    "report_default",
    "member_name",
    "member_id",
    "call_sign",
    "payment_date",
    "paid_through",
    "membership_year",
    "membership_type",
    "form_number",
]


def _scalar(qp: dict[str, Any], key: str) -> str:
    v = qp.get(key, "")
    if isinstance(v, (list, tuple)):
        v = v[-1] if v else ""
    return str(v).strip() if v is not None and not isinstance(v, dict) else ""


def _optional_iso_date(text: str) -> str | None:
    if text == "":
        return None
    try:
        d = datetime.strptime(text, "%Y-%m-%d")
        return d.strftime("%Y-%m-%d") if d.strftime("%Y-%m-%d") == text else None
    except ValueError:
        return None


def _normalize_sort(sort_by: str, sort_dir: str) -> tuple[str, str]:
    return normalize_sort(sort_by, sort_dir, SORT_FIELDS, "report_default")


def parse_payment_report_query(qp: dict[str, Any]) -> dict[str, Any]:
    sd = _scalar(qp, "start_date")
    ed = _scalar(qp, "end_date")
    pts = _scalar(qp, "paid_through_start")
    pte = _scalar(qp, "paid_through_end")
    my_raw = _scalar(qp, "membership_year")
    membership_year_filter = None
    membership_year_display = ""
    if my_raw != "" and my_raw.lower() != "any":
        membership_year_filter = myear.parse_year_input(my_raw)
        membership_year_display = str(membership_year_filter) if membership_year_filter is not None else ""
    elif my_raw.lower() == "any":
        membership_year_display = "any"
    sort_by, sort_dir = _normalize_sort(
        str(qp.get("sort_by", "report_default")),
        str(qp.get("sort_dir", "asc")),
    )
    return {
        "start_date": sd,
        "end_date": ed,
        "paid_through_start": pts,
        "paid_through_end": pte,
        "membership_year": membership_year_display,
        "membership_year_filter": membership_year_filter,
        "start_filter": _optional_iso_date(sd),
        "end_filter": _optional_iso_date(ed),
        "pt_start_filter": _optional_iso_date(pts),
        "pt_end_filter": _optional_iso_date(pte),
        "sort_by": sort_by,
        "sort_dir": sort_dir,
    }


def next_sort_choice(current_sort_by: str, current_sort_dir: str, clicked_field: str) -> tuple[str, str]:
    return _next_sort_choice(
        current_sort_by,
        current_sort_dir,
        clicked_field,
        desc_first=("payment_date", "paid_through"),
    )


def list_params_to_query_input(p: dict[str, Any]) -> dict[str, Any]:
    q: dict[str, Any] = {}
    for k in ("start_date", "end_date", "paid_through_start", "paid_through_end"):
        if p.get(k):
            q[k] = str(p[k])
    if p.get("membership_year_filter") is not None:
        q["membership_year"] = int(p["membership_year_filter"])
    elif p.get("membership_year") == "any":
        q["membership_year"] = "any"
    q["sort_by"] = str(p.get("sort_by") or "report_default")
    q["sort_dir"] = str(p.get("sort_dir") or "asc")
    return q


def _filter_clause(p: dict[str, Any]) -> tuple[str, list[Any]]:
    parts = ["1 = 1"]
    bind: list[Any] = []
    if p.get("start_filter"):
        parts.append("date(p.payment_date) >= date(?)")
        bind.append(p["start_filter"])
    if p.get("end_filter"):
        parts.append("date(p.payment_date) <= date(?)")
        bind.append(p["end_filter"])
    if p.get("pt_start_filter"):
        parts.append("date(p.paid_through) >= date(?)")
        bind.append(p["pt_start_filter"])
    if p.get("pt_end_filter"):
        parts.append("date(p.paid_through) <= date(?)")
        bind.append(p["pt_end_filter"])
    if p.get("membership_year_filter") is not None:
        parts.append("p.membership_year = ?")
        bind.append(int(p["membership_year_filter"]))
    return " AND ".join(parts), bind


def _secondary_suffix(sort_by: str) -> str:
    parts = []
    if sort_by not in ("member_name", "report_default"):
        parts.append("m.last_name ASC, m.first_name ASC")
    if sort_by != "call_sign":
        parts.append("(m.call_sign) IS NULL, m.call_sign ASC")
    if sort_by != "payment_date":
        parts.append("(p.payment_date) IS NULL, p.payment_date DESC")
    return (", " + ", ".join(parts)) if parts else ""


def _order_by_sql(sort_by: str, sort_dir: str) -> str:
    desc = sort_dir == "desc"
    direction = "DESC" if desc else "ASC"
    tie = ", p.id " + ("DESC" if desc else "ASC")
    sec = _secondary_suffix(sort_by)
    mapping = {
        "report_default": ORDER_SQL_REPORT_DEFAULT_BASE + sec + ", p.id DESC",
        "member_id": f"p.member_id {direction}{sec}{tie}",
        "member_name": f"m.last_name {direction}, m.first_name {direction}{sec}{tie}",
        "call_sign": f"(m.call_sign) IS NULL, m.call_sign {direction}{sec}{tie}",
        "payment_date": f"(p.payment_date) IS NULL, p.payment_date {direction}{sec}{tie}",
        "paid_through": f"(p.paid_through) IS NULL, p.paid_through {direction}{sec}{tie}",
        "membership_year": f"(p.membership_year) IS NULL, p.membership_year {direction}{sec}{tie}",
        "membership_type": f"(mt.name) IS NULL, mt.name {direction}{sec}{tie}",
        "form_number": f"(p.form_number) IS NULL, p.form_number {direction}{sec}{tie}",
    }
    return mapping.get(sort_by, ORDER_SQL_REPORT_DEFAULT_BASE + sec + ", p.id DESC")


def map_row(r: sqlite3.Row) -> dict:
    ln = str(r["last_name"] or "")
    fn = str(r["first_name"] or "")
    member_name = f"{ln}, {fn}" if ln or fn else ""
    nm = str(r["mt_name"]) if r["mt_name"] is not None else ""
    mt_id = int(r["mt_id"]) if r["mt_id"] is not None else None
    call = str(r["call_sign"]) if r["call_sign"] is not None else ""
    my = r["membership_year"]
    return {
        "payment_id": int(r["payment_id"]),
        "member_id": int(r["member_id"]),
        "member_name": member_name,
        "call_sign": call.upper().strip() if call else "",
        "payment_date": str(r["payment_date"] or ""),
        "paid_through": str(r["paid_through"] or ""),
        "membership_year": int(my) if my not in (None, "") else None,
        "membership_type": normalizer.membership_type_display(mt_id, nm),
        "form_number": str(r["form_number"] or ""),
        "notes": str(r["notes"] or ""),
    }


class PaymentsReportRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def count_rows(self, p: dict[str, Any]) -> int:
        where, bind = _filter_clause(p)
        row = self.conn.execute(
            f"SELECT COUNT(*) FROM payments p INNER JOIN members m ON m.id = p.member_id WHERE {where}",
            bind,
        ).fetchone()
        return int(row[0])

    def list_payment_report_rows(self, p: dict[str, Any]) -> list[dict]:
        where, bind = _filter_clause(p)
        order = _order_by_sql(str(p["sort_by"]), str(p["sort_dir"]))
        sql = f"""
            SELECT p.id AS payment_id,
                   p.member_id AS member_id,
                   p.payment_date AS payment_date,
                   p.paid_through AS paid_through,
                   p.membership_year AS membership_year,
                   p.form_number AS form_number,
                   p.notes AS notes,
                   m.last_name AS last_name,
                   m.first_name AS first_name,
                   m.call_sign AS call_sign,
                   mt.id AS mt_id,
                   mt.name AS mt_name
            FROM payments p
            INNER JOIN members m ON m.id = p.member_id
            LEFT JOIN membership_types mt ON mt.id = COALESCE(p.membership_type_id, m.membership_type_id)
            WHERE {where}
            ORDER BY {order}
        """
        return [map_row(r) for r in self.conn.execute(sql, bind).fetchall()]
