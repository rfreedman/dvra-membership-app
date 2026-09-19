"""Validation for member create/edit forms."""

from __future__ import annotations

import sqlite3
from typing import Any

from dvra import normalizer
from dvra.license_class import find_unlicensed_class_id


def _form_str(body: dict[str, Any], key: str) -> str:
    v = body.get(key)
    if v is None:
        return ""
    return str(v)


def apply_unlicensed_call_sign(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    unlicensed_id = find_unlicensed_class_id(conn)
    if unlicensed_id is not None and row.get("license_class_id") == unlicensed_id:
        row["call_sign"] = None


def validate_member_row(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    body: dict[str, Any],
    *,
    require_paid_year: bool,
    paid_year: int | None,
) -> str | None:
    apply_unlicensed_call_sign(conn, row)

    if row["last_name"].strip() == "" or row["first_name"].strip() == "":
        return "Last name and first name are required."

    if row.get("license_class_id") is None:
        return "License class is required."

    if row.get("membership_type_id") is None:
        return "Membership type is required."

    if normalizer.strip_optional(_form_str(body, "email")) is None:
        return "Email is required."

    phone_raw = _form_str(body, "phone").strip()
    if phone_raw == "":
        return "Phone is required."
    if row.get("phone") is None:
        return "Enter a valid 10-digit US phone number."

    for field, label in (
        ("address_street", "Street"),
        ("address_city", "City"),
        ("address_state", "State"),
        ("address_zip", "ZIP"),
    ):
        if not (row.get(field) or "").strip():
            return f"{label} is required."

    unlicensed_id = find_unlicensed_class_id(conn)
    if unlicensed_id is None or row.get("license_class_id") != unlicensed_id:
        if row.get("call_sign") is None:
            return "Call sign is required for licensed members."

    if require_paid_year and paid_year is None:
        return "Paid for year is required."

    return None
