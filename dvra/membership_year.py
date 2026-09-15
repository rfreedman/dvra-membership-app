"""Membership-year helpers and paid_through Dec 31 convention."""

from __future__ import annotations

from datetime import date

MIN_YEAR = 2000
MAX_YEAR = 2100


def paid_through_iso(year: int) -> str:
    return f"{year:04d}-12-31"


def is_valid(year: int) -> bool:
    return MIN_YEAR <= year <= MAX_YEAR


def option_years(center_year: int, span: int = 5) -> list[int]:
    span = max(0, span)
    start = max(MIN_YEAR, center_year - span)
    end = min(MAX_YEAR, center_year + span)
    return list(range(start, end + 1))


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
