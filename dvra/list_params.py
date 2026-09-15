"""Session-backed list/report filter snapshots."""

from __future__ import annotations

from typing import Any

from dvra import membership_year as myear
from dvra import session_query
from dvra.member_list import list_params_to_query_input, parse_list_query
from dvra.payments_report import list_params_to_query_input as pay_list_params

# Session snapshots for grid filters/sorts (not URL query strings).
MEMBERS_KEY = "dvra_members_last_export_query_input"
PAYMENTS_KEY = "dvra_payments_report_filters"
KEYHOLDERS_KEY = "dvra_keyholders_report_sort"
ROSTER_KEY = "dvra_roster_report_membership_year"


def members_persist(session: dict[str, Any], parsed: dict[str, Any]) -> None:
    session_query.write(session, MEMBERS_KEY, list_params_to_query_input(parsed))


def members_read(session: dict[str, Any]) -> dict[str, Any]:
    s = session_query.read(session, MEMBERS_KEY)
    return s if _members_snapshot_valid(s) else {}


def members_merge_post(session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    return session_query.merge_post(session, MEMBERS_KEY, body, "reset_list_filters")


def members_merge_client_sort(session: dict[str, Any], body: dict[str, Any]) -> None:
    snap = session_query.read(session, MEMBERS_KEY)
    if not _members_snapshot_valid(snap):
        snap = list_params_to_query_input(parse_list_query({}))
    flat = session_query.flatten_scalar_map(body)
    for k in ("sort_by", "sort_dir"):
        if k in flat:
            snap[k] = flat[k]
    members_persist(session, parse_list_query(snap))


def _members_snapshot_valid(snapshot: dict[str, Any] | None) -> bool:
    if not snapshot:
        return False
    for k in ("sort_by", "sort_dir", "current_only"):
        v = snapshot.get(k)
        if not isinstance(v, (str, int, float)):
            return False
    return True


def payments_persist(session: dict[str, Any], parsed: dict[str, Any]) -> None:
    session_query.write(session, PAYMENTS_KEY, pay_list_params(parsed))


def payments_read(session: dict[str, Any]) -> dict[str, Any]:
    return session_query.read(session, PAYMENTS_KEY)


def payments_merge_post(session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    return session_query.merge_post(session, PAYMENTS_KEY, body, "clear_filters")


def keyholders_persist(session: dict[str, Any], parsed: dict[str, str]) -> None:
    session_query.write(session, KEYHOLDERS_KEY, {"sort_by": parsed["sort_by"], "sort_dir": parsed["sort_dir"]})


def keyholders_read(session: dict[str, Any]) -> dict[str, Any]:
    return session_query.read(session, KEYHOLDERS_KEY)


def keyholders_merge_post(session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    return session_query.merge_post(session, KEYHOLDERS_KEY, body, None)


def roster_persist_year(session: dict[str, Any], year: int) -> None:
    session_query.write(session, ROSTER_KEY, {"membership_year": year})


def roster_read_year(session: dict[str, Any], fallback: int) -> int:
    s = session_query.read(session, ROSTER_KEY)
    parsed = myear.parse_year_input(s.get("membership_year"), fallback)
    return parsed if parsed is not None else fallback


def roster_merge_post_year(session: dict[str, Any], body: dict[str, Any], fallback: int) -> int:
    flat = session_query.flatten_scalar_map(body)
    year = myear.parse_year_input(flat.get("membership_year"), fallback) or fallback
    roster_persist_year(session, year)
    return year
