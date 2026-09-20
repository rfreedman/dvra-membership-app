"""Apply schema.sql and incremental migrations."""

from __future__ import annotations

import sqlite3
from datetime import date

from dvra.app_settings import (
    DEFAULT_NEW_HAM_EXTENSION_START,
    DEFAULT_NEW_MEMBER_EXTENSION_START,
    KEY_NEW_HAM_EXTENSION_START,
    KEY_NEW_MEMBER_EXTENSION_START,
)
from dvra.new_ham import NEW_HAM_TYPE_NAME
from dvra.paths import SCHEMA_PATH

# Bump when schema.sql or migrate_* logic changes so ensure() re-runs.
SCHEMA_USER_VERSION = 12


def ensure(conn: sqlite3.Connection) -> None:
    current = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if current >= SCHEMA_USER_VERSION:
        return
    if not SCHEMA_PATH.is_file():
        raise RuntimeError(f"Missing schema file: {SCHEMA_PATH}")
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    for stmt in split_statements(sql):
        if stmt:
            conn.execute(stmt)
    migrate_drop_license_and_membership_labels(conn)
    migrate_app_settings_and_payment_membership_year(conn)
    migrate_member_notes(conn)
    migrate_member_nickname_and_qrz_email(conn)
    migrate_seed_new_ham_membership_type(conn)
    migrate_join_extension_settings(conn)
    migrate_remove_regular_membership_type(conn)
    migrate_member_family_primary(conn)
    migrate_roster_family_links_and_new_ham(conn)
    migrate_delete_secondary_payments_covered_by_primary(conn)
    migrate_member_deceased(conn)
    conn.execute(f"PRAGMA user_version = {SCHEMA_USER_VERSION}")
    conn.commit()


def migrate_drop_license_and_membership_labels(conn: sqlite3.Connection) -> None:
    for table in ("license_classes", "membership_types"):
        if sqlite_table_has_column(conn, table, "label"):
            conn.execute(f"ALTER TABLE {table} DROP COLUMN label")


def migrate_app_settings_and_payment_membership_year(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY NOT NULL,
            value TEXT NOT NULL
        )
        """
    )
    row = conn.execute(
        "SELECT 1 FROM app_settings WHERE key = ? LIMIT 1",
        ("current_membership_year",),
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?)",
            ("current_membership_year", date.today().strftime("%Y")),
        )

    if not sqlite_table_has_column(conn, "payments", "membership_year"):
        conn.execute("ALTER TABLE payments ADD COLUMN membership_year INTEGER")
        conn.execute(
            """
            UPDATE payments SET membership_year = CAST(strftime('%Y', paid_through) AS INTEGER)
            WHERE membership_year IS NULL AND paid_through IS NOT NULL AND paid_through != ''
            """
        )
        conn.execute(
            """
            UPDATE payments SET membership_year = CAST(strftime('%Y', 'now') AS INTEGER)
            WHERE membership_year IS NULL
            """
        )

    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_payments_membership_year ON payments (membership_year)"
    )


def migrate_member_notes(conn: sqlite3.Connection) -> None:
    if not sqlite_table_has_column(conn, "members", "notes"):
        conn.execute("ALTER TABLE members ADD COLUMN notes TEXT")


def migrate_member_nickname_and_qrz_email(conn: sqlite3.Connection) -> None:
    if not sqlite_table_has_column(conn, "members", "nickname"):
        conn.execute("ALTER TABLE members ADD COLUMN nickname TEXT")
    if not sqlite_table_has_column(conn, "members", "qrz_email"):
        conn.execute("ALTER TABLE members ADD COLUMN qrz_email VARCHAR(320)")


def migrate_join_extension_settings(conn: sqlite3.Connection) -> None:
    defaults = (
        (KEY_NEW_MEMBER_EXTENSION_START, DEFAULT_NEW_MEMBER_EXTENSION_START),
        (KEY_NEW_HAM_EXTENSION_START, DEFAULT_NEW_HAM_EXTENSION_START),
    )
    for key, value in defaults:
        row = conn.execute(
            "SELECT 1 FROM app_settings WHERE key = ? LIMIT 1",
            (key,),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO app_settings (key, value) VALUES (?, ?)",
                (key, value),
            )


def migrate_remove_regular_membership_type(conn: sqlite3.Connection) -> None:
    regular = conn.execute(
        "SELECT id FROM membership_types WHERE name = 'Regular' LIMIT 1",
    ).fetchone()
    if regular is None:
        return
    regular_id = int(regular[0])
    individual = conn.execute(
        "SELECT id FROM membership_types WHERE name = 'Individual' LIMIT 1",
    ).fetchone()
    if individual is not None:
        individual_id = int(individual[0])
        conn.execute(
            "UPDATE members SET membership_type_id = ? WHERE membership_type_id = ?",
            (individual_id, regular_id),
        )
        conn.execute(
            "UPDATE payments SET membership_type_id = ? WHERE membership_type_id = ?",
            (individual_id, regular_id),
        )
    conn.execute("DELETE FROM membership_types WHERE id = ?", (regular_id,))


def migrate_member_deceased(conn: sqlite3.Connection) -> None:
    if not sqlite_table_has_column(conn, "members", "deceased"):
        conn.execute("ALTER TABLE members ADD COLUMN deceased INTEGER NOT NULL DEFAULT 0")


def migrate_member_family_primary(conn: sqlite3.Connection) -> None:
    if not sqlite_table_has_column(conn, "members", "family_primary_member_id"):
        conn.execute(
            "ALTER TABLE members ADD COLUMN family_primary_member_id INTEGER REFERENCES members(id)"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_members_family_primary_member_id ON members (family_primary_member_id)"
    )


def migrate_delete_secondary_payments_covered_by_primary(conn: sqlite3.Connection) -> None:
    from dvra.family import delete_secondary_payments_covered_by_primary
    from dvra.payments import PaymentRepository

    secondary_ids = delete_secondary_payments_covered_by_primary(conn)
    pay = PaymentRepository(conn)
    for member_id in secondary_ids:
        pay.sync_member_paid_through_from_payments(member_id)


def migrate_roster_family_links_and_new_ham(conn: sqlite3.Connection) -> None:
    from dvra.family import MASON_SHARMA_CALL, NEW_HAM_APPROXIMATE_NOTE, apply_roster_family_links

    apply_roster_family_links(conn)

    nh = conn.execute(
        "SELECT id FROM membership_types WHERE name = ? LIMIT 1",
        (NEW_HAM_TYPE_NAME,),
    ).fetchone()
    if nh is None:
        return
    nh_id = int(nh[0])
    member = conn.execute(
        "SELECT id, paid_through FROM members WHERE upper(call_sign) = upper(?) LIMIT 1",
        (MASON_SHARMA_CALL,),
    ).fetchone()
    if member is None:
        return
    member_id = int(member[0])
    conn.execute(
        "UPDATE members SET membership_type_id = ? WHERE id = ?",
        (nh_id, member_id),
    )
    has_2026 = conn.execute(
        "SELECT 1 FROM payments WHERE member_id = ? AND membership_year = 2026 LIMIT 1",
        (member_id,),
    ).fetchone()
    if has_2026 is None:
        conn.execute(
            """
            INSERT INTO payments (
                member_id, payment_date, paid_through, membership_year,
                membership_type_id, notes, form_number, created_at
            ) VALUES (?, '2026-01-01', '2026-12-31', 2026, ?, ?, NULL, CURRENT_TIMESTAMP)
            """,
            (member_id, nh_id, NEW_HAM_APPROXIMATE_NOTE),
        )
        if member["paid_through"] in (None, ""):
            conn.execute(
                "UPDATE members SET paid_through = '2026-12-31' WHERE id = ?",
                (member_id,),
            )


def migrate_seed_new_ham_membership_type(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO membership_types (name)
        SELECT ?
        WHERE NOT EXISTS (SELECT 1 FROM membership_types WHERE name = ?)
        """,
        (NEW_HAM_TYPE_NAME, NEW_HAM_TYPE_NAME),
    )


def sqlite_table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    allowed = {"license_classes", "membership_types", "payments", "app_settings", "members"}
    if table not in allowed:
        return False
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def split_statements(sql: str) -> list[str]:
    out: list[str] = []
    buf = ""
    for line in sql.splitlines():
        t = line.strip()
        if t == "" or t.startswith("--"):
            continue
        buf += " " + line
        if line.rstrip().endswith(";"):
            out.append(buf.strip().rstrip(";").strip())
            buf = ""
    buf = buf.strip()
    if buf:
        out.append(buf)
    return out
