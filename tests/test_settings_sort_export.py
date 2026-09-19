from __future__ import annotations

import re
from pathlib import Path

from dvra.admin_accounts import AdminAccountRepository
from dvra.exports import timestamp_stem
from dvra.member_list import MemberListRepository
from dvra.reference_data import ReferenceDataRepository
from dvra.settings import Settings
from dvra.sort_toggle import next_sort_choice, normalize_sort

from tests.conftest import memory_db

_SETTINGS_KEYS = (
    "DATABASE_DSN",
    "DVRA_ADMIN_USERNAME",
    "DVRA_ADMIN_PASSWORD",
    "DVRA_DISPLAY_ERRORS",
    "DVRA_SESSION_COOKIE",
    "DVRA_SESSION_MAX_AGE",
)


def test_normalize_and_toggle_sort():
    assert normalize_sort("bogus", "DESC", ["name", "email"], "name") == ("name", "desc")
    assert normalize_sort("email", "asc", ["name", "email"], "name") == ("email", "asc")
    assert next_sort_choice("name", "asc", "name") == ("name", "desc")
    assert next_sort_choice("name", "desc", "name") == ("name", "asc")
    assert next_sort_choice("name", "asc", "email") == ("email", "asc")
    assert next_sort_choice("name", "asc", "payment_date", desc_first=("payment_date", "paid_through")) == (
        "payment_date",
        "desc",
    )


def test_compact_timestamp_stem_format():
    compact = timestamp_stem("payments-report", compact=True)
    assert re.fullmatch(r"payments-report-\d{8}-\d{6}", compact)
    wide = timestamp_stem("members")
    assert re.fullmatch(r"members-\d{4}-\d{2}-\d{2}-\d{6}", wide)


def test_settings_dotenv_overlay_env_wins(tmp_path: Path, monkeypatch):
    for key in _SETTINGS_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr("dvra.settings.ROOT_DIR", tmp_path)
    (tmp_path / ".env").write_text(
        "DVRA_ADMIN_USERNAME=fileuser\nDVRA_SESSION_COOKIE=filecookie\nDVRA_SESSION_MAX_AGE=123\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DVRA_ADMIN_USERNAME", "envuser")
    loaded = Settings.load()
    assert loaded.admin_username == "envuser"
    assert loaded.session_cookie_name == "filecookie"
    assert loaded.session_max_age == 123


def test_member_list_uses_reference_membership_types():
    conn = memory_db()
    ref = ReferenceDataRepository(conn)
    ref.create_membership_type("Family")
    listed = MemberListRepository(conn).list_membership_types()
    assert listed == ref.list_membership_types()
    assert [row["name"] for row in listed] == ["Family", "New Ham"]


def test_username_unique_across_admin_and_manager_tables():
    conn = memory_db()
    accounts = AdminAccountRepository(conn)
    accounts.create_admin_user("shared", "pw1")
    try:
        accounts.create_manager("shared", "pw2", None)
        raised = False
    except Exception:
        raised = True
    assert raised
    accounts.create_manager("other", "pw3", "Pat")
    try:
        accounts.create_admin_user("other", "pw4")
        raised = False
    except Exception:
        raised = True
    assert raised
