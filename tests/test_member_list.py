from __future__ import annotations

from dvra.member_list import MemberListRepository
from dvra.payments import PaymentRepository

from tests.conftest import insert_member, memory_db


def _list_params(**overrides) -> dict:
    params = {
        "search": "",
        "membership_type_id": None,
        "arrl": "",
        "current_only": "no",
        "membership_year": 2026,
        "sort_by": "last_name",
        "sort_dir": "asc",
    }
    params.update(overrides)
    return params


def _pay(conn, member_id: int, payment_date: str, year: int) -> None:
    PaymentRepository(conn).insert_payment(
        member_id,
        {
            "payment_date": payment_date,
            "membership_year": year,
            "membership_type_id": None,
            "notes": None,
            "form_number": None,
        },
    )


def test_date_paid_is_latest_payment_date():
    conn = memory_db()
    mid = insert_member(conn, "Able", "Ann")
    _pay(conn, mid, "2025-03-01", 2025)
    _pay(conn, mid, "2026-11-15", 2026)
    rows = MemberListRepository(conn).list_rows_for_tabulator(_list_params())
    by_id = {r["id"]: r for r in rows}
    assert by_id[mid]["date_paid"] == "2026-11-15"


def test_date_paid_empty_when_no_payments():
    conn = memory_db()
    mid = insert_member(conn, "Baker", "Bob")
    rows = MemberListRepository(conn).list_rows_for_tabulator(_list_params())
    by_id = {r["id"]: r for r in rows}
    assert by_id[mid]["date_paid"] == ""
