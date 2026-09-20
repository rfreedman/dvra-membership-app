"""Validation for member create/edit forms."""

from __future__ import annotations

import sqlite3
from typing import Any

from dvra import family
from dvra import normalizer
from dvra.license_class import find_unlicensed_class_id
from dvra.reference_data import (
    HIDDEN_LICENSE_CLASS,
    HIDDEN_MEMBERSHIP_TYPE,
    ReferenceDataRepository,
)


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
    member_id: int | None = None,
) -> str | None:
    apply_unlicensed_call_sign(conn, row)

    if row["last_name"].strip() == "" or row["first_name"].strip() == "":
        return "Last name and first name are required."

    if row.get("license_class_id") is None:
        return "License class is required."

    if row.get("membership_type_id") is None:
        return "Membership type is required."

    existing_lc = None
    existing_mt = None
    if member_id is not None:
        existing = conn.execute(
            "SELECT license_class_id, membership_type_id FROM members WHERE id = ?",
            (member_id,),
        ).fetchone()
        if existing is not None:
            if existing["license_class_id"] is not None:
                existing_lc = int(existing["license_class_id"])
            if existing["membership_type_id"] is not None:
                existing_mt = int(existing["membership_type_id"])
    ref = ReferenceDataRepository(conn)
    if ref.is_hidden_license_class(row.get("license_class_id")) and row.get("license_class_id") != existing_lc:
        return HIDDEN_LICENSE_CLASS
    if ref.is_hidden_membership_type(row.get("membership_type_id")) and row.get(
        "membership_type_id"
    ) != existing_mt:
        return HIDDEN_MEMBERSHIP_TYPE

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

    family_err = family.validate_family_primary(conn, member_id, row.get("family_primary_member_id"))
    if family_err:
        return family_err

    return None
