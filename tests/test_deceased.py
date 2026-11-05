from __future__ import annotations

import pytest

from dvra import member_sk
from dvra.member_list import MemberListRepository
from dvra.members import MemberRepository
from dvra.pages.members import handle_member_edit, handle_member_new_post
from dvra.payments import MemberIsDeceased, PaymentRepository
from dvra.reports import ReportsRepository

from tests.conftest import ensure_member_form_reference_data, insert_member, member_create_form, memory_db


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


def _mark_deceased(conn, member_id: int) -> None:
    conn.execute("UPDATE members SET deceased = 1 WHERE id = ?", (member_id,))
    conn.commit()


def _ctx(conn, form: dict) -> dict:
    return {"conn": conn, "session": {}, "form": form, "query": {}}


def _prepare_editable_member(conn, *, last_name: str = "Test", first_name: str = "User") -> int:
    tech_id, _unlic, mt_id = ensure_member_form_reference_data(conn)
    mid = insert_member(conn, last_name, first_name)
    conn.execute(
        """
        UPDATE members SET call_sign = 'K1SK', license_class_id = ?, membership_type_id = ?,
               email = 'user@example.com', phone = '6095551212', address_street = '1 Main St',
               address_city = 'Trenton', address_state = 'NJ', address_zip = '08608'
        WHERE id = ?
        """,
        (tech_id, mt_id, mid),
    )
    conn.commit()
    return mid


def _edit_form(conn, mid: int, **overrides) -> dict:
    member = MemberRepository(conn).find_member_by_id(mid)
    assert member is not None
    form = member_create_form(
        conn,
        last_name=member["last_name"],
        first_name=member["first_name"],
        call_sign=member.get("call_sign") or "K1SK",
    )
    form.update(overrides)
    return form


def _current_filt(year: int = 2026) -> dict:
    return {
        "search": "",
        "membership_type_id": None,
        "arrl": "",
        "current_only": "yes",
        "membership_year": year,
        "sort_by": "last_name",
        "sort_dir": "asc",
    }


def test_deceased_member_is_not_current_or_on_roster():
    conn = memory_db()
    living = insert_member(conn, "Able", "Ann")
    dead = insert_member(conn, "Baker", "Bob")
    _pay(conn, living, 2026)
    _pay(conn, dead, 2026)
    _mark_deceased(conn, dead)
    repo = MemberListRepository(conn)
    names = {r["last_name"] for r in repo.list_rows_for_export(_current_filt())}
    assert names == {"Able"}
    all_living = {
        r["last_name"]
        for r in repo.list_rows_for_export({**_current_filt(), "current_only": "no"})
    }
    assert all_living == {"Able"}
    included = {
        r["last_name"]
        for r in repo.list_rows_for_export({**_current_filt(), "include_deceased": "yes"})
    }
    assert included == {"Able", "Baker"}
    all_included = {
        r["last_name"]
        for r in repo.list_rows_for_export(
            {**_current_filt(), "current_only": "no", "include_deceased": "yes"}
        )
    }
    assert all_included == {"Able", "Baker"}
    bob = next(
        r
        for r in repo.list_rows_for_export(
            {**_current_filt(), "current_only": "no", "include_deceased": "yes"}
        )
        if r["last_name"] == "Baker"
    )
    assert bob["deceased"] is True
    reports = ReportsRepository(conn)
    assert {r["last_name"] for r in reports.roster_by_name(2026)} == {"Able"}
    unpaid = {r["last_name"] for r in reports.list_unpaid_memberships(2027)}
    assert unpaid == {"Able"}


def test_deceased_secondary_is_not_current_when_primary_is_paid():
    conn = memory_db()
    primary = insert_member(conn, "Gerbavac", "Cindy")
    secondary = insert_member(conn, "Fritz", "Don")
    _pay(conn, primary, 2026)
    conn.execute(
        "UPDATE members SET family_primary_member_id = ? WHERE id = ?",
        (primary, secondary),
    )
    conn.commit()
    names = {r["first_name"] for r in MemberListRepository(conn).list_rows_for_export(_current_filt())}
    assert names == {"Cindy", "Don"}
    _mark_deceased(conn, secondary)
    names = {r["first_name"] for r in MemberListRepository(conn).list_rows_for_export(_current_filt())}
    assert names == {"Cindy"}


def test_cannot_insert_payment_for_deceased_member():
    conn = memory_db()
    mid = insert_member(conn, "Baker", "Bob")
    _pay(conn, mid, 2025)
    _mark_deceased(conn, mid)
    with pytest.raises(MemberIsDeceased):
        _pay(conn, mid, 2026)
    years = [
        int(r["membership_year"])
        for r in conn.execute("SELECT membership_year FROM payments WHERE member_id = ?", (mid,))
    ]
    assert years == [2025]
    member = MemberRepository(conn).find_member_by_id(mid)
    assert member["deceased"] is True


def test_new_member_post_ignores_deceased_and_records_payment():
    conn = memory_db()
    form = member_create_form(conn, deceased="yes")
    resp = handle_member_new_post(_ctx(conn, form))
    assert resp.status == 303
    mid = int(conn.execute("SELECT id FROM members ORDER BY id DESC LIMIT 1").fetchone()[0])
    deceased = conn.execute("SELECT deceased FROM members WHERE id = ?", (mid,)).fetchone()[0]
    assert int(deceased) == 0
    pay_count = conn.execute("SELECT COUNT(*) FROM payments WHERE member_id = ?", (mid,)).fetchone()[0]
    assert int(pay_count) == 1


def test_edit_clear_sk_requires_confirm():
    conn = memory_db()
    mid = _prepare_editable_member(conn)
    _mark_deceased(conn, mid)
    form = _edit_form(conn, mid, deceased="no")
    resp = handle_member_edit(_ctx(conn, form), mid)
    assert resp.status == 400
    assert member_sk.SK_CHANGE_CONFIRM_REQUIRED.encode() in resp.body
    deceased = conn.execute("SELECT deceased FROM members WHERE id = ?", (mid,)).fetchone()[0]
    assert int(deceased) == 1


def test_edit_clear_sk_with_confirm():
    conn = memory_db()
    mid = _prepare_editable_member(conn)
    _mark_deceased(conn, mid)
    form = _edit_form(conn, mid, deceased="no", confirm_deceased_change="1")
    resp = handle_member_edit(_ctx(conn, form), mid)
    assert resp.status == 303
    deceased = conn.execute("SELECT deceased FROM members WHERE id = ?", (mid,)).fetchone()[0]
    assert int(deceased) == 0


def test_edit_mark_sk_with_confirm():
    conn = memory_db()
    mid = _prepare_editable_member(conn)
    form = _edit_form(conn, mid, deceased="yes", confirm_deceased_change="1")
    resp = handle_member_edit(_ctx(conn, form), mid)
    assert resp.status == 303
    deceased = conn.execute("SELECT deceased FROM members WHERE id = ?", (mid,)).fetchone()[0]
    assert int(deceased) == 1
