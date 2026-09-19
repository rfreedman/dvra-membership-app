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


def test_resolve_new_ham_september_uses_general_note_only():
    conn = memory_db()
    nh = new_ham.find_type_id(conn)
    assert nh is not None
    out = join_extension.resolve_new_member_initial_payment(
        conn, date(2026, 9, 15), nh, 2026
    )
    assert out["paid_through"] == "2027-12-31"
    assert new_ham.NEW_HAM_FREE_YEAR_NOTE in (out["notes"] or "")
    assert join_extension.NEW_MEMBER_EXTENSION_NOTE in (out["notes"] or "")
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
    nh = new_ham.find_type_id(conn)
    assert nh is not None
    assert not join_extension.in_late_join_window(date(2026, 8, 31), settings.get_new_member_extension_start())
    out = join_extension.resolve_new_member_initial_payment(
        conn, date(2026, 9, 1), nh, 2026
    )
    assert out["paid_through"] == "2027-12-31"


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
