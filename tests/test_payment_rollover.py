from __future__ import annotations

from dvra.payments import PaymentRepository

from tests.conftest import insert_member, memory_db


def test_duplicate_year_without_confirm_does_not_insert():
    conn = memory_db()
    # Use the app DB path: tests that hit CGI need the default sqlite file.
    # Drive rollover via repositories (server rule) plus a CGI login check separately.
    mid = insert_member(conn)
    pay = PaymentRepository(conn)
    data = {
        "payment_date": "2026-02-01",
        "membership_year": 2026,
        "membership_type_id": None,
        "notes": None,
        "form_number": None,
    }
    pay.insert_payment(mid, data)
    assert pay.member_has_payment_for_year(mid, 2026)
    proposed = pay.next_free_membership_year(mid, 2026)
    assert proposed == 2027
    n = conn.execute("SELECT COUNT(*) FROM payments WHERE member_id = ?", (mid,)).fetchone()[0]
    assert n == 1


def test_duplicate_year_with_confirm_inserts_next_free_year():
    conn = memory_db()
    mid = insert_member(conn)
    pay = PaymentRepository(conn)
    data = {
        "payment_date": "2026-02-01",
        "membership_year": 2026,
        "membership_type_id": None,
        "notes": None,
        "form_number": None,
    }
    pay.insert_payment(mid, data)
    proposed = pay.next_free_membership_year(mid, 2026)
    data["membership_year"] = proposed
    pay.insert_payment(mid, data)
    years = {
        int(r[0])
        for r in conn.execute("SELECT membership_year FROM payments WHERE member_id = ?", (mid,)).fetchall()
    }
    assert years == {2026, 2027}


def test_edit_collision_excludes_row_being_edited():
    conn = memory_db()
    mid = insert_member(conn)
    pay = PaymentRepository(conn)
    pay.insert_payment(
        mid,
        {
            "payment_date": "2025-01-01",
            "membership_year": 2025,
            "membership_type_id": None,
            "notes": None,
            "form_number": None,
        },
    )
    pay.insert_payment(
        mid,
        {
            "payment_date": "2026-01-01",
            "membership_year": 2026,
            "membership_type_id": None,
            "notes": None,
            "form_number": None,
        },
    )
    pid_2026 = int(
        conn.execute(
            "SELECT id FROM payments WHERE member_id = ? AND membership_year = 2026", (mid,)
        ).fetchone()[0]
    )
    assert pay.member_has_payment_for_year(mid, 2025, pid_2026)
    assert pay.next_free_membership_year(mid, 2025, pid_2026) == 2026
    pay.update_payment(
        pid_2026,
        {
            "payment_date": "2026-01-01",
            "membership_year": 2027,
            "membership_type_id": None,
            "notes": None,
            "form_number": None,
        },
    )
    years = {
        int(r[0])
        for r in conn.execute("SELECT membership_year FROM payments WHERE member_id = ?", (mid,)).fetchall()
    }
    assert years == {2025, 2027}
