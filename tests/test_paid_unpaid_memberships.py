from __future__ import annotations

from dvra.payments import PaymentRepository
from dvra.reports import ReportsRepository

from tests.conftest import insert_member, memory_db


def _pay(conn, member_id: int, payment_date: str, year: int, paid_through: str | None = None) -> None:
    PaymentRepository(conn).insert_payment(
        member_id,
        {
            "payment_date": payment_date,
            "membership_year": year,
            "membership_type_id": None,
            "notes": None,
            "form_number": None,
            **({"paid_through": paid_through} if paid_through else {}),
        },
    )


def test_paid_memberships_is_year_or_prior_year_covering_year_end():
    conn = memory_db()
    paid_2026 = insert_member(conn, "Able", "Ann")
    paid_2025 = insert_member(conn, "Baker", "Bob")
    ext_2026 = insert_member(conn, "Cole", "Cara")
    ext_2025 = insert_member(conn, "Diaz", "Dee")
    paid_2024 = insert_member(conn, "Early", "Eve")
    insert_member(conn, "None", "Ned")
    _pay(conn, paid_2026, "2026-01-10", 2026)
    _pay(conn, paid_2025, "2025-01-10", 2025)
    _pay(conn, ext_2026, "2026-11-01", 2026, paid_through="2027-12-31")
    _pay(conn, ext_2025, "2025-11-01", 2025, paid_through="2026-12-31")
    _pay(conn, paid_2024, "2024-01-10", 2024)
    repo = ReportsRepository(conn)
    assert {r["last_name"] for r in repo.list_paid_memberships(2026)} == {"Able", "Cole", "Diaz"}
    assert {r["last_name"] for r in repo.list_paid_memberships(2027)} == {"Cole"}
    assert {r["last_name"] for r in repo.list_paid_memberships(2025)} == {"Baker", "Diaz"}
    assert "Able" not in {r["last_name"] for r in repo.list_paid_memberships(2025)}
    assert "Early" not in {r["last_name"] for r in repo.list_paid_memberships(2026)}


def test_unpaid_memberships_prior_year_paid_but_not_selected_year():
    conn = memory_db()
    lapsed = insert_member(conn, "Able", "Ann")
    current = insert_member(conn, "Baker", "Bob")
    older = insert_member(conn, "Cole", "Cara")
    insert_member(conn, "Dunn", "Dan")
    _pay(conn, lapsed, "2025-01-10", 2025)
    _pay(conn, current, "2025-01-10", 2025)
    _pay(conn, current, "2026-01-10", 2026)
    _pay(conn, older, "2024-01-10", 2024)
    repo = ReportsRepository(conn)
    unpaid = {r["last_name"] for r in repo.list_unpaid_memberships(2026)}
    assert unpaid == {"Able"}
    paid = {r["last_name"] for r in repo.list_paid_memberships(2026)}
    assert paid == {"Baker"}
