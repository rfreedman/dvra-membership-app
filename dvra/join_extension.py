"""Late-join membership extension for new members (create flow only)."""

from __future__ import annotations

import re
import sqlite3
from datetime import date
from typing import Any

from dvra import membership_year as myear
from dvra import new_ham

NEW_MEMBER_EXTENSION_NOTE = (
    "Extended membership through December 31 of the following year "
    "(new member joining in the late-year period)."
)
NEW_HAM_EXTENSION_NOTE = (
    "Extended membership through December 31 of the following year "
    "(New Ham joining in November or December)."
)

_MM_DD_RE = re.compile(r"^(\d{1,2})-(\d{1,2})$")


def parse_threshold_mmdd(raw: str) -> tuple[int, int]:
    text = (raw or "").strip()
    m = _MM_DD_RE.fullmatch(text)
    if m is None:
        raise ValueError("Threshold must be MM-DD.")
    month = int(m.group(1))
    day = int(m.group(2))
    if month < 1 or month > 12 or day < 1 or day > 31:
        raise ValueError("Invalid month or day in threshold.")
    try:
        date(2000, month, day)
    except ValueError:
        raise ValueError("Invalid calendar date for threshold.")
    return month, day


def format_threshold_mmdd(month: int, day: int) -> str:
    return f"{month:02d}-{day:02d}"


def in_late_join_window(join_date: date, threshold_mmdd: str) -> bool:
    month, day = parse_threshold_mmdd(threshold_mmdd)
    y = join_date.year
    window_start = date(y, month, day)
    window_end = date(y, 12, 31)
    return window_start <= join_date <= window_end


def extended_paid_through_iso(membership_year: int) -> str:
    return myear.paid_through_iso(membership_year + 1)


def sql_exists_payment_current_for_year(payment_alias: str = "pay") -> str:
    """SQL fragment: member m is current for membership year bound as two ? params (same Y)."""
    a = payment_alias
    return f"""EXISTS (
        SELECT 1 FROM payments {a}
        WHERE {a}.member_id = m.id
        AND {a}.membership_year <= ?
        AND date({a}.paid_through) >= date(printf('%04d-12-31', ?))
    )"""


def _extension_note(
    conn: sqlite3.Connection,
    join_date: date,
    membership_type_id: int | None,
) -> str | None:
    from dvra.app_settings import AppSettingsRepository

    settings = AppSettingsRepository(conn)
    nh_id = new_ham.find_type_id(conn)
    is_new_ham = nh_id is not None and membership_type_id == nh_id
    if is_new_ham and in_late_join_window(join_date, settings.get_new_ham_extension_start()):
        return NEW_HAM_EXTENSION_NOTE
    if in_late_join_window(join_date, settings.get_new_member_extension_start()):
        return NEW_MEMBER_EXTENSION_NOTE
    return None


def compose_initial_payment_notes(
    conn: sqlite3.Connection,
    join_date: date,
    membership_type_id: int | None,
    extension_note: str | None,
) -> str | None:
    parts: list[str] = []
    base = new_ham.initial_payment_notes(conn, membership_type_id)
    if base:
        parts.append(base)
    if extension_note:
        parts.append(extension_note)
    if not parts:
        return None
    return " ".join(parts)


def resolve_new_member_initial_payment(
    conn: sqlite3.Connection,
    join_date: date,
    membership_type_id: int | None,
    membership_year: int,
) -> dict[str, Any]:
    """Payment fields for the first payment on create member (paid_through, notes)."""
    ext_note = _extension_note(conn, join_date, membership_type_id)
    paid_through = (
        extended_paid_through_iso(membership_year)
        if ext_note is not None
        else myear.paid_through_iso(membership_year)
    )
    notes = compose_initial_payment_notes(conn, join_date, membership_type_id, ext_note)
    return {
        "paid_through": paid_through,
        "notes": notes,
    }
