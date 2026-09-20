"""Form input normalization (call sign, US phone, member/payment rows)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from dvra import family
from dvra import membership_year as myear


def normalize_call_sign(raw: str | None) -> str | None:
    s = (raw or "").upper().strip()
    return s if s else None


def strip_optional(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = raw.strip()
    return s if s else None


def normalize_phone_us_ten_digit(raw: str | None) -> str | None:
    s = (raw or "").strip()
    if s == "":
        return None
    digits = re.sub(r"\D+", "", s)
    if digits == "":
        return None
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    if len(digits) != 10:
        return None
    return f"{digits[0:3]}-{digits[3:6]}-{digits[6:10]}"


def normalize_state(raw: str | None) -> str | None:
    s = strip_optional(raw)
    if s is None:
        return None
    u = s.upper()
    if re.fullmatch(r"[A-Z]{2}", u):
        return u
    return u[:16]


def normalize_zip(raw: str | None) -> str | None:
    s = strip_optional(raw)
    if s is None:
        return None
    compact = s.replace(" ", "")
    if re.fullmatch(r"[0-9]{5}(?:-[0-9]{4})?", compact):
        return compact
    return s


def _form_str(body: dict[str, Any], key: str) -> str:
    v = body.get(key)
    if v is None:
        return ""
    return str(v)


def member_create_from_form(body: dict[str, Any], paid_through: str | None) -> dict[str, Any]:
    key_raw = _form_str(body, "key_number").strip()
    lic = _form_str(body, "license_class").strip()
    mt = _form_str(body, "membership_type").strip()
    qrz = strip_optional(_form_str(body, "qrz_email"))
    return {
        "last_name": _form_str(body, "last_name").strip(),
        "first_name": _form_str(body, "first_name").strip(),
        "call_sign": normalize_call_sign(_form_str(body, "call_sign")),
        "email": strip_optional(_form_str(body, "email")),
        "nickname": strip_optional(_form_str(body, "nickname")),
        "qrz_email": qrz.lower() if qrz else None,
        "phone": normalize_phone_us_ten_digit(_form_str(body, "phone")),
        "address_street": strip_optional(_form_str(body, "address_street")),
        "address_city": strip_optional(_form_str(body, "address_city")),
        "address_state": normalize_state(_form_str(body, "address_state")),
        "address_zip": normalize_zip(_form_str(body, "address_zip")),
        "license_class_id": int(lic) if lic.isdigit() else None,
        "membership_type_id": int(mt) if mt.isdigit() else None,
        "family_primary_member_id": family.parse_family_primary_member_id(body.get("family_primary_member_id")),
        "arrl_member": _form_str(body, "arrl_member") == "yes",
        "deceased": _form_str(body, "deceased") == "yes",
        "key_number": int(key_raw) if key_raw.isdigit() else None,
        "paid_through": paid_through,
        "notes": strip_optional(_form_str(body, "notes")),
    }


def member_update_from_form(body: dict[str, Any]) -> dict[str, Any]:
    parsed = member_create_from_form(body, None)
    parsed.pop("paid_through", None)
    return parsed


def _parse_iso_date(raw: str) -> str | None:
    trimmed = raw.strip()
    if trimmed == "":
        return None
    try:
        return datetime.strptime(trimmed, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        try:
            return datetime.fromisoformat(trimmed).date().isoformat()
        except ValueError:
            return None


def payment_from_form(body: dict[str, Any]) -> dict[str, Any]:
    pd_raw = _form_str(body, "payment_date").strip()
    if pd_raw == "":
        return {"ok": False, "error": "Payment date is required."}
    payment_date = _parse_iso_date(pd_raw)
    if payment_date is None:
        return {"ok": False, "error": "Invalid payment date."}
    year = myear.parse_year_input(body.get("membership_year"))
    if year is None:
        return {"ok": False, "error": "Membership year is required."}
    mt_raw = _form_str(body, "membership_type").strip()
    membership_type_id = int(mt_raw) if mt_raw.isdigit() else None
    notes_raw = _form_str(body, "notes").strip()
    fn_raw = _form_str(body, "form_number").strip()
    return {
        "ok": True,
        "error": "",
        "data": {
            "payment_date": payment_date,
            "membership_year": year,
            "membership_type_id": membership_type_id,
            "notes": notes_raw or None,
            "form_number": fn_raw or None,
        },
    }


def reference_label(name: str | None) -> str:
    return (name or "").strip()


def membership_type_display(resolved_type_row_id: int | None, name: str) -> str:
    trim_name = name.strip()
    if trim_name == "":
        return ""
    if (
        resolved_type_row_id is not None
        and resolved_type_row_id >= 1
        and trim_name.isdigit()
        and int(trim_name) == resolved_type_row_id
    ):
        return ""
    return trim_name
