"""Family primary/secondary coverage (secondaries inherit the primary’s payments)."""

from __future__ import annotations

import sqlite3
from typing import Any

# Imported roster: secondary call -> primary call (one hop).
ROSTER_FAMILY_PRIMARY_BY_CALL: tuple[tuple[str, str], ...] = (
    ("KC3INP", "KC3KEO"),
    ("KE2DAE", "WO0LEN"),
    ("W2ECH", "W2SRH"),
    ("KC2NSY", "W2SRH"),
    ("AD2CE", "AD2CD"),
    ("KB3JYX", "K3CCN"),
    ("KB2UAL", "W2DHS"),
    ("W2JIL", "K2GW"),
    ("W1PAM", "K2GW"),
    ("KE2EWH", "WA2GZT"),
)

MASON_SHARMA_CALL = "KE2HLP"
NEW_HAM_APPROXIMATE_NOTE = "payment date approximate"


def apply_roster_family_links(conn: sqlite3.Connection) -> None:
    for secondary_call, primary_call in ROSTER_FAMILY_PRIMARY_BY_CALL:
        conn.execute(
            """
            UPDATE members
            SET family_primary_member_id = (
                SELECT p.id FROM members p
                WHERE upper(p.call_sign) = upper(?)
                LIMIT 1
            )
            WHERE upper(call_sign) = upper(?)
              AND family_primary_member_id IS NULL
              AND EXISTS (
                  SELECT 1 FROM members p
                  WHERE upper(p.call_sign) = upper(?)
              )
            """,
            (primary_call, secondary_call, primary_call),
        )


def covered_by_delete_current_payment_confirm(membership_year: int) -> str:
    return (
        f"This member has a payment for membership year {membership_year}. "
        "Continue to set Covered by and delete that payment? "
        "Cancel keeps the payment and does not change Covered by."
    )


def member_has_payment_for_year(
    conn: sqlite3.Connection, member_id: int, membership_year: int
) -> bool:
    row = conn.execute(
        "SELECT 1 FROM payments WHERE member_id = ? AND membership_year = ? LIMIT 1",
        (member_id, membership_year),
    ).fetchone()
    return row is not None


def delete_member_payments_for_year(
    conn: sqlite3.Connection, member_id: int, membership_year: int
) -> int:
    """Delete this member's own payments for one membership year. Returns rows deleted."""
    cur = conn.execute(
        "DELETE FROM payments WHERE member_id = ? AND membership_year = ?",
        (member_id, membership_year),
    )
    return int(cur.rowcount or 0)


def delete_secondary_payments_covered_by_primary(
    conn: sqlite3.Connection,
    member_id: int | None = None,
) -> list[int]:
    """Delete a secondary's own payments for years the primary already has.

    Returns the secondary member ids whose payments were removed.
    """
    member_filter = ""
    params: list[Any] = []
    if member_id is not None:
        member_filter = "AND (p.member_id = ? OR m.family_primary_member_id = ?)"
        params.extend([member_id, member_id])
    rows = conn.execute(
        f"""
        SELECT p.id, p.member_id
        FROM payments p
        JOIN members m ON m.id = p.member_id
        WHERE m.family_primary_member_id IS NOT NULL
          {member_filter}
          AND EXISTS (
              SELECT 1 FROM payments prim
              WHERE prim.member_id = m.family_primary_member_id
                AND prim.membership_year = p.membership_year
          )
        """,
        params,
    ).fetchall()
    if not rows:
        return []
    payment_ids = [int(r["id"]) for r in rows]
    secondary_ids = sorted({int(r["member_id"]) for r in rows})
    placeholders = ",".join("?" * len(payment_ids))
    conn.execute(f"DELETE FROM payments WHERE id IN ({placeholders})", payment_ids)
    return secondary_ids


def covered_by_payment_note(primary_label: str) -> str:
    return f"Covered by {primary_label}"


# Membership types that cannot cover another member (complimentary or non-dues).
FAMILY_PRIMARY_EXCLUDED_TYPE_NAMES = ("life", "emeritus", "new ham", "student")


def sql_family_primary_type_allowed(member_alias: str = "m") -> str:
    """SQL fragment: member's type is not Life, Emeritus, New Ham, or Student.

    Binds FAMILY_PRIMARY_EXCLUDED_TYPE_NAMES in that order.
    """
    placeholders = ",".join("?" * len(FAMILY_PRIMARY_EXCLUDED_TYPE_NAMES))
    return f"""(
        {member_alias}.membership_type_id IS NULL
        OR {member_alias}.membership_type_id NOT IN (
            SELECT id FROM membership_types WHERE lower(name) IN ({placeholders})
        )
    )"""


def format_member_label(last_name: str, first_name: str, call_sign: str | None) -> str:
    name = f"{(last_name or '').strip()}, {(first_name or '').strip()}".strip(", ").strip()
    call = (call_sign or "").strip().upper()
    if call:
        return f"{name} ({call})"
    return name


def parse_family_primary_member_id(raw: Any) -> int | None:
    text = str(raw or "").strip()
    if text == "":
        return None
    if not text.isdigit():
        return None
    value = int(text)
    return value if value > 0 else None


def sql_exists_own_or_family_payment(alias: str, predicate_sql: str) -> str:
    """EXISTS a matching payment on this member or their linked family primary."""
    return f"""EXISTS (
        SELECT 1 FROM payments {alias}
        WHERE {alias}.member_id IN (m.id, m.family_primary_member_id)
          AND {predicate_sql}
    )"""


EFFECTIVE_DATE_PAID_SQL = """(
    SELECT p.payment_date FROM payments p
    WHERE p.member_id IN (m.id, m.family_primary_member_id)
    ORDER BY date(p.payment_date) DESC, p.id DESC
    LIMIT 1
)"""

EFFECTIVE_PAID_THROUGH_SQL = """(
    SELECT MAX(p.paid_through) FROM payments p
    WHERE p.member_id IN (m.id, m.family_primary_member_id)
)"""

COVERED_BY_SQL = """CASE
    WHEN m.family_primary_member_id IS NULL THEN NULL
    ELSE TRIM(
        prim.last_name || ', ' || prim.first_name ||
        CASE
            WHEN prim.call_sign IS NOT NULL AND TRIM(prim.call_sign) <> ''
            THEN ' (' || UPPER(prim.call_sign) || ')'
            ELSE ''
        END
    )
END"""


def validate_family_primary(
    conn: sqlite3.Connection,
    member_id: int | None,
    primary_id: int | None,
) -> str | None:
    if primary_id is None:
        return None
    if member_id is not None and primary_id == member_id:
        return "A member cannot be covered by themselves."
    row = conn.execute(
        "SELECT id, family_primary_member_id FROM members WHERE id = ? LIMIT 1",
        (primary_id,),
    ).fetchone()
    if row is None:
        return "Covered-by member was not found."
    if row["family_primary_member_id"] is not None:
        return "That member is already covered by someone else. Choose the primary member."
    if member_id is not None:
        dep = conn.execute(
            "SELECT 1 FROM members WHERE family_primary_member_id = ? LIMIT 1",
            (member_id,),
        ).fetchone()
        if dep is not None:
            return "This member already covers other family members and cannot become a secondary."
    return None
