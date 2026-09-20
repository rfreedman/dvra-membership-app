from __future__ import annotations

from datetime import date

from dvra.payments import PaymentRepository
from dvra.reference_data import ReferenceDataRepository
from dvra.reports import ReportsRepository, default_new_members_since, parse_new_members_query

from tests.conftest import insert_member, memory_db


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


def test_default_since_is_first_of_month():
    assert default_new_members_since(date(2026, 9, 20)) == "2026-09-01"


def test_parse_new_members_uses_default_when_missing_or_invalid():
    today = date(2026, 3, 15)
    assert parse_new_members_query({}, today=today)["since"] == "2026-03-01"
    assert parse_new_members_query({"since": "not-a-date"}, today=today)["since"] == "2026-03-01"
    assert parse_new_members_query({"since": "2026-04-10"}, today=today)["since"] == "2026-04-10"


def test_new_members_filters_by_latest_date_paid():
    conn = memory_db()
    ref = ReferenceDataRepository(conn)
    ref.create_membership_type("Individual")
    individual_id = int(
        conn.execute("SELECT id FROM membership_types WHERE name = 'Individual'").fetchone()[0]
    )
    included = insert_member(conn, "Able", "Ann")
    excluded = insert_member(conn, "Baker", "Bob")
    none = insert_member(conn, "Cain", "Cara")
    conn.execute(
        "UPDATE members SET address_city = ?, address_state = ?, membership_type_id = ? WHERE id = ?",
        ("Trenton", "NJ", individual_id, included),
    )
    conn.commit()
    _pay(conn, included, "2026-08-01", 2026)
    _pay(conn, included, "2026-09-12", 2026)
    _pay(conn, excluded, "2026-08-15", 2026)
    rows = ReportsRepository(conn).list_new_members("2026-09-01")
    names = {r["last_name"] for r in rows}
    assert names == {"Able"}
    assert rows[0]["date_paid"] == "2026-09-12"
    assert rows[0]["paid_through"] == "2026-12-31"
    assert rows[0]["membership_type"] == "Individual"
    assert rows[0]["city"] == "Trenton"
    assert rows[0]["state"] == "NJ"
    assert none not in {r["id"] for r in rows}
