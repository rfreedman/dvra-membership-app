from __future__ import annotations

import sqlite3

from dvra.schema import ensure


def memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure(conn)
    return conn


def ensure_member_form_reference_data(conn: sqlite3.Connection) -> tuple[int, int, int]:
    """Return (technician_license_id, unlicensed_license_id, default_membership_type_id)."""
    from dvra import new_ham
    from dvra.reference_data import ReferenceDataRepository

    if conn.row_factory is None:
        conn.row_factory = sqlite3.Row
    ref = ReferenceDataRepository(conn)
    if conn.execute("SELECT 1 FROM license_classes WHERE name = 'Technician' LIMIT 1").fetchone() is None:
        ref.create_license_class("Technician")
    if conn.execute("SELECT 1 FROM license_classes WHERE name = 'Unlicensed' LIMIT 1").fetchone() is None:
        ref.create_license_class("Unlicensed")
    tech_id = int(conn.execute("SELECT id FROM license_classes WHERE name = 'Technician'").fetchone()[0])
    unlic_id = int(conn.execute("SELECT id FROM license_classes WHERE name = 'Unlicensed'").fetchone()[0])
    nh = new_ham.find_type_id(conn)
    if nh is not None:
        mt_id = nh
    else:
        if conn.execute("SELECT 1 FROM membership_types LIMIT 1").fetchone() is None:
            ref.create_membership_type("Individual")
        mt_id = int(conn.execute("SELECT id FROM membership_types ORDER BY id LIMIT 1").fetchone()[0])
    return tech_id, unlic_id, mt_id


def member_create_form(conn: sqlite3.Connection, **overrides) -> dict:
    tech_id, _unlic, mt_id = ensure_member_form_reference_data(conn)
    base = {
        "last_name": "Test",
        "first_name": "User",
        "call_sign": "K1ABC",
        "email": "user@example.com",
        "phone": "6095551212",
        "address_street": "1 Main St",
        "address_city": "Trenton",
        "address_state": "NJ",
        "address_zip": "08608",
        "license_class": str(tech_id),
        "membership_type": str(mt_id),
        "arrl_member": "no",
        "paid_for_year": "2026",
    }
    for key, val in overrides.items():
        if key == "membership_type_id":
            base["membership_type"] = str(val)
        elif key == "license_class_id":
            base["license_class"] = str(val)
        else:
            base[key] = val
    return base


def insert_member(conn: sqlite3.Connection, last_name: str = "Pay", first_name: str = "Tester") -> int:
    cur = conn.execute(
        """
        INSERT INTO members (last_name, first_name, arrl_member, created_at, updated_at)
        VALUES (?, ?, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (last_name, first_name),
    )
    conn.commit()
    return int(cur.lastrowid)
