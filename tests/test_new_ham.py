from __future__ import annotations

import sqlite3
from datetime import date
from unittest.mock import patch

from dvra import new_ham
from dvra.pages.members import handle_member_new_post, handle_payment_edit, handle_payment_new
from dvra.payments import PaymentRepository
from dvra.reference_data import ReferenceDataRepository
from dvra.schema import SCHEMA_USER_VERSION, ensure

from tests.conftest import insert_member, member_create_form, memory_db


def _type_id(conn: sqlite3.Connection, name: str) -> int:
    return int(conn.execute("SELECT id FROM membership_types WHERE name = ?", (name,)).fetchone()[0])


def _individual_id(conn: sqlite3.Connection) -> int:
    ref = ReferenceDataRepository(conn)
    if conn.execute("SELECT 1 FROM membership_types WHERE name = 'Individual' LIMIT 1").fetchone() is None:
        ref.create_membership_type("Individual")
    return _type_id(conn, "Individual")


def _pay_data(year: int, type_id: int | None, notes: str | None = None) -> dict:
    return {
        "payment_date": f"{year}-01-15",
        "membership_year": year,
        "membership_type_id": type_id,
        "notes": notes,
        "form_number": None,
    }


def _ctx(conn: sqlite3.Connection, form: dict) -> dict:
    return {"conn": conn, "session": {}, "form": form, "query": {}}


def test_schema_ensure_seeds_new_ham():
    conn = memory_db()
    row = conn.execute(
        "SELECT id, name FROM membership_types WHERE name = ?",
        (new_ham.NEW_HAM_TYPE_NAME,),
    ).fetchone()
    assert row is not None
    assert str(row["name"]) == new_ham.NEW_HAM_TYPE_NAME
    assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == SCHEMA_USER_VERSION


def test_schema_seeds_new_ham_when_upgrading_from_v4():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE membership_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(64) NOT NULL,
            CONSTRAINT uq_membership_type_name UNIQUE (name)
        )
        """
    )
    conn.execute("PRAGMA user_version = 4")
    conn.commit()
    ensure(conn)
    assert conn.execute(
        "SELECT 1 FROM membership_types WHERE name = ?",
        (new_ham.NEW_HAM_TYPE_NAME,),
    ).fetchone()
    assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == SCHEMA_USER_VERSION


@patch("dvra.pages.members._new_member_join_date", return_value=date(2026, 6, 1))
def test_new_member_new_ham_sets_free_year_payment_note(_mock_join):
    conn = memory_db()
    nh = new_ham.find_type_id(conn)
    assert nh is not None
    ctx = _ctx(conn, member_create_form(conn, membership_type_id=nh, last_name="Ham", first_name="Newbie"))
    resp = handle_member_new_post(ctx)
    assert resp.status == 303
    row = conn.execute(
        "SELECT membership_type_id, notes, membership_year FROM payments LIMIT 1"
    ).fetchone()
    assert int(row["membership_type_id"]) == nh
    assert row["notes"] == new_ham.NEW_HAM_FREE_YEAR_NOTE
    assert int(row["membership_year"]) == 2026
    member = conn.execute("SELECT membership_type_id FROM members LIMIT 1").fetchone()
    assert int(member["membership_type_id"]) == nh


@patch("dvra.pages.members._new_member_join_date", return_value=date(2026, 6, 1))
def test_new_member_other_type_has_null_payment_notes(_mock_join):
    conn = memory_db()
    individual = _individual_id(conn)
    ctx = _ctx(
        conn,
        member_create_form(
            conn,
            membership_type_id=individual,
            last_name="Member",
            first_name="Individual",
        ),
    )
    resp = handle_member_new_post(ctx)
    assert resp.status == 303
    row = conn.execute("SELECT membership_type_id, notes FROM payments LIMIT 1").fetchone()
    assert int(row["membership_type_id"]) == individual
    assert row["notes"] is None


def test_second_new_ham_payment_is_rejected():
    conn = memory_db()
    nh = new_ham.find_type_id(conn)
    assert nh is not None
    mid = insert_member(conn)
    PaymentRepository(conn).insert_payment(mid, _pay_data(2026, nh))
    ctx = _ctx(
        conn,
        {
            "payment_date": "2027-01-15",
            "membership_year": "2027",
            "membership_type": str(nh),
        },
    )
    resp = handle_payment_new(ctx, mid)
    assert resp.status == 303
    assert ctx["session"]["dvra_flash_payment_error"] == new_ham.NEW_HAM_RENEWAL_ERROR
    n = int(conn.execute("SELECT COUNT(*) FROM payments WHERE member_id = ?", (mid,)).fetchone()[0])
    assert n == 1


def test_blank_membership_type_rejected_after_new_ham():
    conn = memory_db()
    nh = new_ham.find_type_id(conn)
    assert nh is not None
    mid = insert_member(conn)
    PaymentRepository(conn).insert_payment(mid, _pay_data(2026, nh))
    ctx = _ctx(
        conn,
        {"payment_date": "2027-01-15", "membership_year": "2027", "membership_type": ""},
    )
    handle_payment_new(ctx, mid)
    assert ctx["session"]["dvra_flash_payment_error"] == new_ham.NEW_HAM_RENEWAL_ERROR
    n = int(conn.execute("SELECT COUNT(*) FROM payments WHERE member_id = ?", (mid,)).fetchone()[0])
    assert n == 1


def test_editing_original_new_ham_payment_still_works():
    conn = memory_db()
    nh = new_ham.find_type_id(conn)
    assert nh is not None
    mid = insert_member(conn)
    PaymentRepository(conn).insert_payment(mid, _pay_data(2026, nh, "keep"))
    pid = int(conn.execute("SELECT id FROM payments WHERE member_id = ?", (mid,)).fetchone()[0])
    ctx = _ctx(
        conn,
        {
            "payment_date": "2026-02-01",
            "membership_year": "2026",
            "membership_type": str(nh),
            "notes": "keep",
        },
    )
    resp = handle_payment_edit(ctx, pid)
    assert resp.status == 303
    assert "dvra_flash_payment_error" not in ctx["session"]
    row = conn.execute("SELECT payment_date, membership_type_id FROM payments WHERE id = ?", (pid,)).fetchone()
    assert str(row["payment_date"]) == "2026-02-01"
    assert int(row["membership_type_id"]) == nh


def test_later_non_new_ham_payment_updates_member_type():
    conn = memory_db()
    nh = new_ham.find_type_id(conn)
    assert nh is not None
    individual = _individual_id(conn)
    mid = insert_member(conn)
    pay = PaymentRepository(conn)
    pay.insert_payment(mid, _pay_data(2026, nh))
    assert int(conn.execute("SELECT membership_type_id FROM members WHERE id = ?", (mid,)).fetchone()[0]) == nh
    ctx = _ctx(
        conn,
        {
            "payment_date": "2027-01-15",
            "membership_year": "2027",
            "membership_type": str(individual),
        },
    )
    resp = handle_payment_new(ctx, mid)
    assert resp.status == 303
    assert "dvra_flash_payment_error" not in ctx["session"]
    n = int(conn.execute("SELECT COUNT(*) FROM payments WHERE member_id = ?", (mid,)).fetchone()[0])
    assert n == 2
    assert int(conn.execute("SELECT membership_type_id FROM members WHERE id = ?", (mid,)).fetchone()[0]) == individual


def test_admin_cannot_rename_or_delete_new_ham():
    conn = memory_db()
    nh = new_ham.find_type_id(conn)
    assert nh is not None
    ref = ReferenceDataRepository(conn)
    try:
        ref.update_membership_type(nh, "Not New Ham")
        raised_rename = False
    except RuntimeError as e:
        raised_rename = True
        assert str(e) == new_ham.CANNOT_RENAME_NEW_HAM
    assert raised_rename
    still = conn.execute("SELECT name FROM membership_types WHERE id = ?", (nh,)).fetchone()
    assert str(still["name"]) == new_ham.NEW_HAM_TYPE_NAME
    try:
        ref.delete_membership_type_or_fail(nh)
        raised_delete = False
    except RuntimeError as e:
        raised_delete = True
        assert str(e) == new_ham.CANNOT_DELETE_NEW_HAM
    assert raised_delete
    assert conn.execute(
        "SELECT 1 FROM membership_types WHERE name = ?",
        (new_ham.NEW_HAM_TYPE_NAME,),
    ).fetchone()
