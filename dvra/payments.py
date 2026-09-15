"""Payment CRUD; sync members.paid_through = MAX(payments.paid_through)."""

from __future__ import annotations

import sqlite3

from dvra import membership_year as myear


class PaymentRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def sync_member_paid_through_from_payments(self, member_id: int) -> None:
        self.conn.execute(
            """
            UPDATE members SET paid_through = (
                SELECT MAX(paid_through) FROM payments WHERE member_id = ?
            ), updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """,
            (member_id, member_id),
        )

    def find_payment_meta(self, payment_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT member_id FROM payments WHERE id = ? LIMIT 1", (payment_id,)
        ).fetchone()
        if row is None:
            return None
        return {"member_id": int(row["member_id"])}

    def member_has_payment_for_year(
        self, member_id: int, year: int, exclude_payment_id: int | None = None
    ) -> bool:
        if exclude_payment_id is not None and exclude_payment_id > 0:
            row = self.conn.execute(
                "SELECT 1 FROM payments WHERE member_id = ? AND membership_year = ? AND id != ? LIMIT 1",
                (member_id, year, exclude_payment_id),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT 1 FROM payments WHERE member_id = ? AND membership_year = ? LIMIT 1",
                (member_id, year),
            ).fetchone()
        return row is not None

    def next_free_membership_year(
        self, member_id: int, requested_year: int, exclude_payment_id: int | None = None
    ) -> int:
        y = requested_year
        while y <= myear.MAX_YEAR:
            if not self.member_has_payment_for_year(member_id, y, exclude_payment_id):
                return y
            y += 1
        raise RuntimeError("No free membership year available.")

    def insert_payment(self, member_id: int, data: dict) -> None:
        year = int(data["membership_year"])
        paid_through = myear.paid_through_iso(year)
        try:
            self.conn.execute(
                """
                INSERT INTO payments (member_id, payment_date, paid_through, membership_year,
                    membership_type_id, notes, form_number, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    member_id,
                    data["payment_date"],
                    paid_through,
                    year,
                    data["membership_type_id"],
                    data["notes"],
                    data["form_number"],
                ),
            )
            self.sync_member_paid_through_from_payments(member_id)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def update_payment(self, payment_id: int, data: dict) -> int | None:
        meta = self.find_payment_meta(payment_id)
        if meta is None:
            return None
        member_id = meta["member_id"]
        year = int(data["membership_year"])
        paid_through = myear.paid_through_iso(year)
        try:
            self.conn.execute(
                """
                UPDATE payments SET payment_date = ?, paid_through = ?, membership_year = ?,
                    membership_type_id = ?, notes = ?, form_number = ?
                WHERE id = ?
                """,
                (
                    data["payment_date"],
                    paid_through,
                    year,
                    data["membership_type_id"],
                    data["notes"],
                    data["form_number"],
                    payment_id,
                ),
            )
            self.sync_member_paid_through_from_payments(member_id)
            self.conn.commit()
            return member_id
        except Exception:
            self.conn.rollback()
            raise

    def delete_payment(self, payment_id: int) -> int | None:
        meta = self.find_payment_meta(payment_id)
        if meta is None:
            return None
        member_id = meta["member_id"]
        try:
            self.conn.execute("DELETE FROM payments WHERE id = ?", (payment_id,))
            self.sync_member_paid_through_from_payments(member_id)
            self.conn.commit()
            return member_id
        except Exception:
            self.conn.rollback()
            raise
