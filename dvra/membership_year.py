"""Membership-year helpers and paid_through Dec 31 convention."""

from __future__ import annotations

import sqlite3
from datetime import date

MIN_YEAR = 2000
MAX_YEAR = 2100


def paid_through_iso(year: int) -> str:
    return f"{year:04d}-12-31"


def is_valid(year: int) -> bool:
    return MIN_YEAR <= year <= MAX_YEAR


def earliest_membership_year(conn: sqlite3.Connection) -> int | None:
    """Return the earliest payments.membership_year, or None if there is no data."""
    row = conn.execute(
        "SELECT MIN(membership_year) AS y FROM payments WHERE membership_year IS NOT NULL"
    ).fetchone()
    if row is None:
        return None
    raw = row["y"] if isinstance(row, sqlite3.Row) else row[0]
    if raw is None:
        return None
    try:
        year = int(raw)
    except (TypeError, ValueError):
        return None
    return year if is_valid(year) else None


def option_years(
    center_year: int, span: int = 5, *, min_year: int | None = None
) -> list[int]:
    """Years around center_year.

    When ``min_year`` is set (typically the earliest payment membership year),
    the list starts there instead of at ``center_year - span``.
    """
    span = max(0, span)
    end = min(MAX_YEAR, center_year + span)
    if min_year is not None:
        start = max(MIN_YEAR, int(min_year))
    else:
        start = max(MIN_YEAR, center_year - span)
    if start > end:
        start = end
    return list(range(start, end + 1))


def option_years_from_db(
    conn: sqlite3.Connection, center_year: int, span: int = 5
) -> list[int]:
    """Like option_years, floored at the earliest membership year in payments."""
    return option_years(
        center_year, span=span, min_year=earliest_membership_year(conn)
    )


def parse_year_input(raw: object, fallback: int | None = None) -> int | None:
    if raw is None:
        return fallback
    if isinstance(raw, (list, tuple)):
        if not raw:
            return fallback
        raw = raw[-1]
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return fallback
    text = str(raw).strip()
    if text == "":
        return fallback
    try:
        n = int(text)
    except ValueError:
        return fallback
    if not is_valid(n):
        return fallback
    return n


def calendar_year() -> int:
    return int(date.today().strftime("%Y"))
