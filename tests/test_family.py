from __future__ import annotations

import pytest

from dvra.app_settings import AppSettingsRepository
from dvra import view
from dvra.family import (
    apply_roster_family_links,
    delete_secondary_payments_covered_by_primary,
    validate_family_primary,
)
from dvra.member_list import MemberListRepository
from dvra.members import MemberHasFamilySecondaries, MemberRepository
from dvra.pages.members import handle_member_edit, handle_member_new_post
from dvra.payments import PaymentRepository
from dvra.reference_data import ReferenceDataRepository
from dvra.reports import ReportsRepository

from tests.conftest import insert_member, member_create_form, memory_db


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


def _link(conn, secondary_id: int, primary_id: int) -> None:
    conn.execute(
        "UPDATE members SET family_primary_member_id = ? WHERE id = ?",
        (primary_id, secondary_id),
    )
    for sid in delete_secondary_payments_covered_by_primary(conn, secondary_id):
        PaymentRepository(conn).sync_member_paid_through_from_payments(sid)
    conn.commit()


def test_secondary_is_current_when_primary_is_paid():
    conn = memory_db()
    primary = insert_member(conn, "Wilson", "Gary")
    secondary = insert_member(conn, "Wilson", "Jill")
    _pay(conn, primary, 2026)
    _link(conn, secondary, primary)
    repo = MemberListRepository(conn)
    filt = {
        "search": "",
        "membership_type_id": None,
        "arrl": "",
        "current_only": "yes",
        "membership_year": 2026,
        "sort_by": "last_name",
        "sort_dir": "asc",
    }
    rows = repo.list_rows_for_export(filt)
    names = {r["first_name"] for r in rows}
    assert names == {"Gary", "Jill"}
    jill = next(r for r in rows if r["first_name"] == "Jill")
    assert jill["covered_by"] == "Wilson, Gary"
    assert jill["paid_through"] == "2026-12-31"
    assert jill["date_paid"] == "2026-01-15"


def test_secondary_drops_off_current_when_primary_lapses():
    conn = memory_db()
    primary = insert_member(conn, "Wilson", "Gary")
    secondary = insert_member(conn, "Wilson", "Jill")
    _pay(conn, primary, 2025)
    _link(conn, secondary, primary)
    repo = MemberListRepository(conn)
    filt = {
        "search": "",
        "membership_type_id": None,
        "arrl": "",
        "current_only": "yes",
        "membership_year": 2026,
        "sort_by": "last_name",
        "sort_dir": "asc",
    }
    assert repo.list_rows_for_export(filt) == []
    filt["membership_year"] = 2025
    names = {r["first_name"] for r in repo.list_rows_for_export(filt)}
    assert names == {"Gary", "Jill"}


def test_roster_and_paid_unpaid_follow_family_primary():
    conn = memory_db()
    primary = insert_member(conn, "Santoro", "David")
    secondary = insert_member(conn, "Santoro", "Leslie")
    _pay(conn, primary, 2025)
    _pay(conn, primary, 2026)
    _link(conn, secondary, primary)
    reports = ReportsRepository(conn)
    roster_names = {r["last_name"] + r["first_name"] for r in reports.roster_by_name(2026)}
    assert roster_names == {"SantoroDavid", "SantoroLeslie"}
    paid = reports.list_paid_memberships(2026)
    assert {r["first_name"] for r in paid} == {"David", "Leslie"}
    leslie = next(r for r in paid if r["first_name"] == "Leslie")
    assert leslie["covered_by"] == "Santoro, David"
    assert reports.list_unpaid_memberships(2026) == []

    conn.execute("DELETE FROM payments WHERE member_id = ? AND membership_year = 2026", (primary,))
    conn.execute("UPDATE members SET paid_through = '2025-12-31' WHERE id = ?", (primary,))
    conn.commit()
    unpaid = {r["first_name"] for r in reports.list_unpaid_memberships(2026)}
    assert unpaid == {"David", "Leslie"}


def test_family_primary_validation_rules():
    conn = memory_db()
    primary = insert_member(conn, "Huston", "Steven")
    secondary = insert_member(conn, "Huston", "Emily")
    other = insert_member(conn, "Huston", "Stephanie")
    _link(conn, secondary, primary)
    assert validate_family_primary(conn, secondary, secondary) == "A member cannot be covered by themselves."
    assert "already covered" in (validate_family_primary(conn, other, secondary) or "")
    assert "already covers" in (validate_family_primary(conn, primary, other) or "")
    assert validate_family_primary(conn, other, primary) is None
    assert validate_family_primary(conn, None, None) is None


def test_secondary_with_older_own_payment_uses_later_primary_paid_through():
    conn = memory_db()
    primary = insert_member(conn, "Brucks", "Debbie")
    secondary = insert_member(conn, "Brucks", "Glenn")
    _pay(conn, secondary, 2025)
    _pay(conn, primary, 2026)
    _link(conn, secondary, primary)
    repo = MemberListRepository(conn)
    filt = {
        "search": "",
        "membership_type_id": None,
        "arrl": "",
        "current_only": "yes",
        "membership_year": 2026,
        "sort_by": "first_name",
        "sort_dir": "asc",
    }
    rows = repo.list_rows_for_export(filt)
    glenn = next(r for r in rows if r["first_name"] == "Glenn")
    assert glenn["paid_through"] == "2026-12-31"
    member = MemberRepository(conn).find_member_by_id(secondary)
    assert member["paid_through"] == "2026-12-31"
    assert member["paid_through_inherited"] is True


def test_secondary_payments_show_covered_by_not_primary_notes():
    conn = memory_db()
    primary = insert_member(conn, "Brucks", "Debbie")
    secondary = insert_member(conn, "Brucks", "Glenn")
    conn.execute("UPDATE members SET call_sign = ? WHERE id = ?", ("KC3KEO", primary))
    conn.commit()
    PaymentRepository(conn).insert_payment(
        primary,
        {
            "payment_date": "2026-01-14",
            "membership_year": 2026,
            "membership_type_id": None,
            "notes": "1/14/2026 (619)",
            "form_number": "619",
        },
    )
    _pay(conn, primary, 2025)
    _pay(conn, secondary, 2025)
    _pay(conn, secondary, 2024)
    _link(conn, secondary, primary)
    own_years = [
        int(r["membership_year"])
        for r in conn.execute(
            "SELECT membership_year FROM payments WHERE member_id = ? ORDER BY membership_year DESC",
            (secondary,),
        )
    ]
    assert own_years == [2024]
    rows = MemberRepository(conn).list_payments_for_member(secondary)
    inherited = [p for p in rows if p["inherited"]]
    own = [p for p in rows if not p["inherited"]]
    assert [p["membership_year"] for p in inherited] == [2026, 2025]
    assert inherited[0]["notes"] == "Covered by Brucks, Debbie (KC3KEO)"
    assert inherited[0]["form_number"] == "619"
    assert inherited[1]["notes"] == "Covered by Brucks, Debbie (KC3KEO)"
    assert [p["membership_year"] for p in own] == [2024]
    assert own[0]["inherited"] is False


def test_overlapping_secondary_payments_are_deleted_but_member_stays_current():
    conn = memory_db()
    primary = insert_member(conn, "Wilson", "Gary")
    secondary = insert_member(conn, "Wilson", "Jill")
    _pay(conn, primary, 2026)
    _pay(conn, primary, 2025)
    _pay(conn, secondary, 2025)
    _link(conn, secondary, primary)
    leftover = conn.execute("SELECT COUNT(*) FROM payments WHERE member_id = ?", (secondary,)).fetchone()
    assert int(leftover[0]) == 0
    repo = MemberListRepository(conn)
    filt = {
        "search": "",
        "membership_type_id": None,
        "arrl": "",
        "current_only": "yes",
        "membership_year": 2026,
        "sort_by": "first_name",
        "sort_dir": "asc",
    }
    names = {r["first_name"] for r in repo.list_rows_for_export(filt)}
    assert names == {"Gary", "Jill"}
    paid = {r["first_name"] for r in ReportsRepository(conn).list_paid_memberships(2026)}
    assert paid == {"Gary", "Jill"}


def test_roster_links_don_fritz_to_cindy_gerbavac():
    conn = memory_db()
    cindy = insert_member(conn, "Gerbavac", "Cindy")
    don = insert_member(conn, "Fritz", "Don")
    conn.execute("UPDATE members SET call_sign = ? WHERE id = ?", ("WA2GZT", cindy))
    conn.execute("UPDATE members SET call_sign = ? WHERE id = ?", ("KE2EWH", don))
    conn.commit()
    _pay(conn, cindy, 2026)
    _pay(conn, don, 2026)
    apply_roster_family_links(conn)
    for sid in delete_secondary_payments_covered_by_primary(conn, don):
        PaymentRepository(conn).sync_member_paid_through_from_payments(sid)
    conn.commit()
    row = conn.execute("SELECT family_primary_member_id FROM members WHERE id = ?", (don,)).fetchone()
    assert int(row["family_primary_member_id"]) == cindy
    leftover = conn.execute("SELECT COUNT(*) FROM payments WHERE member_id = ?", (don,)).fetchone()
    assert int(leftover[0]) == 0
    paid = {r["first_name"] for r in ReportsRepository(conn).list_paid_memberships(2026)}
    assert paid == {"Cindy", "Don"}
    rows = MemberRepository(conn).list_payments_for_member(don)
    assert [p["inherited"] for p in rows] == [True]
    assert rows[0]["notes"] == "Covered by Gerbavac, Cindy (WA2GZT)"


def test_cannot_delete_primary_with_secondaries():
    conn = memory_db()
    primary = insert_member(conn, "Brucks", "Debbie")
    secondary = insert_member(conn, "Brucks", "Glenn")
    _link(conn, secondary, primary)
    with pytest.raises(MemberHasFamilySecondaries):
        MemberRepository(conn).delete_member_by_id(primary)
    assert MemberRepository(conn).find_member_by_id(primary) is not None
    assert MemberRepository(conn).delete_member_by_id(secondary) is True


def test_delete_member_with_payments_succeeds():
    conn = memory_db()
    mid = insert_member(conn, "McTestFace", "Testy")
    _pay(conn, mid, 2026)
    assert conn.execute("SELECT COUNT(*) FROM payments WHERE member_id = ?", (mid,)).fetchone()[0] == 1
    assert MemberRepository(conn).delete_member_by_id(mid) is True
    assert conn.execute("SELECT id FROM members WHERE id = ?", (mid,)).fetchone() is None
    assert conn.execute("SELECT COUNT(*) FROM payments WHERE member_id = ?", (mid,)).fetchone()[0] == 0


def _edit_ctx(conn, form: dict) -> dict:
    return {"conn": conn, "session": {}, "form": form, "query": {}}


def test_setting_covered_by_without_confirm_keeps_current_year_payment():
    conn = memory_db()
    AppSettingsRepository(conn).set_current_membership_year(2026)
    primary = insert_member(conn, "Wilson", "Gary")
    secondary = insert_member(conn, "Wilson", "Jill")
    _pay(conn, secondary, 2026)
    form = member_create_form(
        conn,
        last_name="Wilson",
        first_name="Jill",
        family_primary_member_id=str(primary),
    )
    resp = handle_member_edit(_edit_ctx(conn, form), secondary)
    assert resp.status == 400
    years = [
        int(r["membership_year"])
        for r in conn.execute(
            "SELECT membership_year FROM payments WHERE member_id = ?",
            (secondary,),
        )
    ]
    assert years == [2026]
    linked = conn.execute(
        "SELECT family_primary_member_id FROM members WHERE id = ?",
        (secondary,),
    ).fetchone()
    assert linked["family_primary_member_id"] is None


def test_setting_covered_by_with_confirm_deletes_current_year_payment():
    conn = memory_db()
    AppSettingsRepository(conn).set_current_membership_year(2026)
    primary = insert_member(conn, "Wilson", "Gary")
    secondary = insert_member(conn, "Wilson", "Jill")
    _pay(conn, secondary, 2026)
    _pay(conn, secondary, 2024)
    form = member_create_form(
        conn,
        last_name="Wilson",
        first_name="Jill",
        family_primary_member_id=str(primary),
        confirm_delete_current_year_payment="1",
    )
    resp = handle_member_edit(_edit_ctx(conn, form), secondary)
    assert resp.status == 303
    years = [
        int(r["membership_year"])
        for r in conn.execute(
            "SELECT membership_year FROM payments WHERE member_id = ? ORDER BY membership_year",
            (secondary,),
        )
    ]
    assert years == [2024]


def test_new_covered_by_member_without_confirm_keeps_no_member():
    conn = memory_db()
    AppSettingsRepository(conn).set_current_membership_year(2026)
    primary = insert_member(conn, "Wilson", "Gary")
    _pay(conn, primary, 2026)
    form = member_create_form(
        conn,
        last_name="Wilson",
        first_name="Jill",
        call_sign="W2JILX",
        family_primary_member_id=str(primary),
        paid_for_year="2026",
    )
    resp = handle_member_new_post(_edit_ctx(conn, form))
    assert resp.status == 400
    assert conn.execute("SELECT id FROM members WHERE call_sign = 'W2JILX'").fetchone() is None


def test_new_covered_by_member_with_confirm_skips_current_year_payment():
    conn = memory_db()
    AppSettingsRepository(conn).set_current_membership_year(2026)
    primary = insert_member(conn, "Wilson", "Gary")
    _pay(conn, primary, 2026)
    form = member_create_form(
        conn,
        last_name="Wilson",
        first_name="Jill",
        call_sign="W2JILX",
        family_primary_member_id=str(primary),
        paid_for_year="2026",
        confirm_delete_current_year_payment="1",
    )
    resp = handle_member_new_post(_edit_ctx(conn, form))
    assert resp.status == 303
    mid = int(conn.execute("SELECT id FROM members WHERE call_sign = 'W2JILX'").fetchone()[0])
    own = conn.execute(
        "SELECT COUNT(*) FROM payments WHERE member_id = ? AND membership_year = 2026",
        (mid,),
    ).fetchone()
    assert int(own[0]) == 0


def _type_id(conn, name: str) -> int:
    ref = ReferenceDataRepository(conn)
    row = conn.execute("SELECT id FROM membership_types WHERE name = ? LIMIT 1", (name,)).fetchone()
    if row is None:
        ref.create_membership_type(name)
        row = conn.execute("SELECT id FROM membership_types WHERE name = ? LIMIT 1", (name,)).fetchone()
    return int(row["id"])


def _set_type(conn, member_id: int, type_id: int) -> None:
    conn.execute("UPDATE members SET membership_type_id = ? WHERE id = ?", (type_id, member_id))
    conn.commit()


def test_family_primary_options_only_current_eligible_members():
    conn = memory_db()
    AppSettingsRepository(conn).set_current_membership_year(2026)
    individual = _type_id(conn, "Individual")
    life = _type_id(conn, "Life")
    emeritus = _type_id(conn, "Emeritus")
    new_ham = _type_id(conn, "New Ham")
    student = _type_id(conn, "Student")

    self_id = insert_member(conn, "Able", "Ann")
    current = insert_member(conn, "Baker", "Bob")
    unpaid = insert_member(conn, "Clark", "Cara")
    life_id = insert_member(conn, "Davis", "Dan")
    emeritus_id = insert_member(conn, "Evans", "Eve")
    new_ham_id = insert_member(conn, "Foster", "Fay")
    student_id = insert_member(conn, "Green", "Gus")
    deceased = insert_member(conn, "Hall", "Hal")
    lapsed_selected = insert_member(conn, "Inman", "Ivy")
    secondary = insert_member(conn, "Baker", "Jill")

    for mid, tid in (
        (self_id, individual),
        (current, individual),
        (unpaid, individual),
        (life_id, life),
        (emeritus_id, emeritus),
        (new_ham_id, new_ham),
        (student_id, student),
        (deceased, individual),
        (lapsed_selected, individual),
        (secondary, individual),
    ):
        _set_type(conn, mid, tid)

    for mid in (self_id, current, life_id, emeritus_id, new_ham_id, student_id, deceased):
        _pay(conn, mid, 2026)
    _pay(conn, lapsed_selected, 2025)
    _link(conn, secondary, current)
    conn.execute("UPDATE members SET deceased = 1 WHERE id = ?", (deceased,))
    conn.commit()

    ids = {item["id"] for item in MemberRepository(conn).list_family_primary_options(self_id)}
    assert current in ids
    bob = next(item for item in MemberRepository(conn).list_family_primary_options(self_id) if item["id"] == current)
    assert bob["last_name"] == "Baker"
    assert bob["first_name"] == "Bob"
    assert "call_sign" in bob
    assert "label" in bob
    assert self_id not in ids
    assert unpaid not in ids
    assert life_id not in ids
    assert emeritus_id not in ids
    assert new_ham_id not in ids
    assert student_id not in ids
    assert deceased not in ids
    assert lapsed_selected not in ids
    assert secondary not in ids

    included = {
        item["id"]
        for item in MemberRepository(conn).list_family_primary_options(
            self_id, include_primary_id=lapsed_selected
        )
    }
    assert lapsed_selected in included
    assert current in included
    assert life_id not in included


def test_covered_by_picker_markup_uses_search_dialog():
    field = view.render(
        "_covered_by_field.html",
        covered_by_value=2,
        covered_by_label="Baker, Bob (K2BOB)",
        family_primary_options=[],
    )
    assert 'name="family_primary_member_id"' in field
    assert 'id="covered-by-id"' in field
    assert 'name="confirm_delete_current_year_payment"' in field
    assert 'id="covered-by-open"' in field
    assert 'id="covered-by-search"' not in field
    assert "<select" not in field
    dialog = view.render(
        "_covered_by_dialog.html",
        family_primary_options=[
            {
                "id": 2,
                "last_name": "Baker",
                "first_name": "Bob",
                "call_sign": "K2BOB",
                "label": "Baker, Bob (K2BOB)",
            }
        ],
    )
    assert 'id="covered-by-dialog"' in dialog
    assert 'id="covered-by-search"' in dialog
    assert "Last name" in dialog
    assert "First name" in dialog
    assert "Call sign" in dialog
    assert "K2BOB" in dialog
    assert "covered-by-results" in dialog
