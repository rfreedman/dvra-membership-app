from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from dvra.membership_report import (
    MembershipReportRepository,
    membership_report_month_options,
    membership_report_year_options,
    parse_membership_report_query,
)
from dvra.membership_report_export import membership_report_pdf
from dvra.passwords import hash_password
from dvra.payments import PaymentRepository
from dvra.reference_data import ReferenceDataRepository

from tests.conftest import insert_member, memory_db
from tests.test_cgi_login import _login_readonly, _run, _session_id


def _login_manager(tmp_path: Path, username: str = "mgr", password: str = "mgrpass") -> tuple[str, str, Path]:
    db = tmp_path / "t.sqlite"
    dsn = "sqlite:" + str(db)
    _run("GET", "/login", dsn=dsn)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO managers (username, password_hash) VALUES (?, ?)",
        (username, hash_password(password)),
    )
    conn.commit()
    conn.close()
    status, headers, _ = _run(
        "POST", "/login", body=f"username={username}&password={password}", dsn=dsn
    )
    assert status == 303
    sid = _session_id(headers)
    return f"dvra_session={sid}", dsn, db


def _pay(conn, member_id: int, payment_date: str, year: int) -> None:
    PaymentRepository(conn).insert_payment(
        member_id,
        {
            "payment_date": payment_date,
            "membership_year": year,
            "membership_type_id": None,
            "notes": None,
            "form_number": None,
        },
    )


def _seed_report_db() -> sqlite3.Connection:
    conn = memory_db()
    ref = ReferenceDataRepository(conn)
    ref.create_license_class("Technician")
    ref.create_license_class("General")
    tech = int(conn.execute("SELECT id FROM license_classes WHERE name = 'Technician'").fetchone()[0])
    gen = int(conn.execute("SELECT id FROM license_classes WHERE name = 'General'").fetchone()[0])

    a = insert_member(conn, "Alpha", "Ann")
    b = insert_member(conn, "Bravo", "Bob")
    c = insert_member(conn, "Charlie", "Cara")
    d = insert_member(conn, "Delta", "Dee")
    e = insert_member(conn, "Echo", "Ed")
    f = insert_member(conn, "Foxtrot", "Fay")

    conn.execute("UPDATE members SET license_class_id = ?, arrl_member = 1 WHERE id = ?", (tech, a))
    conn.execute("UPDATE members SET license_class_id = ?, arrl_member = 1 WHERE id = ?", (tech, b))
    conn.execute("UPDATE members SET license_class_id = ?, arrl_member = 0 WHERE id = ?", (gen, c))
    conn.execute("UPDATE members SET license_class_id = ?, arrl_member = 0 WHERE id = ?", (tech, d))
    conn.execute("UPDATE members SET license_class_id = ?, arrl_member = 0 WHERE id = ?", (gen, e))
    conn.execute("UPDATE members SET license_class_id = ?, arrl_member = 1 WHERE id = ?", (tech, f))
    conn.commit()

    _pay(conn, a, "2025-11-01", 2026)
    _pay(conn, b, "2026-01-10", 2026)
    _pay(conn, c, "2026-02-01", 2026)
    _pay(conn, d, "2026-03-15", 2026)
    _pay(conn, e, "2025-01-01", 2025)
    _pay(conn, e, "2026-03-20", 2026)
    _pay(conn, f, "2026-01-05", 2026)
    return conn


def test_parse_membership_report_defaults():
    today = date(2026, 9, 20)
    parsed = parse_membership_report_query({}, today=today, default_membership_year=2026)
    assert parsed == {
        "membership_year": 2026,
        "calendar_month": 9,
    }
    parsed = parse_membership_report_query(
        {"membership_year": "2025", "calendar_month": "3"},
        today=today,
        default_membership_year=2026,
    )
    assert parsed["membership_year"] == 2025
    assert parsed["calendar_month"] == 3
    # Legacy calendar_year in the form is ignored; membership_year is the report year.
    parsed = parse_membership_report_query(
        {"membership_year": "2026", "calendar_year": "2024", "calendar_month": "3"},
        today=today,
        default_membership_year=2026,
    )
    assert parsed == {"membership_year": 2026, "calendar_month": 3}


def test_parse_membership_report_clamps_future_year_and_month():
    today = date(2026, 9, 20)
    parsed = parse_membership_report_query(
        {"membership_year": "2027", "calendar_month": "1"},
        today=today,
        default_membership_year=2026,
    )
    assert parsed == {"membership_year": 2026, "calendar_month": 1}
    parsed = parse_membership_report_query(
        {"membership_year": "2026", "calendar_month": "12"},
        today=today,
        default_membership_year=2026,
    )
    assert parsed == {"membership_year": 2026, "calendar_month": 9}
    # Past years still allow all months.
    parsed = parse_membership_report_query(
        {"membership_year": "2025", "calendar_month": "12"},
        today=today,
        default_membership_year=2026,
    )
    assert parsed == {"membership_year": 2025, "calendar_month": 12}
    # Future default membership year falls back to calendar year.
    parsed = parse_membership_report_query({}, today=today, default_membership_year=2027)
    assert parsed == {"membership_year": 2026, "calendar_month": 9}


def test_membership_report_filter_options_exclude_future():
    today = date(2026, 9, 20)
    years = membership_report_year_options(2026, today=today, min_year=2024)
    assert years[0] == 2024
    assert years[-1] == 2026
    assert all(y <= 2026 for y in years)
    months = membership_report_month_options(2026, today=today)
    assert [m["value"] for m in months] == list(range(1, 10))
    assert months[-1]["label"] == "September"
    months_past = membership_report_month_options(2025, today=today)
    assert [m["value"] for m in months_past] == list(range(1, 13))


def test_membership_report_aggregations():
    conn = _seed_report_db()
    report = MembershipReportRepository(conn).build_report(
        {"membership_year": 2026, "calendar_month": 3}
    )
    assert report["member_count"] == 6
    assert [r["month"] for r in report["member_counts_by_month"]] == [1, 2, 3]
    by_member_count = {r["month"]: r["count"] for r in report["member_counts_by_month"]}
    assert by_member_count[1] == 3
    assert by_member_count[2] == 4
    assert by_member_count[3] == 6
    assert report["member_counts_by_month"][-1]["count"] == report["member_count"]
    assert report["charts"]["member_count"]["labels"] == ["January", "February", "March"]
    assert report["charts"]["member_count"]["values"] == [3, 4, 6]
    assert report["new_members_month"] == 1
    assert report["new_members_ytd_total"] == 4
    assert [r["month"] for r in report["new_members_ytd"]] == [1, 2, 3]
    by_month = {r["month"]: r["count"] for r in report["new_members_ytd"]}
    assert by_month[1] == 2
    assert by_month[2] == 1
    assert by_month[3] == 1
    assert report["charts"]["new_enrollment"]["labels"] == ["January", "February", "March"]
    assert report["arrl_members"] == 3
    assert report["arrl_non_members"] == 3
    assert report["arrl_percent"] == 50
    assert report["arrl_members_percent"] == 50
    assert report["arrl_non_members_percent"] == 50
    assert report["charts"]["arrl"]["percents"] == [50, 50]
    assert report["report_heading"] == "DVRA Membership - March, 2026"
    license_map = {r["name"]: r["count"] for r in report["license_class"]}
    assert license_map["Technician"] == 4
    assert license_map["General"] == 2
    license_pct = {r["name"]: r["percent"] for r in report["license_class"]}
    assert license_pct["Technician"] == 67
    assert license_pct["General"] == 33
    assert sum(license_pct.values()) == 100
    assert report["charts"]["license_class"]["percents"] == [67, 33]
    assert report["charts"]["arrl"]["values"] == [3, 3]


def test_current_members_respect_as_of_month_via_payment_date():
    """Payment in April for membership year 2026 counts in May, not in March."""
    conn = memory_db()
    early = insert_member(conn, "Early", "Ed")
    late = insert_member(conn, "Late", "Lou")
    _pay(conn, early, "2026-03-15", 2026)
    _pay(conn, late, "2026-04-10", 2026)
    repo = MembershipReportRepository(conn)

    march = repo.build_report({"membership_year": 2026, "calendar_month": 3})
    assert march["member_count"] == 1
    assert march["arrl_members"] + march["arrl_non_members"] == 1
    assert [r["count"] for r in march["member_counts_by_month"]] == [0, 0, 1]

    april = repo.build_report({"membership_year": 2026, "calendar_month": 4})
    assert april["member_count"] == 2
    assert april["arrl_members"] + april["arrl_non_members"] == 2
    assert [r["count"] for r in april["member_counts_by_month"]] == [0, 0, 1, 2]

def test_membership_report_pdf_magic():
    conn = _seed_report_db()
    report = MembershipReportRepository(conn).build_report(
        {"membership_year": 2026, "calendar_month": 3}
    )
    data = membership_report_pdf(report)
    assert data.startswith(b"%PDF-")
    assert len(data) > 5000


def test_membership_report_routes_manager_and_readonly(tmp_path: Path):
    cookie_m, dsn_m, _ = _login_manager(tmp_path / "mgr")
    status, _, body = _run("GET", "/reports/membership", cookie=cookie_m, dsn=dsn_m)
    assert status == 200
    assert b"Membership report" in body
    assert b"License Class Distribution" in body

    status, headers, body = _run("GET", "/reports/membership/export.pdf", cookie=cookie_m, dsn=dsn_m)
    assert status == 200
    assert "pdf" in headers.get("content-type", "")
    assert body.startswith(b"%PDF-")

    status, _, _ = _run("GET", "/reports/membership/export.xlsx", cookie=cookie_m, dsn=dsn_m)
    assert status == 404

    cookie_r, dsn_r, _ = _login_readonly(tmp_path / "ro")
    status, _, body = _run("GET", "/reports/membership", cookie=cookie_r, dsn=dsn_r)
    assert status == 200
    assert b"Membership report" in body

    status, headers, _ = _run(
        "POST",
        "/reports/membership",
        body="membership_year=2026&calendar_month=3",
        cookie=cookie_r,
        dsn=dsn_r,
    )
    assert status == 303
    assert headers.get("location", "").endswith("/reports/membership")
