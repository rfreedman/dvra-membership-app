from __future__ import annotations

from dvra import member_form_validation
from dvra import normalizer
from dvra.pages.members import handle_member_edit, handle_member_new_post
from dvra.reference_data import ReferenceDataRepository

from tests.conftest import ensure_member_form_reference_data, insert_member, member_create_form, memory_db


def _ctx(conn, form: dict) -> dict:
    return {"conn": conn, "session": {}, "form": form, "query": {}}


def test_validate_requires_email_and_phone():
    conn = memory_db()
    tech_id, _, mt_id = ensure_member_form_reference_data(conn)
    body = {
        "last_name": "A",
        "first_name": "B",
        "license_class": str(tech_id),
        "membership_type": str(mt_id),
        "call_sign": "K1ZZZ",
        "email": "",
        "phone": "",
        "address_street": "1 St",
        "address_city": "City",
        "address_state": "NJ",
        "address_zip": "08608",
        "arrl_member": "no",
    }
    row = normalizer.member_create_from_form(body, None)
    assert member_form_validation.validate_member_row(conn, row, body, require_paid_year=False, paid_year=None) == (
        "Email is required."
    )


def test_unlicensed_clears_call_sign_on_save():
    conn = memory_db()
    _, unlic_id, mt_id = ensure_member_form_reference_data(conn)
    mid = insert_member(conn)
    conn.execute(
        "UPDATE members SET call_sign = 'W1AW', license_class_id = ?, membership_type_id = ?, "
        "email = 'a@b.com', phone = '609-555-1212', address_street = '1 St', address_city = 'X', "
        "address_state = 'NJ', address_zip = '08608' WHERE id = ?",
        (unlic_id, mt_id, mid),
    )
    conn.commit()
    form = member_create_form(
        conn,
        license_class_id=unlic_id,
        call_sign="SHOULD_CLEAR",
        last_name="Pay",
        first_name="Tester",
    )
    resp = handle_member_edit(_ctx(conn, form), mid)
    assert resp.status == 303
    cs = conn.execute("SELECT call_sign FROM members WHERE id = ?", (mid,)).fetchone()[0]
    assert cs is None


def test_new_member_post_requires_paid_year():
    conn = memory_db()
    form = member_create_form(conn)
    del form["paid_for_year"]
    resp = handle_member_new_post(_ctx(conn, form))
    assert resp.status == 400


def test_migrate_removes_regular_type():
    conn = memory_db()
    ref = ReferenceDataRepository(conn)
    ref.create_membership_type("Individual")
    ref.create_membership_type("Regular")
    regular_id = int(conn.execute("SELECT id FROM membership_types WHERE name = 'Regular'").fetchone()[0])
    individual_id = int(conn.execute("SELECT id FROM membership_types WHERE name = 'Individual'").fetchone()[0])
    mid = insert_member(conn)
    conn.execute("UPDATE members SET membership_type_id = ? WHERE id = ?", (regular_id, mid))
    conn.commit()
    from dvra.schema import migrate_remove_regular_membership_type

    migrate_remove_regular_membership_type(conn)
    conn.commit()
    assert conn.execute("SELECT 1 FROM membership_types WHERE name = 'Regular'").fetchone() is None
    row = conn.execute("SELECT membership_type_id FROM members WHERE id = ?", (mid,)).fetchone()
    assert int(row[0]) == individual_id
