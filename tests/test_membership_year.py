from __future__ import annotations

import sqlite3

from dvra.app_settings import AppSettingsRepository
from dvra.membership_year import paid_through_iso
from dvra.payments import PaymentRepository
from dvra.schema import ensure

from tests.conftest import insert_member, memory_db


def test_settings_seeded_and_settable():
    conn = memory_db()
    settings = AppSettingsRepository(conn)
    y = settings.get_current_membership_year()
    assert y >= 2000
    settings.set_current_membership_year(2031)
    assert settings.get_current_membership_year() == 2031


def test_insert_payment_sets_paid_through_dec31():
    conn = memory_db()
    member_id = insert_member(conn)
    PaymentRepository(conn).insert_payment(
        member_id,
        {
            "payment_date": "2026-03-01",
            "membership_year": 2026,
            "membership_type_id": None,
            "notes": None,
            "form_number": None,
        },
    )
    row = conn.execute("SELECT paid_through, membership_year FROM payments LIMIT 1").fetchone()
    assert row["paid_through"] == "2026-12-31"
    assert int(row["membership_year"]) == 2026
    assert paid_through_iso(2026) == "2026-12-31"


def test_next_free_membership_year_after_duplicates():
    conn = memory_db()
    member_id = insert_member(conn)
    payments = PaymentRepository(conn)
    data = {
        "payment_date": "2026-01-01",
        "membership_year": 2026,
        "membership_type_id": None,
        "notes": None,
        "form_number": None,
    }
    payments.insert_payment(member_id, data)
    assert payments.member_has_payment_for_year(member_id, 2026)
    assert payments.next_free_membership_year(member_id, 2026) == 2027
    data["membership_year"] = 2027
    payments.insert_payment(member_id, data)
    assert payments.next_free_membership_year(member_id, 2026) == 2028


def test_migration_backfills_membership_year_from_paid_through():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            payment_date TEXT NOT NULL,
            paid_through TEXT NOT NULL,
            membership_type_id INTEGER,
            notes TEXT,
            form_number VARCHAR(64),
            created_at TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO payments (member_id, payment_date, paid_through, created_at)
        VALUES (1, '2024-05-01', '2024-12-31', CURRENT_TIMESTAMP)
        """
    )
    ensure(conn)
    y = int(conn.execute("SELECT membership_year FROM payments LIMIT 1").fetchone()[0])
    assert y == 2024
    setting = int(
        conn.execute(
            "SELECT value FROM app_settings WHERE key = 'current_membership_year'"
        ).fetchone()[0]
    )
    assert setting >= 2000
