"""Member CRUD."""

from __future__ import annotations

import sqlite3
from typing import Any

from dvra import normalizer
from dvra.reference_data import ReferenceDataRepository


class DuplicateMemberKeyNumber(Exception):
    pass


class MemberRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def list_license_classes(self) -> list[dict]:
        return ReferenceDataRepository(self.conn).list_license_classes()

    def list_membership_types(self) -> list[dict]:
        return ReferenceDataRepository(self.conn).list_membership_types()

    def find_member_by_id(self, id_: int) -> dict | None:
        row = self.conn.execute(
            """
            SELECT id, last_name, first_name, call_sign, email, phone,
                   address_street, address_city, address_state, address_zip,
                   license_class_id, membership_type_id, arrl_member, key_number, paid_through
            FROM members WHERE id = ? LIMIT 1
            """,
            (id_,),
        ).fetchone()
        if row is None:
            return None
        return self._normalize_member_row(row)

    @staticmethod
    def _normalize_member_row(row: sqlite3.Row) -> dict:
        def s(key: str) -> str | None:
            v = row[key]
            return str(v) if v is not None else None

        return {
            "id": int(row["id"]),
            "last_name": str(row["last_name"]),
            "first_name": str(row["first_name"]),
            "call_sign": s("call_sign"),
            "email": s("email"),
            "phone": s("phone"),
            "address_street": s("address_street"),
            "address_city": s("address_city"),
            "address_state": s("address_state"),
            "address_zip": s("address_zip"),
            "license_class_id": int(row["license_class_id"]) if row["license_class_id"] is not None else None,
            "membership_type_id": int(row["membership_type_id"]) if row["membership_type_id"] is not None else None,
            "arrl_member": bool(row["arrl_member"]),
            "key_number": int(row["key_number"]) if row["key_number"] is not None else None,
            "paid_through": s("paid_through"),
        }

    def find_id_by_nonnull_call_sign(self, call_sign: str) -> int | None:
        n = normalizer.normalize_call_sign(call_sign)
        if n is None:
            return None
        row = self.conn.execute("SELECT id FROM members WHERE call_sign = ? LIMIT 1", (n,)).fetchone()
        return int(row["id"]) if row else None

    def exists_name_without_call_sign(self, last_name: str, first_name: str, exclude_member_id: int | None) -> bool:
        if exclude_member_id is not None:
            row = self.conn.execute(
                """
                SELECT 1 FROM members
                WHERE lower(trim(last_name)) = lower(trim(?))
                  AND lower(trim(first_name)) = lower(trim(?))
                  AND call_sign IS NULL
                  AND id != ?
                LIMIT 1
                """,
                (last_name, first_name, exclude_member_id),
            ).fetchone()
        else:
            row = self.conn.execute(
                """
                SELECT 1 FROM members
                WHERE lower(trim(last_name)) = lower(trim(?))
                  AND lower(trim(first_name)) = lower(trim(?))
                  AND call_sign IS NULL
                LIMIT 1
                """,
                (last_name, first_name),
            ).fetchone()
        return row is not None

    def find_member_id_by_key_number(self, key_number: int, exclude_member_id: int | None) -> int | None:
        if exclude_member_id is not None:
            row = self.conn.execute(
                "SELECT id FROM members WHERE key_number = ? AND id != ? LIMIT 1",
                (key_number, exclude_member_id),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT id FROM members WHERE key_number = ? LIMIT 1", (key_number,)
            ).fetchone()
        return int(row["id"]) if row else None

    def enforce_unique_key_number(self, key_number: int | None, exclude_member_id: int | None) -> None:
        if key_number is None:
            return
        if self.find_member_id_by_key_number(key_number, exclude_member_id) is not None:
            raise DuplicateMemberKeyNumber("Another member already holds that key number.")

    @staticmethod
    def _coerce_phone(data: dict[str, Any]) -> None:
        raw = data.get("phone")
        as_string = str(raw) if raw not in (None, "") else None
        data["phone"] = normalizer.normalize_phone_us_ten_digit(as_string)

    def insert_member(self, data: dict[str, Any]) -> int:
        self._coerce_phone(data)
        self.enforce_unique_key_number(data["key_number"], None)
        cur = self.conn.execute(
            """
            INSERT INTO members (
                last_name, first_name, call_sign, email, phone,
                address_street, address_city, address_state, address_zip,
                license_class_id, membership_type_id, arrl_member, key_number, paid_through,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                data["last_name"],
                data["first_name"],
                data["call_sign"],
                data["email"],
                data["phone"],
                data["address_street"],
                data["address_city"],
                data["address_state"],
                data["address_zip"],
                data["license_class_id"],
                data["membership_type_id"],
                1 if data["arrl_member"] else 0,
                data["key_number"],
                data["paid_through"],
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update_member(self, id_: int, data: dict[str, Any]) -> None:
        self._coerce_phone(data)
        self.enforce_unique_key_number(data["key_number"], id_)
        self.conn.execute(
            """
            UPDATE members SET
                last_name = ?, first_name = ?, call_sign = ?, email = ?, phone = ?,
                address_street = ?, address_city = ?, address_state = ?, address_zip = ?,
                license_class_id = ?, membership_type_id = ?, arrl_member = ?, key_number = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                data["last_name"],
                data["first_name"],
                data["call_sign"],
                data["email"],
                data["phone"],
                data["address_street"],
                data["address_city"],
                data["address_state"],
                data["address_zip"],
                data["license_class_id"],
                data["membership_type_id"],
                1 if data["arrl_member"] else 0,
                data["key_number"],
                id_,
            ),
        )
        self.conn.commit()

    def delete_member_by_id(self, id_: int) -> bool:
        cur = self.conn.execute("DELETE FROM members WHERE id = ?", (id_,))
        self.conn.commit()
        return cur.rowcount > 0

    def list_payments_for_member(self, member_id: int) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT p.id, p.payment_date, p.paid_through, p.membership_year, p.membership_type_id, p.form_number, p.notes,
                   mt.name AS mt_name,
                   mt.id AS mt_row_id
            FROM payments p
            LEFT JOIN membership_types mt ON p.membership_type_id = mt.id
            WHERE p.member_id = ?
            ORDER BY p.membership_year DESC, p.payment_date DESC, p.id DESC
            """,
            (member_id,),
        ).fetchall()
        out = []
        for r in rows:
            nm = str(r["mt_name"]) if r["mt_name"] is not None else ""
            mt_row_id = int(r["mt_row_id"]) if r["mt_row_id"] is not None else None
            out.append(
                {
                    "id": int(r["id"]),
                    "payment_date": str(r["payment_date"] or ""),
                    "paid_through": str(r["paid_through"] or ""),
                    "membership_year": int(r["membership_year"] or 0),
                    "membership_type_id": int(r["membership_type_id"]) if r["membership_type_id"] is not None else None,
                    "form_number": str(r["form_number"]) if r["form_number"] is not None else None,
                    "notes": str(r["notes"]) if r["notes"] is not None else None,
                    "membership_type_display": normalizer.membership_type_display(mt_row_id, nm),
                }
            )
        return out

    def normalize_stored_member_phones_to_us_ten_digit(self) -> int:
        rows = self.conn.execute(
            "SELECT id, phone FROM members WHERE phone IS NOT NULL AND TRIM(phone) <> ''"
        ).fetchall()
        changed = 0
        for row in rows:
            raw = str(row["phone"])
            nxt = normalizer.normalize_phone_us_ten_digit(raw)
            if nxt != raw:
                self.conn.execute("UPDATE members SET phone = ? WHERE id = ?", (nxt, int(row["id"])))
                changed += 1
        self.conn.commit()
        return changed
