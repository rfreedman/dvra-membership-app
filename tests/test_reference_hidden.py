from __future__ import annotations

import sqlite3

from dvra.pages.admin import handle_admin_get, handle_license_hide, handle_mt_unhide
from dvra.pages.members import handle_member_edit, handle_member_new_post, handle_payment_new
from dvra.reference_data import (
    CANNOT_DELETE_REFERENCED_LICENSE,
    CANNOT_DELETE_REFERENCED_TYPE,
    HIDDEN_LICENSE_CLASS,
    HIDDEN_MEMBERSHIP_TYPE,
    ReferenceDataRepository,
)
from dvra.schema import SCHEMA_USER_VERSION, ensure, sqlite_table_has_column

from tests.conftest import ensure_member_form_reference_data, insert_member, member_create_form, memory_db


def _admin_ctx(conn: sqlite3.Connection, form: dict | None = None) -> dict:
    return {
        "conn": conn,
        "session": {"role": "admin", "user_id": 1, "username": "admin"},
        "form": form or {},
        "query": {},
    }


def _member_ctx(conn: sqlite3.Connection, form: dict) -> dict:
    return {"conn": conn, "session": {}, "form": form, "query": {}}


def _create_type(conn: sqlite3.Connection, name: str) -> int:
    ref = ReferenceDataRepository(conn)
    ref.create_membership_type(name)
    return int(conn.execute("SELECT id FROM membership_types WHERE name = ?", (name,)).fetchone()[0])


def _create_license(conn: sqlite3.Connection, name: str) -> int:
    ref = ReferenceDataRepository(conn)
    ref.create_license_class(name)
    return int(conn.execute("SELECT id FROM license_classes WHERE name = ?", (name,)).fetchone()[0])


def test_schema_migrates_hidden_columns_from_v12():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE license_classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(64) NOT NULL,
            CONSTRAINT uq_license_class_name UNIQUE (name)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE membership_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(64) NOT NULL,
            CONSTRAINT uq_membership_type_name UNIQUE (name)
        )
        """
    )
    conn.execute("INSERT INTO license_classes (name) VALUES ('Technician')")
    conn.execute("INSERT INTO membership_types (name) VALUES ('Individual')")
    conn.execute("PRAGMA user_version = 12")
    conn.commit()
    assert not sqlite_table_has_column(conn, "license_classes", "hidden")
    ensure(conn)
    assert sqlite_table_has_column(conn, "license_classes", "hidden")
    assert sqlite_table_has_column(conn, "membership_types", "hidden")
    assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == SCHEMA_USER_VERSION
    hidden = int(
        conn.execute("SELECT hidden FROM license_classes WHERE name = 'Technician'").fetchone()[0]
    )
    assert hidden == 0
    conn.close()


def test_delete_unreferenced_license_class():
    conn = memory_db()
    ref = ReferenceDataRepository(conn)
    lid = _create_license(conn, "Novice")
    assert ref.license_class_is_referenced(lid) is False
    ref.delete_license_class_or_fail(lid)
    assert conn.execute("SELECT 1 FROM license_classes WHERE id = ?", (lid,)).fetchone() is None


def test_referenced_license_class_cannot_delete_can_hide_and_unhide():
    conn = memory_db()
    tech_id, _, _ = ensure_member_form_reference_data(conn)
    mid = insert_member(conn)
    conn.execute("UPDATE members SET license_class_id = ? WHERE id = ?", (tech_id, mid))
    conn.commit()
    ref = ReferenceDataRepository(conn)
    assert ref.license_class_is_referenced(tech_id) is True
    try:
        ref.delete_license_class_or_fail(tech_id)
        raised = False
    except RuntimeError as e:
        raised = True
        assert str(e) == CANNOT_DELETE_REFERENCED_LICENSE
    assert raised
    ref.set_license_class_hidden(tech_id, True)
    assert ref.is_hidden_license_class(tech_id) is True
    ref.set_license_class_hidden(tech_id, False)
    assert ref.is_hidden_license_class(tech_id) is False


def test_delete_unreferenced_membership_type():
    conn = memory_db()
    ref = ReferenceDataRepository(conn)
    tid = _create_type(conn, "Associate")
    assert ref.membership_type_is_referenced(tid) is False
    ref.delete_membership_type_or_fail(tid)
    assert conn.execute("SELECT 1 FROM membership_types WHERE id = ?", (tid,)).fetchone() is None


def test_membership_type_referenced_by_member_cannot_delete():
    conn = memory_db()
    tid = _create_type(conn, "Family")
    mid = insert_member(conn)
    conn.execute("UPDATE members SET membership_type_id = ? WHERE id = ?", (tid, mid))
    conn.commit()
    ref = ReferenceDataRepository(conn)
    try:
        ref.delete_membership_type_or_fail(tid)
        raised = False
    except RuntimeError as e:
        raised = True
        assert str(e) == CANNOT_DELETE_REFERENCED_TYPE
    assert raised
    ref.set_membership_type_hidden(tid, True)
    assert ref.is_hidden_membership_type(tid) is True


def test_list_attachable_excludes_hidden_unless_included():
    conn = memory_db()
    ref = ReferenceDataRepository(conn)
    visible = _create_type(conn, "Visible Type")
    hidden = _create_type(conn, "Hidden Type")
    ref.set_membership_type_hidden(hidden, True)
    names = {r["name"] for r in ref.list_membership_types(include_hidden=False)}
    assert "Visible Type" in names
    assert "Hidden Type" not in names
    included = {r["id"] for r in ref.list_membership_types(include_hidden=False, include_ids=[hidden])}
    assert hidden in included
    assert visible in included
    admin_names = {r["name"] for r in ref.list_membership_types()}
    assert "Hidden Type" in admin_names


def test_new_member_cannot_attach_hidden_type_or_class():
    conn = memory_db()
    tech_id, _, mt_id = ensure_member_form_reference_data(conn)
    hidden_type = _create_type(conn, "Retired Type")
    hidden_class = _create_license(conn, "Retired Class")
    ref = ReferenceDataRepository(conn)
    ref.set_membership_type_hidden(hidden_type, True)
    ref.set_license_class_hidden(hidden_class, True)
    form = member_create_form(conn, membership_type_id=hidden_type, license_class_id=tech_id)
    resp = handle_member_new_post(_member_ctx(conn, form))
    assert resp.status == 400
    assert HIDDEN_MEMBERSHIP_TYPE.encode() in resp.body
    form = member_create_form(conn, membership_type_id=mt_id, license_class_id=hidden_class)
    resp = handle_member_new_post(_member_ctx(conn, form))
    assert resp.status == 400
    assert HIDDEN_LICENSE_CLASS.encode() in resp.body


def test_edit_keeps_hidden_assignment_but_rejects_switching_to_hidden():
    conn = memory_db()
    tech_id, _, mt_id = ensure_member_form_reference_data(conn)
    hidden_type = _create_type(conn, "Retired Type")
    other_hidden = _create_type(conn, "Other Retired")
    ref = ReferenceDataRepository(conn)
    ref.set_membership_type_hidden(hidden_type, True)
    ref.set_membership_type_hidden(other_hidden, True)
    mid = insert_member(conn)
    conn.execute(
        """
        UPDATE members SET license_class_id = ?, membership_type_id = ?,
            email = 'a@b.com', phone = '609-555-1212',
            address_street = '1 St', address_city = 'X', address_state = 'NJ', address_zip = '08608'
         WHERE id = ?
        """,
        (tech_id, hidden_type, mid),
    )
    conn.commit()
    keep = member_create_form(
        conn,
        license_class_id=tech_id,
        membership_type_id=hidden_type,
        last_name="Pay",
        first_name="Tester",
    )
    resp = handle_member_edit(_member_ctx(conn, keep), mid)
    assert resp.status == 303
    still = int(conn.execute("SELECT membership_type_id FROM members WHERE id = ?", (mid,)).fetchone()[0])
    assert still == hidden_type
    switch = member_create_form(
        conn,
        license_class_id=tech_id,
        membership_type_id=other_hidden,
        last_name="Pay",
        first_name="Tester",
    )
    resp = handle_member_edit(_member_ctx(conn, switch), mid)
    assert resp.status == 400
    assert HIDDEN_MEMBERSHIP_TYPE.encode() in resp.body
    leftover = int(conn.execute("SELECT membership_type_id FROM members WHERE id = ?", (mid,)).fetchone()[0])
    assert leftover == hidden_type
    visible_ok = member_create_form(
        conn,
        license_class_id=tech_id,
        membership_type_id=mt_id,
        last_name="Pay",
        first_name="Tester",
    )
    resp = handle_member_edit(_member_ctx(conn, visible_ok), mid)
    assert resp.status == 303


def test_new_payment_rejects_hidden_membership_type():
    conn = memory_db()
    hidden_type = _create_type(conn, "Retired Type")
    ReferenceDataRepository(conn).set_membership_type_hidden(hidden_type, True)
    mid = insert_member(conn)
    ctx = _member_ctx(
        conn,
        {
            "payment_date": "2026-01-15",
            "membership_year": "2026",
            "membership_type": str(hidden_type),
        },
    )
    resp = handle_payment_new(ctx, mid)
    assert resp.status == 303
    assert ctx["session"]["dvra_flash_payment_error"] == HIDDEN_MEMBERSHIP_TYPE
    assert int(conn.execute("SELECT COUNT(*) FROM payments WHERE member_id = ?", (mid,)).fetchone()[0]) == 0


def test_admin_shows_hide_for_referenced_and_delete_for_unused():
    conn = memory_db()
    unused = _create_license(conn, "Unused Class")
    used = _create_license(conn, "Used Class")
    mid = insert_member(conn)
    conn.execute("UPDATE members SET license_class_id = ? WHERE id = ?", (used, mid))
    conn.commit()
    unused_type = _create_type(conn, "Unused Type")
    used_type = _create_type(conn, "Used Type")
    conn.execute("UPDATE members SET membership_type_id = ? WHERE id = ?", (used_type, mid))
    conn.commit()
    ReferenceDataRepository(conn).set_membership_type_hidden(used_type, True)
    resp = handle_admin_get(_admin_ctx(conn))
    assert resp.status == 200
    html = resp.body.decode()
    assert f"/admin/license/{unused}/delete" in html
    assert f"/admin/license/{used}/hide" in html
    assert f"/admin/license/{used}/delete" not in html
    assert f"/admin/membership-type/{unused_type}/delete" in html
    assert f"/admin/membership-type/{used_type}/unhide" in html
    assert f"/admin/membership-type/{used_type}/delete" not in html
    assert "Hidden" in html


def test_admin_hide_and_unhide_handlers():
    conn = memory_db()
    lid = _create_license(conn, "Extra Class")
    tid = _create_type(conn, "Extra Type")
    hide = handle_license_hide(_admin_ctx(conn), lid)
    assert hide.status == 303
    assert ReferenceDataRepository(conn).is_hidden_license_class(lid) is True
    unhide = handle_mt_unhide(_admin_ctx(conn), tid)
    assert unhide.status == 303
    ReferenceDataRepository(conn).set_membership_type_hidden(tid, True)
    unhide = handle_mt_unhide(_admin_ctx(conn), tid)
    assert unhide.status == 303
    assert ReferenceDataRepository(conn).is_hidden_membership_type(tid) is False
