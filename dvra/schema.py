"""Apply schema.sql and incremental migrations."""

from __future__ import annotations

import sqlite3
from datetime import date

from dvra.paths import SCHEMA_PATH


def ensure(conn: sqlite3.Connection) -> None:
    if not SCHEMA_PATH.is_file():
        raise RuntimeError(f"Missing schema file: {SCHEMA_PATH}")
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    for stmt in split_statements(sql):
        if stmt:
            conn.execute(stmt)
    migrate_drop_license_and_membership_labels(conn)
    migrate_app_settings_and_payment_membership_year(conn)
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


def sqlite_table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    allowed = {"license_classes", "membership_types", "payments", "app_settings"}
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
