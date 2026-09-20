from datetime import date

from scripts.import_from_spreadsheet import canonical_membership_name, parse_roster_payment_cell


def test_canonical_membership_name_title_cases_lowercase():
    assert canonical_membership_name("individual") == "Individual"
    assert canonical_membership_name("Individual") == "Individual"
    assert canonical_membership_name("waived") == "New Ham"


def test_parse_full_date_and_trailing_form_number():
    pay_dt, notes, form_number = parse_roster_payment_cell("1/10/2026 (610)", 2026)
    assert pay_dt == date(2026, 1, 10)
    assert notes is None
    assert form_number == "610"


def test_parse_glued_full_date():
    pay_dt, notes, form_number = parse_roster_payment_cell("Paid  ProRated10/11/2024 Form 336", 2025)
    assert pay_dt == date(2024, 10, 11)
    assert form_number is None
    assert notes is not None
    assert "ProRated" in notes or "Form 336" in notes


def test_parse_month_year_uses_first_of_month():
    pay_dt, notes, form_number = parse_roster_payment_cell("2/2024 (295)", 2024)
    assert pay_dt == date(2024, 2, 1)
    assert form_number == "295"
    assert notes is None


def test_parse_month_name_year():
    pay_dt, notes, _form = parse_roster_payment_cell("Joined Club August 2025", 2026)
    assert pay_dt == date(2025, 8, 1)
    assert notes is not None
    assert "Joined Club" in notes


def test_parse_month_day_uses_column_year():
    pay_dt, notes, _form = parse_roster_payment_cell("CHK - 11/25 - Email Greg", 2025)
    assert pay_dt == date(2025, 11, 25)
    assert notes is not None
    assert "CHK" in notes
    assert "Email Greg" in notes


def test_parse_no_date_uses_january_first_and_approximate_note():
    pay_dt, notes, form_number = parse_roster_payment_cell("Free 2026 new ham", 2026)
    assert pay_dt == date(2026, 1, 1)
    assert form_number is None
    assert notes == "payment date approximate; Free 2026 new ham"
