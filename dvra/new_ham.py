"""New Ham complimentary first-year membership type."""

from __future__ import annotations

import sqlite3

NEW_HAM_TYPE_NAME = "New Ham"
NEW_HAM_FREE_YEAR_NOTE = "New Ham - first year free."
NEW_HAM_RENEWAL_ERROR = (
    "New Ham membership is only available once. The second year is not free; "
    "a membership payment must be made, and a different membership type must be chosen."
)
NEW_HAM_PAYMENTS_NOTICE = (
    "This member already used their free New Ham year. The second year is not free; "
    "a membership payment must be made, and a different membership type must be chosen."
)
NEW_HAM_CONVERT_CONFIRM = (
    "New Ham is a one-time free first-year membership. "
    "Are you sure you want to change this member to New Ham?"
)
CANNOT_RENAME_NEW_HAM = "Cannot rename the New Ham membership type."
CANNOT_DELETE_NEW_HAM = "Cannot delete the New Ham membership type."


def find_type_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute(
        "SELECT id FROM membership_types WHERE name = ? LIMIT 1",
        (NEW_HAM_TYPE_NAME,),
    ).fetchone()
    if row is None:
        return None
    return int(row["id"])


def is_protected_type_id(conn: sqlite3.Connection, type_id: int) -> bool:
    found = find_type_id(conn)
    return found is not None and int(type_id) == found


def member_has_new_ham_payment(
    conn: sqlite3.Connection, member_id: int, exclude_payment_id: int | None = None
) -> bool:
    type_id = find_type_id(conn)
    if type_id is None:
        return False
    if exclude_payment_id is not None and exclude_payment_id > 0:
        row = conn.execute(
            """
            SELECT 1 FROM payments
             WHERE member_id = ? AND membership_type_id = ? AND id != ?
             LIMIT 1
            """,
            (member_id, type_id, exclude_payment_id),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT 1 FROM payments
             WHERE member_id = ? AND membership_type_id = ?
             LIMIT 1
            """,
            (member_id, type_id),
        ).fetchone()
    return row is not None


def initial_payment_notes(conn: sqlite3.Connection, membership_type_id: int | None) -> str | None:
    new_ham_id = find_type_id(conn)
    if new_ham_id is not None and membership_type_id == new_ham_id:
        return NEW_HAM_FREE_YEAR_NOTE
    return None


def payment_membership_type_error(
    conn: sqlite3.Connection,
    member_id: int,
    membership_type_id: int | None,
    exclude_payment_id: int | None = None,
) -> str | None:
    """Error if this payment would violate the one-New-Ham-payment rule."""
    new_ham_id = find_type_id(conn)
    if new_ham_id is None:
        return None
    if not member_has_new_ham_payment(conn, member_id, exclude_payment_id):
        return None
    if membership_type_id is None or membership_type_id == new_ham_id:
        return NEW_HAM_RENEWAL_ERROR
    return None
