from __future__ import annotations

from datetime import date
from unittest.mock import patch

from dvra import join_extension
from dvra import new_ham
from dvra.app_settings import AppSettingsRepository
from dvra.member_list import MemberListRepository
from dvra.pages import members as member_pages
from dvra.payments import PaymentRepository
from dvra.reference_data import ReferenceDataRepository
from dvra.reports import ReportsRepository

from tests.conftest import insert_member, member_create_form, memory_db


def _ctx(conn, form: dict) -> dict:
    return {"conn": conn, "session": {}, "form": form, "query": {}}


def test_in_late_join_window_respects_threshold():
    assert join_extension.in_late_join_window(date(2026, 8, 1), "08-01")
    assert join_extension.in_late_join_window(date(2026, 12, 31), "08-01")
    assert not join_extension.in_late_join_window(date(2026, 7, 31), "08-01")


def test_resolve_new_ham_november_extends_paid_through_and_notes():
    conn = memory_db()
    nh = new_ham.find_type_id(conn)
    assert nh is not None
    out = join_extension.resolve_new_member_initial_payment(
        conn, date(2026, 11, 10), nh, 2026
    )
    assert out["paid_through"] == "2027-12-31"
    assert new_ham.NEW_HAM_FREE_YEAR_NOTE in (out["notes"] or "")
    assert join_extension.NEW_HAM_EXTENSION_NOTE in (out["notes"] or "")
    assert join_extension.NEW_MEMBER_EXTENSION_NOTE not in (out["notes"] or "")


def test_resolve_regular_september_general_extension_only():
    conn = memory_db()
    regular = ReferenceDataRepository(conn)
    regular.create_membership_type("Regular")
    rid = int(
        conn.execute("SELECT id FROM membership_types WHERE name = 'Regular'").fetchone()[0]
    )
    out = join_extension.resolve_new_member_initial_payment(
        conn, date(2026, 9, 1), rid, 2026
    )
    assert out["paid_through"] == "2027-12-31"
    assert out["notes"] == join_extension.NEW_MEMBER_EXTENSION_NOTE


def test_resolve_new_ham_september_skips_regular_extension():
    conn = memory_db()
    nh = new_ham.find_type_id(conn)
    assert nh is not None
    out = join_extension.resolve_new_member_initial_payment(
        conn, date(2026, 9, 15), nh, 2026
    )
    assert out["paid_through"] == "2026-12-31"
    assert out["notes"] == new_ham.NEW_HAM_FREE_YEAR_NOTE
    assert join_extension.NEW_MEMBER_EXTENSION_NOTE not in (out["notes"] or "")
    assert join_extension.NEW_HAM_EXTENSION_NOTE not in (out["notes"] or "")


def test_resolve_july_no_extension():
    conn = memory_db()
    nh = new_ham.find_type_id(conn)
    out = join_extension.resolve_new_member_initial_payment(
        conn, date(2026, 7, 1), nh, 2026
    )
    assert out["paid_through"] == "2026-12-31"
    assert out["notes"] == new_ham.NEW_HAM_FREE_YEAR_NOTE


def test_custom_threshold_from_settings():
    conn = memory_db()
    settings = AppSettingsRepository(conn)
    settings.set_new_member_extension_start("09-01")
    ReferenceDataRepository(conn).create_membership_type("Regular")
    rid = int(
        conn.execute("SELECT id FROM membership_types WHERE name = 'Regular'").fetchone()[0]
    )
    nh = new_ham.find_type_id(conn)
    assert nh is not None
    assert not join_extension.in_late_join_window(date(2026, 8, 31), settings.get_new_member_extension_start())
    out = join_extension.resolve_new_member_initial_payment(
        conn, date(2026, 9, 1), rid, 2026
    )
    assert out["paid_through"] == "2027-12-31"
    new_ham_out = join_extension.resolve_new_member_initial_payment(
        conn, date(2026, 9, 1), nh, 2026
    )
    assert new_ham_out["paid_through"] == "2026-12-31"


@patch("dvra.pages.members._new_member_join_date", return_value=date(2026, 11, 12))
def test_new_member_post_new_ham_november(_mock_join):
    conn = memory_db()
    nh = new_ham.find_type_id(conn)
    assert nh is not None
    resp = member_pages.handle_member_new_post(
        _ctx(
            conn,
            member_create_form(
                conn,
                membership_type_id=nh,
                last_name="Late",
                first_name="Join",
            ),
        )
    )
    assert resp.status == 303
    row = conn.execute(
        "SELECT paid_through, notes, membership_year FROM payments LIMIT 1"
    ).fetchone()
    assert row["paid_through"] == "2027-12-31"
    assert int(row["membership_year"]) == 2026
    assert join_extension.NEW_HAM_EXTENSION_NOTE in (row["notes"] or "")


def test_new_member_form_includes_payment_date():
    conn = memory_db()
    resp = member_pages.handle_member_new_get(_ctx(conn, {}))
    assert resp.status == 200
    html = resp.body.decode()
    assert 'id="new-payment-date"' in html
    assert 'name="payment_date"' in html
    assert 'type="date"' in html


def test_new_member_payment_date_extends_late_join():
    conn = memory_db()
    nh = new_ham.find_type_id(conn)
    assert nh is not None
    resp = member_pages.handle_member_new_post(
        _ctx(
            conn,
            member_create_form(
                conn,
                membership_type_id=nh,
                last_name="Late",
                first_name="Paid",
                call_sign="K2LATE",
                payment_date="2026-11-12",
            ),
        )
    )
    assert resp.status == 303
    row = conn.execute(
        "SELECT payment_date, paid_through, notes, membership_year FROM payments LIMIT 1"
    ).fetchone()
    assert str(row["payment_date"]) == "2026-11-12"
    assert row["paid_through"] == "2027-12-31"
    assert int(row["membership_year"]) == 2026
    assert join_extension.NEW_HAM_EXTENSION_NOTE in (row["notes"] or "")


@patch("dvra.pages.members._new_member_join_date", return_value=date(2026, 11, 12))
def test_new_member_payment_date_overrides_today(_mock_join):
    conn = memory_db()
    nh = new_ham.find_type_id(conn)
    assert nh is not None
    resp = member_pages.handle_member_new_post(
        _ctx(
            conn,
            member_create_form(
                conn,
                membership_type_id=nh,
                last_name="Early",
                first_name="Paid",
                call_sign="K2EARL",
                payment_date="2026-06-01",
            ),
        )
    )
    assert resp.status == 303
    row = conn.execute(
        "SELECT payment_date, paid_through FROM payments LIMIT 1"
    ).fetchone()
    assert str(row["payment_date"]) == "2026-06-01"
    assert row["paid_through"] == "2026-12-31"
    assert join_extension.NEW_HAM_EXTENSION_NOTE not in (
        conn.execute("SELECT notes FROM payments LIMIT 1").fetchone()["notes"] or ""
    )


def test_new_member_rejects_blank_payment_date():
    conn = memory_db()
    form = member_create_form(conn, call_sign="K2NONE", payment_date="")
    resp = member_pages.handle_member_new_post(_ctx(conn, form))
    assert resp.status == 400
    assert b"Payment date is required." in resp.body
    assert conn.execute("SELECT id FROM members WHERE call_sign = 'K2NONE'").fetchone() is None


def test_payment_edit_saves_paid_through_without_changing_it_from_payment_date():
    conn = memory_db()
    mid = insert_member(conn)
    PaymentRepository(conn).insert_payment(
        mid,
        {
            "payment_date": "2026-01-15",
            "membership_year": 2026,
            "membership_type_id": None,
            "paid_through": "2026-12-31",
            "notes": None,
            "form_number": None,
        },
    )
    pid = int(conn.execute("SELECT id FROM payments WHERE member_id = ?", (mid,)).fetchone()[0])
    resp = member_pages.handle_payment_edit(
        _ctx(
            conn,
            {
                "payment_date": "2026-09-01",
                "membership_year": "2026",
                "paid_through": "2027-06-30",
                "notes": "adjusted",
            },
        ),
        pid,
    )
    assert resp.status == 303
    row = conn.execute(
        "SELECT payment_date, paid_through, notes FROM payments WHERE id = ?",
        (pid,),
    ).fetchone()
    assert str(row["payment_date"]) == "2026-09-01"
    assert row["paid_through"] == "2027-06-30"
    assert row["notes"] == "adjusted"
    member = conn.execute("SELECT paid_through FROM members WHERE id = ?", (mid,)).fetchone()
    assert member["paid_through"] == "2027-06-30"


def test_payments_page_paid_through_is_editable_and_saved_explicitly():
    conn = memory_db()
    mid = insert_member(conn, "Row", "Editor")
    PaymentRepository(conn).insert_payment(
        mid,
        {
            "payment_date": "2026-03-01",
            "membership_year": 2026,
            "membership_type_id": None,
            "notes": "dues",
            "form_number": "44",
        },
    )
    resp = member_pages.handle_member_payments(_ctx(conn, {}), mid)
    assert resp.status == 200
    html = resp.body.decode()
    assert 'name="paid_through" type="date"' in html
    assert 'class="payment-row-save"' in html
    assert "payment-unsaved-stay" in html
    assert "Continue and lose changes" in html
    assert 'querySelectorAll(".payment-row-input")' not in html


def test_extended_paid_through_counts_current_for_following_year():
    conn = memory_db()
    mid = insert_member(conn)
    PaymentRepository(conn).insert_payment(
        mid,
        {
            "payment_date": "2026-11-01",
            "membership_year": 2026,
            "membership_type_id": None,
            "paid_through": "2027-12-31",
            "notes": None,
            "form_number": None,
        },
    )
    filt = {
        "search": "",
        "membership_type_id": None,
        "arrl": "",
        "current_only": "yes",
        "membership_year": 2027,
        "sort_by": "last_name",
        "sort_dir": "asc",
    }
    rows = MemberListRepository(conn).list_rows_for_export(filt)
    assert len(rows) == 1
    reports = ReportsRepository(conn)
    assert len(reports.roster_by_name(2027)) == 1
    assert reports.roster_by_name(2028) == []
