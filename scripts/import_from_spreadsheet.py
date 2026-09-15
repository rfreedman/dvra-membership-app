"""Import DVRA member spreadsheet (.xlsx) into the membership database.

Run from the repo root, for example:

    python scripts/import_from_spreadsheet.py --spreadsheet ./data.xlsx --database-url sqlite:///... --replace

CLI-only importer. SQLAlchemy is used here, not in the CGI web app.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dvra.import_orm import crud  # noqa: E402
from dvra.import_orm.database import Base  # noqa: E402
from dvra.import_orm.models import LicenseClass, Member, MembershipType, Payment  # noqa: E402
from dvra.normalizer import normalize_phone_us_ten_digit  # noqa: E402
from dvra.roster_us_address import member_address_parts_from_raw  # noqa: E402

XML_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

# Column G may be labeled "Membership Type" (preferred) or "Status" (legacy spreadsheets).
HEADER_COL_G = frozenset({"Membership Type", "Status"})


@dataclass(frozen=True, kw_only=True)
class SpreadsheetRow:
    last_name: str
    first_name: str
    call_sign: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    paid_through: Optional[date] = None
    membership_type: Optional[str] = None
    license_class: Optional[str] = None
    arrl_member: bool = False
    key_number: Optional[int] = None
    #: Original roster column **O** text (stripped).
    address_raw: Optional[str] = None
    address_street: Optional[str] = None
    address_city: Optional[str] = None
    address_state: Optional[str] = None
    address_zip: Optional[str] = None
    #: Excel worksheet row index when read from roster layout (optional; for previews / tooling).
    source_excel_row: Optional[int] = None
    #: Roster layout only: ``(payment_date, paid_through_dec31, raw_cell_text)`` per year column D/F/H that parsed.
    roster_historical_payments: Optional[tuple[tuple[date, date, str], ...]] = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import DVRA member spreadsheet into SQL database.")
    parser.add_argument("--spreadsheet", required=True, help="Path to DVRA .xlsx spreadsheet")
    parser.add_argument(
        "--database-url",
        default="sqlite:///./var/dvra_membership.sqlite",
        help="SQLAlchemy database URL (sqlite/postgresql/mysql)",
    )
    parser.add_argument("--replace", action="store_true", help="Delete existing members/payments before import")
    parser.add_argument(
        "--default-membership-type",
        default="",
        help=(
            "If column G (Status / Membership Type) is empty on a row, use this type name for that row’s "
            "inferred payment and member sync (get-or-create in membership_types). "
            "Many DVRA exports omit G for every data row; without this flag, membership_type_id stays null."
        ),
    )
    return parser.parse_args()


def _strip_middle_initial(first: str) -> str:
    words = first.strip().split()
    if len(words) >= 2:
        token = words[1].rstrip(".")
        if len(token) == 1 and token.isalpha():
            words = [words[0]] + words[2:]
    return " ".join(words)


def _title_name_part(part: str) -> str:
    return " ".join(w[:1].upper() + w[1:].lower() if w else w for w in part.strip().split())


def _is_all_caps_word_phrase(s: str) -> bool:
    """True when ``s`` looks like shouting (all uppercase letters); mixed case left unchanged downstream."""
    t = s.strip()
    if not t or not any(c.isalpha() for c in t):
        return False
    if t != t.upper():
        return False
    # Skip bare two-letter alphabetics (NJ, HI, ME, OK, …) — title-casing would produce ``Nj``.
    if len(t) == 2 and t.isalpha():
        return False
    return True


def title_case_import_field_if_all_caps(raw: Optional[str]) -> Optional[str]:
    """Roster/club exports often use ALL CAPS; normalize to readable title case unless already mixed."""
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    if not _is_all_caps_word_phrase(text):
        return text
    return _title_name_part(text)


def _title_street_line_if_all_caps(raw: Optional[str]) -> Optional[str]:
    """Title-case shouted street fragments; restore ``US`` / ``PO`` / ``P.O.`` USPS tokens mangled by title case."""
    t = title_case_import_field_if_all_caps(raw)
    if t is None or not raw or not raw.strip():
        return t
    if not _is_all_caps_word_phrase(raw.strip()):
        return t
    out = t
    out = re.sub(r"(?i)\bUs Highway\b", "US Highway", out)
    out = re.sub(r"(?i)\bUs Hwy\b", "US Hwy", out)
    out = re.sub(r"(?i)\bUs Route\b", "US Route", out)
    out = re.sub(r"(?i)\bP\.o\.\s*Box\b", "P.O. Box", out)
    out = re.sub(r"(?i)\bPo Box\b", "PO Box", out)
    return out


_SHOUTED_CITY_ABBREV: dict[str, str] = {
    "TWP": "Twp",
    "TOWNSHIP": "Township",
    "BORO": "Boro",
    "BOROUGH": "Borough",
}


def _normalize_shouted_city_suffix_tokens(city_line: str) -> str:
    """Title-case municipal tokens that stayed ALL CAPS (e.g. ``… Hamilton TWP`` or ``WASHINGTON-TWP``)."""

    parts: list[str] = []
    for raw_w in city_line.split():
        punct = ""
        w = raw_w
        while w and w[-1] in ",.;:":
            punct = w[-1] + punct
            w = w[:-1]
        if not w:
            parts.append(raw_w)
            continue
        if "-" in w:
            left, _, right = w.rpartition("-")
            canon = _SHOUTED_CITY_ABBREV.get(right.upper())
            if canon is not None and right.isalpha():
                lhs_raw = left.strip()
                lhs = title_case_import_field_if_all_caps(lhs_raw) if lhs_raw else lhs_raw
                if not lhs and lhs_raw:
                    lhs = _title_name_part(lhs_raw)
                if not lhs:
                    lhs = lhs_raw
                parts.append(f"{lhs}-{canon}{punct}")
                continue

        canon = _SHOUTED_CITY_ABBREV.get(w.upper())
        if canon is not None and w.isalpha():
            parts.append(canon + punct)
        else:
            parts.append(w + punct)
    return " ".join(parts)


def normalize_city_import_field(city: Optional[str]) -> Optional[str]:
    """All-caps city → word title case; also normalize municipal abbreviations left in CAPS."""
    c = title_case_import_field_if_all_caps(city)
    if c is None or not c.strip():
        return c
    return _normalize_shouted_city_suffix_tokens(c)


def normalize_last_name(raw: str) -> str:
    return _title_name_part(raw)


def normalize_first_name(raw: str) -> str:
    return _title_name_part(_strip_middle_initial(raw))


_MEMBERSHIP_IMPORT_ALIASES: dict[str, str] = {"waived": "New Ham"}

# Roster workbook (dvra_membership.xlsx): FCC / club shorthand → canonical license_classes.name
_LICENSE_CLASS_ALIASES: dict[str, str] = {
    "extra": "Amateur Extra",
    "advanced": "Amateur Extra",
    "advance": "Amateur Extra",
    "general": "General",
    "technician": "Technician",
    "tech": "Technician",
    "novice": "Novice",
    "inactive": "Inactive",
}

_EXCEL_ERR_TOKENS = frozenset({"#n/a", "#ref!", "#value!", "#null!"})

# Trailing ``(digits)`` in a roster payment cell is stored as ``Payment.form_number``, not in notes.
_TRAILING_FORM_NUMBER_IN_PARENS = re.compile(r"\(\s*(\d+)\s*\)\s*$")


def split_trailing_form_number_from_comment(text: str) -> tuple[str, Optional[str]]:
    """If ``text`` ends with ``(12345)``-style digits in parentheses, return ``(rest, '12345')``; else ``(text.strip(), None)``."""
    s = (text or "").strip()
    if not s:
        return ("", None)
    m = _TRAILING_FORM_NUMBER_IN_PARENS.search(s)
    if not m:
        return (s, None)
    form_number = m.group(1)
    rest = s[: m.start()].rstrip()
    return (rest, form_number)


def canonical_membership_name(raw: str) -> str:
    stripped = raw.strip()
    key = stripped.lower()
    if key in _MEMBERSHIP_IMPORT_ALIASES:
        return _MEMBERSHIP_IMPORT_ALIASES[key]
    t = title_case_import_field_if_all_caps(stripped)
    return t if t is not None else stripped


def read_spreadsheet_rows(path: str) -> list[SpreadsheetRow]:
    with ZipFile(path) as workbook_zip:
        shared_strings = _read_shared_strings(workbook_zip)
        sheet = ET.fromstring(workbook_zip.read("xl/worksheets/sheet1.xml"))
        rows = sheet.findall(".//x:sheetData/x:row", XML_NS)
        if not rows:
            return []
        header_cells = _extract_row_values(rows[0], shared_strings)
        if _is_roster_membership_workbook(header_cells):
            return _read_roster_membership_rows(rows, shared_strings)
        return _read_legacy_report_rows(rows, shared_strings)


def _is_roster_membership_workbook(header_cells: dict[str, str]) -> bool:
    a1 = (header_cells.get("A") or "").strip().lower()
    b1 = (header_cells.get("B") or "").strip()
    return "last name" in a1 and b1 == "Membership Type"


def _read_roster_membership_rows(xml_rows: list[ET.Element], shared_strings: list[str]) -> list[SpreadsheetRow]:
    parsed: list[SpreadsheetRow] = []
    for row_index, row in enumerate(xml_rows):
        if row_index == 0:
            continue
        cells = _extract_row_values(row, shared_strings)
        name_cell = (cells.get("A") or "").strip()
        if not name_cell:
            continue
        excel_row = int(row.attrib.get("r", str(row_index + 1)))
        parsed_name = _parse_roster_name_cell(name_cell)
        if parsed_name is None:
            print(
                f"Warning: could not parse name in column A (Excel row {excel_row}): {name_cell!r}",
                file=sys.stderr,
            )
            continue
        last_name, first_name, call_sign = parsed_name
        membership_type = title_case_import_field_if_all_caps(_none_if_blank(cells.get("B", "")))
        hist = _roster_payment_entries_from_cells(cells)
        member_paid_through = max((h[1] for h in hist), default=None)
        email = _roster_email_from_cells(cells)
        phone = _none_if_blank(cells.get("K", ""))
        license_raw = _none_if_blank(cells.get("N", ""))
        license_class = _map_license_class_name(license_raw)
        arrl_member = _parse_bool_cell(cells.get("P", ""))
        key_number = _parse_optional_int_cell(cells.get("Q", ""))
        addr_raw = (cells.get("O") or "").strip()
        adr_st = adr_city = adr_stt = adr_zip = None
        if addr_raw:
            adr_st, adr_city, adr_stt, adr_zip = member_address_parts_from_raw(addr_raw)
            adr_st = _title_street_line_if_all_caps(adr_st)
            adr_city = normalize_city_import_field(adr_city)
        parsed.append(
            SpreadsheetRow(
                last_name=normalize_last_name(last_name),
                first_name=normalize_first_name(first_name),
                call_sign=call_sign,
                email=email,
                phone=phone,
                paid_through=member_paid_through,
                membership_type=membership_type,
                license_class=license_class,
                arrl_member=arrl_member,
                key_number=key_number,
                address_raw=addr_raw or None,
                address_street=adr_st,
                address_city=adr_city,
                address_state=adr_stt,
                address_zip=adr_zip,
                roster_historical_payments=tuple(hist) if hist else None,
                source_excel_row=excel_row,
            )
        )
    return parsed


def _read_legacy_report_rows(xml_rows: list[ET.Element], shared_strings: list[str]) -> list[SpreadsheetRow]:
    parsed_rows: list[SpreadsheetRow] = []
    for row_index, row in enumerate(xml_rows):
        values_by_col = _extract_row_values(row, shared_strings)
        if row_index == 0:
            _validate_header(values_by_col)
            continue
        normalized = _to_ordered_values(values_by_col)
        if not any(normalized):
            continue
        parsed_rows.append(_to_spreadsheet_row(normalized))
    return parsed_rows


def _parse_roster_name_cell(s: str) -> Optional[tuple[str, str, Optional[str]]]:
    """Parse ``LAST, FIRST ... | CALL`` from column A.

    ``CALL`` after ``|`` may be omitted (member imports with ``call_sign`` null).
    Rows without ``|`` but with ``LAST, FIRST`` import with no call sign.
    """
    s = s.strip()
    if "|" in s:
        left, right = s.rsplit("|", 1)
        call_sign = right.strip().upper() or None
        if "," not in left:
            return None
        last_name, first_part = left.split(",", 1)
        last_name, first_part = last_name.strip(), first_part.strip()
        if not last_name or not first_part:
            return None
        return (last_name, first_part, call_sign)
    if "," not in s:
        return None
    last_name, first_part = s.split(",", 1)
    last_name, first_part = last_name.strip(), first_part.strip()
    if not last_name or not first_part:
        return None
    return (last_name, first_part, None)


def _parse_us_or_iso_date_cell(value: str) -> Optional[date]:
    text = (value or "").strip()
    if not text or text.lower() in _EXCEL_ERR_TOKENS:
        return None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return date(year, month, day)
    try:
        return _parse_iso_date(text)
    except ValueError:
        return None


def _excel_serial_to_date(serial: float) -> Optional[date]:
    """Convert Excel serial day number to a calendar date (uses openpyxl when available)."""
    try:
        from openpyxl.utils.datetime import from_excel

        dt = from_excel(serial)
        d = dt.date() if isinstance(dt, datetime) else dt
        if 1990 <= d.year <= 2100:
            return d
    except Exception:
        pass
    try:
        base = date(1899, 12, 30)
        d = base + timedelta(days=int(round(float(serial))))
        if 1990 <= d.year <= 2100:
            return d
    except (OverflowError, ValueError, OSError):
        pass
    return None


def _parse_roster_payment_date_from_note(raw: str) -> Optional[date]:
    """First payment date from a roster payment note (US date, ISO, or Excel serial as float string)."""
    raw_st = (raw or "").strip()
    if not raw_st or raw_st.lower() in _EXCEL_ERR_TOKENS:
        return None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw_st)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return date(year, month, day)
    try:
        return _parse_iso_date(raw_st)
    except ValueError:
        pass
    try:
        ser = float(raw_st.replace(",", ""))
    except ValueError:
        return None
    if 20000 <= ser <= 60000:
        return _excel_serial_to_date(ser)
    return None


def _roster_payment_entries_from_cells(cells: dict[str, str]) -> list[tuple[date, date, str]]:
    """Build (payment_date, paid_through_dec31, raw) for 2026/2025/2024 columns D, F, H."""
    out: list[tuple[date, date, str]] = []
    for col, membership_year in (("D", 2026), ("F", 2025), ("H", 2024)):
        raw = (cells.get(col) or "").strip()
        if not raw:
            continue
        pay_dt = _parse_roster_payment_date_from_note(raw)
        if pay_dt is None:
            continue
        out.append((pay_dt, date(membership_year, 12, 31), raw))
    return out


def _map_license_class_name(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    stripped = raw.strip()
    key = stripped.lower()
    if key in _LICENSE_CLASS_ALIASES:
        return _LICENSE_CLASS_ALIASES[key]
    t = title_case_import_field_if_all_caps(stripped)
    return t if t is not None else stripped


def _parse_bool_cell(value: str) -> bool:
    t = (value or "").strip().upper()
    return t in ("Y", "YES", "1", "TRUE", "T")


def _parse_optional_int_cell(value: str) -> Optional[int]:
    text = (value or "").strip()
    if not text or text.lower() in _EXCEL_ERR_TOKENS:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _is_valid_nonblank_email(value: str) -> bool:
    """True if ``value`` looks like a single simple email (column I may hold non-email labels such as ``paid``)."""
    s = (value or "").strip()
    if not s or "@" not in s or s.count("@") != 1:
        return False
    local, domain = s.split("@", 1)
    if not local or not domain or "." not in domain:
        return False
    if any(c.isspace() for c in s):
        return False
    return True


def _roster_email_from_cells(cells: dict[str, str]) -> Optional[str]:
    """Roster layout: column I when it is a valid email, else column L; stored lowercased."""
    i_val = (cells.get("I") or "").strip()
    if i_val and _is_valid_nonblank_email(i_val):
        return i_val.lower()
    l_val = (cells.get("L") or "").strip()
    return l_val.lower() if l_val else None


def _membership_type_raw_for_row(row: SpreadsheetRow, default_membership_type: str) -> Optional[str]:
    if row.membership_type:
        return row.membership_type
    if default_membership_type.strip():
        return default_membership_type.strip()
    return None


def import_rows(
    session: Session,
    rows: list[SpreadsheetRow],
    replace_existing: bool = False,
    *,
    default_membership_type: str = "",
) -> tuple[int, int, int]:
    if replace_existing:
        session.execute(delete(Payment))
        session.execute(delete(Member))
        session.flush()

    imported_members = 0
    imported_payments = 0
    rows_with_g = sum(1 for r in rows if r.membership_type)
    existing_calls: set[str] = set()
    existing_no_call_names: set[tuple[str, str]] = set()
    for m in session.execute(select(Member)).scalars():
        if m.call_sign:
            existing_calls.add(m.call_sign.strip().upper())
        else:
            existing_no_call_names.add((m.last_name.casefold(), m.first_name.casefold()))

    for row in rows:
        if row.call_sign:
            if row.call_sign.strip().upper() in existing_calls:
                continue
        else:
            name_key = (row.last_name.casefold(), row.first_name.casefold())
            if name_key in existing_no_call_names:
                continue

        license_class_id = None
        if row.license_class:
            license_class = _get_or_create_license_class(session, row.license_class)
            license_class_id = license_class.id

        member = Member(
            last_name=row.last_name,
            first_name=row.first_name,
            call_sign=row.call_sign,
            email=row.email,
            phone=normalize_phone_us_ten_digit(row.phone),
            address_street=row.address_street,
            address_city=row.address_city,
            address_state=row.address_state,
            address_zip=row.address_zip,
            license_class_id=license_class_id,
            paid_through=row.paid_through,
            membership_type_id=None,
            arrl_member=row.arrl_member,
            key_number=row.key_number,
        )
        session.add(member)
        session.flush()
        imported_members += 1
        if row.call_sign:
            existing_calls.add(row.call_sign.strip().upper())
        else:
            existing_no_call_names.add((row.last_name.casefold(), row.first_name.casefold()))

        mt_source = _membership_type_raw_for_row(row, default_membership_type)

        if row.roster_historical_payments:
            mt_id = _resolve_membership_type_id(session, mt_source)
            for pay_dt, paid_through, raw_note in row.roster_historical_payments:
                _, form_number = split_trailing_form_number_from_comment(raw_note)
                session.add(
                    Payment(
                        member_id=member.id,
                        payment_date=pay_dt,
                        paid_through=paid_through,
                        membership_year=paid_through.year,
                        membership_type_id=mt_id,
                        notes=None,
                        form_number=form_number,
                    )
                )
            session.flush()
            imported_payments += len(row.roster_historical_payments)
            crud.sync_member_membership_from_latest_payment(session, member, commit=False)
        elif row.paid_through is not None:
            mt_id = _resolve_membership_type_id(session, mt_source)
            inferred_payment = Payment(
                member_id=member.id,
                payment_date=date.today(),
                paid_through=row.paid_through,
                membership_year=row.paid_through.year,
                membership_type_id=mt_id,
                notes=None,
            )
            session.add(inferred_payment)
            session.flush()
            imported_payments += 1
            crud.sync_member_membership_from_latest_payment(session, member, commit=False)
        elif mt_source:
            member.membership_type_id = _resolve_membership_type_id(session, mt_source)
            session.add(member)
            session.flush()

    session.commit()
    return imported_members, imported_payments, rows_with_g


def _resolve_membership_type_id(session: Session, raw: Optional[str]) -> Optional[int]:
    if not raw or not raw.strip():
        return None
    name = canonical_membership_name(raw)
    item = session.execute(select(MembershipType).where(MembershipType.name == name)).scalar_one_or_none()
    if item is not None:
        return item.id
    item = MembershipType(name=name)
    session.add(item)
    session.flush()
    return item.id


def _read_shared_strings(workbook_zip: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook_zip.namelist():
        return []
    root = ET.fromstring(workbook_zip.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for string_item in root.findall(".//x:si", XML_NS):
        text_parts = [node.text or "" for node in string_item.findall(".//x:t", XML_NS)]
        values.append("".join(text_parts))
    return values


def _inline_cell_text(cell: ET.Element) -> str:
    is_node = cell.find("x:is", XML_NS)
    if is_node is None:
        return ""
    parts = [node.text or "" for node in is_node.findall(".//x:t", XML_NS)]
    return "".join(parts)


def _extract_row_values(row: ET.Element, shared_strings: list[str]) -> dict[str, str]:
    row_values: dict[str, str] = {}
    for cell in row.findall("x:c", XML_NS):
        reference = cell.attrib.get("r", "")
        column = re.sub(r"\d", "", reference)
        cell_type = cell.attrib.get("t")
        if cell_type == "inlineStr":
            value = _inline_cell_text(cell)
        else:
            value_node = cell.find("x:v", XML_NS)
            if value_node is None or value_node.text is None:
                value = ""
            elif cell_type == "s":
                idx = int(value_node.text)
                value = shared_strings[idx] if 0 <= idx < len(shared_strings) else ""
            else:
                value = value_node.text
        row_values[column] = value.strip()
    return row_values


def _validate_header(values_by_col: dict[str, str]) -> None:
    values = _to_ordered_values(values_by_col)
    expected_prefix = ["Last Name", "First Name", "Call Sign", "Email", "Phone", "Paid Through"]
    if values[:6] != expected_prefix:
        raise ValueError(f"Unexpected spreadsheet header (A–F): {values[:6]}")
    if values[6] not in HEADER_COL_G:
        raise ValueError(f"Column G must be 'Membership Type' or 'Status', got {values[6]!r}")
    if values[7] != "License Class":
        raise ValueError(f"Unexpected column H (expected 'License Class'): {values[7]!r}")


def _to_ordered_values(values_by_col: dict[str, str]) -> list[str]:
    return [values_by_col.get(column, "") for column in ["A", "B", "C", "D", "E", "F", "G", "H"]]


def _to_spreadsheet_row(values: list[str]) -> SpreadsheetRow:
    raw_call = values[2].strip().upper()
    return SpreadsheetRow(
        last_name=normalize_last_name(values[0]),
        first_name=normalize_first_name(values[1]),
        call_sign=raw_call or None,
        email=_none_if_blank(values[3]),
        phone=_none_if_blank(values[4]),
        paid_through=_parse_iso_date(values[5]),
        membership_type=title_case_import_field_if_all_caps(_none_if_blank(values[6])),
        license_class=_map_license_class_name(_none_if_blank(values[7])),
        arrl_member=False,
        key_number=None,
        roster_historical_payments=None,
    )


def _parse_iso_date(value: str) -> Optional[date]:
    if not value:
        return None
    return date.fromisoformat(value)


def _none_if_blank(value: str) -> Optional[str]:
    clean = value.strip()
    if not clean:
        return None
    if clean.lower() in _EXCEL_ERR_TOKENS:
        return None
    return clean


def _get_or_create_license_class(session: Session, name: str) -> LicenseClass:
    item = session.execute(select(LicenseClass).where(LicenseClass.name == name)).scalar_one_or_none()
    if item is not None:
        return item
    item = LicenseClass(name=name)
    session.add(item)
    session.flush()
    return item


def main() -> int:
    args = parse_args()
    rows = read_spreadsheet_rows(args.spreadsheet)

    engine = create_engine(
        args.database_url,
        connect_args={"check_same_thread": False} if args.database_url.startswith("sqlite") else {},
    )
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
    Base.metadata.create_all(bind=engine)
    with session_local() as session:
        member_count, payment_count, rows_with_g = import_rows(
            session=session,
            rows=rows,
            replace_existing=bool(args.replace),
            default_membership_type=args.default_membership_type,
        )
    print(f"Imported {member_count} members and {payment_count} inferred payments.")
    if rows_with_g == 0 and not args.default_membership_type.strip():
        print(
            "Warning: no membership-type values were read from the spreadsheet (legacy column G empty on every row). "
            "For the older eight-column report, Excel often omits blank cells — use "
            '--default-membership-type "Regular" if needed. The "dvra_membership.xlsx" roster layout uses column B.',
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
