from __future__ import annotations

from dvra.member_list import MemberListRepository
from dvra.payments import PaymentRepository
from dvra.reports import ReportsRepository

from tests.conftest import insert_member, memory_db


def _pay(conn, member_id: int, year: int) -> None:
    PaymentRepository(conn).insert_payment(
        member_id,
        {
            "payment_date": f"{year}-01-15",
            "membership_year": year,
            "membership_type_id": None,
            "notes": None,
            "form_number": None,
        },
    )


def test_current_only_includes_members_paid_for_year_independent_of_calendar():
    conn = memory_db()
    a = insert_member(conn, "Able", "Ann")
    b = insert_member(conn, "Baker", "Bob")
    _pay(conn, a, 2024)
    _pay(conn, b, 2025)
    repo = MemberListRepository(conn)
    filt = {
        "search": "",
        "membership_type_id": None,
        "arrl": "",
        "current_only": "yes",
        "membership_year": 2024,
        "sort_by": "last_name",
        "sort_dir": "asc",
    }
    rows = repo.list_rows_for_export(filt)
    names = {r["last_name"] for r in rows}
    assert names == {"Able"}
    filt["membership_year"] = 2025
    rows = repo.list_rows_for_export(filt)
    names = {r["last_name"] for r in rows}
    assert names == {"Baker"}
    filt["current_only"] = "no"
    filt["membership_year"] = 2024
    assert repo.count_members(filt) == 2


def test_roster_uses_same_year_exists_filter():
    conn = memory_db()
    a = insert_member(conn, "Able", "Ann")
    insert_member(conn, "Baker", "Bob")
    _pay(conn, a, 2026)
    reports = ReportsRepository(conn)
    by_name = reports.roster_by_name(2026)
    assert [r["last_name"] for r in by_name] == ["Able"]
    assert reports.roster_by_name(2025) == []
