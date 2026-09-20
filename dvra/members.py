"""Member CRUD."""

from __future__ import annotations

import sqlite3
from typing import Any

from dvra import family
from dvra import normalizer
from dvra.reference_data import ReferenceDataRepository


class DuplicateMemberKeyNumber(Exception):
    pass


class MemberHasFamilySecondaries(Exception):
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
            f"""
            SELECT m.id, m.last_name, m.first_name, m.call_sign, m.email, m.nickname, m.qrz_email,
                   m.phone, m.address_street, m.address_city, m.address_state, m.address_zip,
                   m.license_class_id, m.membership_type_id, m.family_primary_member_id,
                   m.arrl_member, m.deceased, m.key_number, m.paid_through, m.notes,
                   {family.EFFECTIVE_PAID_THROUGH_SQL} AS effective_paid_through
            FROM members m
            WHERE m.id = ?
            LIMIT 1
            """,
            (id_,),
        ).fetchone()
        if row is None:
            return None
        member = self._normalize_member_row(row)
        member["family_primary_label"] = self.family_primary_label(member.get("family_primary_member_id"))
        member["covered_members"] = self.list_covered_member_labels(member["id"])
        own_pt = member.get("paid_through")
        effective = row["effective_paid_through"]
        member["paid_through"] = str(effective) if effective is not None else None
        member["paid_through_inherited"] = bool(
            member.get("family_primary_member_id")
            and member["paid_through"]
            and (not own_pt or str(own_pt) < member["paid_through"])
        )
        return member

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
            "nickname": s("nickname"),
            "qrz_email": s("qrz_email"),
            "phone": s("phone"),
            "address_street": s("address_street"),
            "address_city": s("address_city"),
            "address_state": s("address_state"),
            "address_zip": s("address_zip"),
            "license_class_id": int(row["license_class_id"]) if row["license_class_id"] is not None else None,
            "membership_type_id": int(row["membership_type_id"]) if row["membership_type_id"] is not None else None,
            "family_primary_member_id": (
                int(row["family_primary_member_id"]) if row["family_primary_member_id"] is not None else None
            ),
            "arrl_member": bool(row["arrl_member"]),
            "deceased": bool(row["deceased"]),
            "key_number": int(row["key_number"]) if row["key_number"] is not None else None,
            "paid_through": s("paid_through"),
            "notes": s("notes"),
        }

    def family_primary_label(self, primary_id: int | None) -> str:
        if primary_id is None:
            return ""
        row = self.conn.execute(
            "SELECT last_name, first_name, call_sign FROM members WHERE id = ? LIMIT 1",
            (primary_id,),
        ).fetchone()
        if row is None:
            return ""
        return family.format_member_label(row["last_name"], row["first_name"], row["call_sign"])

    def list_covered_member_labels(self, primary_id: int) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT last_name, first_name, call_sign
            FROM members
            WHERE family_primary_member_id = ?
            ORDER BY last_name ASC, first_name ASC, id ASC
            """,
            (primary_id,),
        ).fetchall()
        return [family.format_member_label(r["last_name"], r["first_name"], r["call_sign"]) for r in rows]

    def list_family_primary_options(
        self, exclude_member_id: int | None, include_primary_id: int | None = None
    ) -> list[dict]:
        living = "COALESCE(deceased, 0) = 0"
        if include_primary_id is not None:
            living = f"({living} OR id = ?)"
        params: list[Any] = []
        if include_primary_id is not None:
            params.append(include_primary_id)
        exclude_sql = ""
        if exclude_member_id is not None:
            exclude_sql = "AND id != ?"
            params.append(exclude_member_id)
        rows = self.conn.execute(
            f"""
            SELECT id, last_name, first_name, call_sign
            FROM members
            WHERE family_primary_member_id IS NULL
              AND {living}
              {exclude_sql}
            ORDER BY last_name ASC, first_name ASC, id ASC
            """,
            params,
        ).fetchall()
        return [
            {
                "id": int(r["id"]),
                "label": family.format_member_label(r["last_name"], r["first_name"], r["call_sign"]),
            }
            for r in rows
        ]

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
                last_name, first_name, call_sign, email, nickname, qrz_email, phone,
                address_street, address_city, address_state, address_zip,
                license_class_id, membership_type_id, family_primary_member_id,
                arrl_member, deceased, key_number, paid_through,
                notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                data["last_name"],
                data["first_name"],
                data["call_sign"],
                data["email"],
                data.get("nickname"),
                data.get("qrz_email"),
                data["phone"],
                data["address_street"],
                data["address_city"],
                data["address_state"],
                data["address_zip"],
                data["license_class_id"],
                data["membership_type_id"],
                data.get("family_primary_member_id"),
                1 if data["arrl_member"] else 0,
                1 if data.get("deceased") else 0,
                data["key_number"],
                data["paid_through"],
                data.get("notes"),
            ),
        )
        self._remove_covered_secondary_payments(int(cur.lastrowid), data.get("family_primary_member_id"))
        self.conn.commit()
        return int(cur.lastrowid)

    def update_member(self, id_: int, data: dict[str, Any]) -> None:
        self._coerce_phone(data)
        self.enforce_unique_key_number(data["key_number"], id_)
        self.conn.execute(
            """
            UPDATE members SET
                last_name = ?, first_name = ?, call_sign = ?, email = ?, nickname = ?, qrz_email = ?, phone = ?,
                address_street = ?, address_city = ?, address_state = ?, address_zip = ?,
                license_class_id = ?, membership_type_id = ?, family_primary_member_id = ?,
                arrl_member = ?, deceased = ?, key_number = ?,
                notes = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                data["last_name"],
                data["first_name"],
                data["call_sign"],
                data["email"],
                data.get("nickname"),
                data.get("qrz_email"),
                data["phone"],
                data["address_street"],
                data["address_city"],
                data["address_state"],
                data["address_zip"],
                data["license_class_id"],
                data["membership_type_id"],
                data.get("family_primary_member_id"),
                1 if data["arrl_member"] else 0,
                1 if data.get("deceased") else 0,
                data["key_number"],
                data.get("notes"),
                id_,
            ),
        )
        self._remove_covered_secondary_payments(id_, data.get("family_primary_member_id"))
        self.conn.commit()

    def _remove_covered_secondary_payments(self, member_id: int, primary_id: Any) -> None:
        if primary_id is None:
            return
        from dvra.payments import PaymentRepository

        secondary_ids = family.delete_secondary_payments_covered_by_primary(self.conn, member_id)
        pay = PaymentRepository(self.conn)
        for sid in secondary_ids:
            pay.sync_member_paid_through_from_payments(sid)

    def update_member_notes(self, id_: int, notes: str | None) -> bool:
        cur = self.conn.execute(
            """
            UPDATE members SET notes = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (notes, id_),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def delete_member_by_id(self, id_: int) -> bool:
        labels = self.list_covered_member_labels(id_)
        if labels:
            raise MemberHasFamilySecondaries(
                "Unlink covered family members before deleting this member: " + "; ".join(labels) + "."
            )
        cur = self.conn.execute("DELETE FROM members WHERE id = ?", (id_,))
        self.conn.commit()
        return cur.rowcount > 0

    def _payment_rows_for_member_id(self, member_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
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

    @staticmethod
    def _map_payment_row(r: sqlite3.Row, *, inherited: bool, covered_by_label: str = "") -> dict:
        nm = str(r["mt_name"]) if r["mt_name"] is not None else ""
        mt_row_id = int(r["mt_row_id"]) if r["mt_row_id"] is not None else None
        notes = str(r["notes"]) if r["notes"] is not None else None
        if inherited:
            notes = family.covered_by_payment_note(covered_by_label)
        return {
            "id": int(r["id"]),
            "payment_date": str(r["payment_date"] or ""),
            "paid_through": str(r["paid_through"] or ""),
            "membership_year": int(r["membership_year"] or 0),
            "membership_type_id": int(r["membership_type_id"]) if r["membership_type_id"] is not None else None,
            "form_number": str(r["form_number"]) if r["form_number"] is not None else None,
            "notes": notes,
            "membership_type_display": normalizer.membership_type_display(mt_row_id, nm),
            "inherited": inherited,
        }

    def list_payments_for_member(self, member_id: int) -> list[dict]:
        own = [self._map_payment_row(r, inherited=False) for r in self._payment_rows_for_member_id(member_id)]
        primary_id = self.conn.execute(
            "SELECT family_primary_member_id FROM members WHERE id = ? LIMIT 1",
            (member_id,),
        ).fetchone()
        if primary_id is None or primary_id["family_primary_member_id"] is None:
            return own
        label = self.family_primary_label(int(primary_id["family_primary_member_id"]))
        inherited = [
            self._map_payment_row(r, inherited=True, covered_by_label=label)
            for r in self._payment_rows_for_member_id(int(primary_id["family_primary_member_id"]))
        ]
        covered_years = {p["membership_year"] for p in inherited}
        own_only = [p for p in own if p["membership_year"] not in covered_years]
        combined = own_only + inherited
        combined.sort(
            key=lambda p: (-int(p["membership_year"] or 0), p["payment_date"] or "", -int(p["id"])),
        )
        return combined

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
