"""License class reference helpers."""

from __future__ import annotations

import sqlite3

UNLICENSED_CLASS_NAME = "Unlicensed"


def find_unlicensed_class_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute(
        "SELECT id FROM license_classes WHERE name = ? LIMIT 1",
        (UNLICENSED_CLASS_NAME,),
    ).fetchone()
    if row is None:
        return None
    return int(row[0])


def is_unlicensed_license_class_id(
    conn: sqlite3.Connection, license_class_id: int | None
) -> bool:
    if license_class_id is None:
        return False
    unlicensed_id = find_unlicensed_class_id(conn)
    return unlicensed_id is not None and license_class_id == unlicensed_id
