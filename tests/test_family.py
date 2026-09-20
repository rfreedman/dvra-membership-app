from __future__ import annotations

import pytest

from dvra.family import (
    apply_roster_family_links,
    delete_secondary_payments_covered_by_primary,
    validate_family_primary,
)
from dvra.member_list import MemberListRepository
from dvra.members import MemberHasFamilySecondaries, MemberRepository
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
