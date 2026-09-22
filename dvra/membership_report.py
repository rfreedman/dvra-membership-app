"""Membership report aggregations (monthly dashboard)."""

from __future__ import annotations

import calendar
import sqlite3
from datetime import date
from typing import Any

from dvra import join_extension
from dvra import membership_year as myear

MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def _percent_parts(counts: list[int]) -> list[int]:
    """Integer percents that sum to 100 (largest-remainder), or all zeros."""
    total = sum(counts)
    if total <= 0:
        return [0 for _ in counts]
    exact = [100.0 * c / total for c in counts]
    floors = [int(x) for x in exact]
    rem = 100 - sum(floors)
    order = sorted(
        range(len(counts)),
        key=lambda i: (exact[i] - floors[i], counts[i]),
        reverse=True,
    )
    for i in order[:rem]:
        floors[i] += 1
    return floors


def parse_membership_report_query(
    qp: dict[str, Any], *, today: date | None = None, default_membership_year: int | None = None
) -> dict[str, Any]:
    """Parse filter snapshot: membership_year (report year) and calendar_month.

    Year/month are clamped so they cannot be later than ``today``.
    """
    today = today or date.today()
    fallback_year = default_membership_year if default_membership_year is not None else today.year
    if fallback_year > today.year:
        fallback_year = today.year
    membership_year = myear.parse_year_input(qp.get("membership_year"), fallback_year) or fallback_year
    if membership_year > today.year:
        membership_year = today.year

    try:
        calendar_month = int(qp.get("calendar_month") or today.month)
    except (TypeError, ValueError):
        calendar_month = today.month
    if calendar_month < 1 or calendar_month > 12:
        calendar_month = today.month
    if membership_year == today.year and calendar_month > today.month:
        calendar_month = today.month

    return {
        "membership_year": membership_year,
        "calendar_month": calendar_month,
    }


def membership_report_year_options(
    default_year: int,
    *,
    today: date | None = None,
    span: int = 5,
    min_year: int | None = None,
) -> list[int]:
    """Year choices centered on default_year, capped at the current calendar year."""
    today = today or date.today()
    center = min(int(default_year), today.year)
    return [
        y
        for y in myear.option_years(center, span=span, min_year=min_year)
        if y <= today.year
    ]


def membership_report_month_options(
    membership_year: int, *, today: date | None = None
) -> list[dict[str, Any]]:
    """Month choices for the selected year; current year stops at today's month."""
    today = today or date.today()
    year = int(membership_year)
    if year > today.year:
        last = 0
    elif year == today.year:
        last = today.month
    else:
        last = 12
    return [{"value": i, "label": MONTH_NAMES[i - 1]} for i in range(1, last + 1)]


def filters_to_session(parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "membership_year": int(parsed["membership_year"]),
        "calendar_month": int(parsed["calendar_month"]),
    }


class MembershipReportRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def build_report(self, filters: dict[str, Any]) -> dict[str, Any]:
        membership_year = int(filters["membership_year"])
        calendar_month = int(filters["calendar_month"])
        # One report period: year drives current-member and new-member stats.
        report_year = membership_year
        last_day = calendar.monthrange(report_year, calendar_month)[1]
        as_of = date(report_year, calendar_month, last_day)

        member_counts = self.member_counts_by_month(
            membership_year, through_month=calendar_month
        )
        member_count = member_counts[-1]["count"] if member_counts else 0
        new_this_month = self.count_new_members_in_month(report_year, calendar_month)
        new_ytd = self.new_members_ytd_by_month(report_year, through_month=calendar_month)
        arrl = self.arrl_split(membership_year, as_of=as_of)
        license_class = self.license_class_distribution(membership_year, as_of=as_of)

        return {
            "membership_year": membership_year,
            "calendar_year": report_year,
            "calendar_month": calendar_month,
            "calendar_month_name": MONTH_NAMES[calendar_month - 1],
            "report_heading": (
                f"DVRA Membership - {MONTH_NAMES[calendar_month - 1]}, {report_year}"
            ),
            "member_count": member_count,
            "member_counts_by_month": member_counts,
            "new_members_month": new_this_month,
            "new_members_ytd_total": sum(r["count"] for r in new_ytd),
            "new_members_ytd": new_ytd,
            "arrl_members": arrl["members"],
            "arrl_non_members": arrl["non_members"],
            "arrl_percent": arrl["percent"],
            "arrl_members_percent": arrl["members_percent"],
            "arrl_non_members_percent": arrl["non_members_percent"],
            "license_class": license_class,
            "charts": {
                "member_count": {
                    "labels": [r["month_name"] for r in member_counts],
                    "values": [r["count"] for r in member_counts],
                },
                "license_class": {
                    "labels": [r["name"] for r in license_class],
                    "values": [r["count"] for r in license_class],
                    "percents": [r["percent"] for r in license_class],
                },
                "new_enrollment": {
                    "labels": [r["month_name"] for r in new_ytd],
                    "values": [r["count"] for r in new_ytd],
                },
                "arrl": {
                    "labels": ["Y", "N"],
                    "values": [arrl["members"], arrl["non_members"]],
                    "percents": [arrl["members_percent"], arrl["non_members_percent"]],
                },
            },
        }

    def count_current_members(self, membership_year: int, *, as_of: date) -> int:
        sql = (
            "SELECT COUNT(*) FROM members m WHERE "
            + join_extension.sql_exists_payment_current_for_year_as_of("pay")
        )
        row = self.conn.execute(
            sql, (membership_year, membership_year, as_of.isoformat())
        ).fetchone()
        return int(row[0])

    def member_counts_by_month(
        self, membership_year: int, *, through_month: int = 12
    ) -> list[dict[str, Any]]:
        """Month-end current-member counts for Jan…through_month of membership_year."""
        last = max(1, min(12, int(through_month)))
        out: list[dict[str, Any]] = []
        for month in range(1, last + 1):
            last_day = calendar.monthrange(membership_year, month)[1]
            as_of = date(membership_year, month, last_day)
            out.append(
                {
                    "month": month,
                    "month_name": MONTH_NAMES[month - 1],
                    "count": self.count_current_members(membership_year, as_of=as_of),
                }
            )
        return out

    def count_new_members_in_month(self, year: int, month: int) -> int:
        start = date(year, month, 1).isoformat()
        last_day = calendar.monthrange(year, month)[1]
        end = date(year, month, last_day).isoformat()
        row = self.conn.execute(
            """
            SELECT COUNT(*) FROM members m
            WHERE EXISTS (
                SELECT 1 FROM payments p
                WHERE p.member_id = m.id
                GROUP BY p.member_id
                HAVING COUNT(*) = 1
                   AND date(MIN(p.payment_date)) >= date(?)
                   AND date(MIN(p.payment_date)) <= date(?)
            )
            """,
            (start, end),
        ).fetchone()
        return int(row[0])

    def new_members_ytd_by_month(self, year: int, *, through_month: int = 12) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT CAST(strftime('%m', first_pay) AS INTEGER) AS mon, COUNT(*) AS cnt
            FROM (
                SELECT m.id AS member_id, MIN(p.payment_date) AS first_pay
                FROM members m
                JOIN payments p ON p.member_id = m.id
                GROUP BY m.id
                HAVING COUNT(*) = 1
                   AND CAST(strftime('%Y', MIN(p.payment_date)) AS INTEGER) = ?
            ) AS firsts
            GROUP BY mon
            """,
            (year,),
        ).fetchall()
        by_month = {int(r["mon"]): int(r["cnt"]) for r in rows}
        last = max(1, min(12, int(through_month)))
        out = []
        for i, name in enumerate(MONTH_NAMES[:last], start=1):
            out.append({"month": i, "month_name": name, "count": by_month.get(i, 0)})
        return out

    def arrl_split(self, membership_year: int, *, as_of: date) -> dict[str, Any]:
        current = join_extension.sql_exists_payment_current_for_year_as_of("pay")
        binds = (membership_year, membership_year, as_of.isoformat())
        members = int(
            self.conn.execute(
                f"SELECT COUNT(*) FROM members m WHERE {current} AND m.arrl_member = 1",
                binds,
            ).fetchone()[0]
        )
        non_members = int(
            self.conn.execute(
                f"SELECT COUNT(*) FROM members m WHERE {current} AND COALESCE(m.arrl_member, 0) = 0",
                binds,
            ).fetchone()[0]
        )
        total = members + non_members
        if total:
            members_percent = int(round(100.0 * members / total))
            non_members_percent = 100 - members_percent
        else:
            members_percent = 0
            non_members_percent = 0
        return {
            "members": members,
            "non_members": non_members,
            "percent": members_percent,
            "members_percent": members_percent,
            "non_members_percent": non_members_percent,
        }

    def license_class_distribution(self, membership_year: int, *, as_of: date) -> list[dict[str, Any]]:
        current = join_extension.sql_exists_payment_current_for_year_as_of("pay")
        rows = self.conn.execute(
            f"""
            SELECT COALESCE(NULLIF(TRIM(lc.name), ''), 'Unlicensed') AS name, COUNT(*) AS cnt
            FROM members m
            LEFT JOIN license_classes lc ON lc.id = m.license_class_id
            WHERE {current}
            GROUP BY COALESCE(NULLIF(TRIM(lc.name), ''), 'Unlicensed')
            ORDER BY cnt DESC, name ASC
            """,
            (membership_year, membership_year, as_of.isoformat()),
        ).fetchall()
        counts = [int(r["cnt"]) for r in rows]
        percents = _percent_parts(counts)
        return [
            {"name": str(r["name"]), "count": cnt, "percent": pct}
            for r, cnt, pct in zip(rows, counts, percents)
        ]
