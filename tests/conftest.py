from __future__ import annotations

import sqlite3

from dvra.schema import ensure


def memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure(conn)
    return conn


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
