from __future__ import annotations

from dvra.normalizer import normalize_phone_us_ten_digit, payment_from_form
from dvra.reference_data import ReferenceDataRepository
from dvra.session_query import flatten_scalar_map, merge_post

from tests.conftest import memory_db


def test_phone_normalizer():
    assert normalize_phone_us_ten_digit("9085551212") == "908-555-1212"
    assert normalize_phone_us_ten_digit("1 (908) 555-1212") == "908-555-1212"
    assert normalize_phone_us_ten_digit("123") is None


def test_payment_from_form_requires_year():
    out = payment_from_form({"payment_date": "2026-01-02", "membership_year": ""})
    assert out["ok"] is False
    ok = payment_from_form({"payment_date": "2026-01-02", "membership_year": "2026"})
    assert ok["ok"] is True
    assert ok["data"]["membership_year"] == 2026


def test_membership_type_delete_blocked_by_current_year_payment():
    conn = memory_db()
    conn.execute("INSERT INTO membership_types (name) VALUES ('Annual')")
    conn.commit()
    tid = int(conn.execute("SELECT id FROM membership_types").fetchone()[0])
    conn.execute(
        """
        INSERT INTO members (last_name, first_name, arrl_member, created_at, updated_at)
        VALUES ('A', 'B', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
    )
    mid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.execute(
        """
        INSERT INTO payments (member_id, payment_date, paid_through, membership_year, membership_type_id, created_at)
        VALUES (?, '2026-01-01', '2026-12-31', 2026, ?, CURRENT_TIMESTAMP)
        """,
        (mid, tid),
    )
    conn.commit()
    ref = ReferenceDataRepository(conn)
    assert ref.membership_type_blocked_by_payments(tid, 2026) is True
    try:
        ref.delete_membership_type_or_fail(tid, 2026)
        raised = False
    except RuntimeError:
        raised = True
    assert raised


def test_session_query_merge_and_clear():
    session = {"k": {"search": "old", "arrl": "yes"}}
    merged = merge_post(session, "k", {"search": "new"}, None)
    assert merged["search"] == "new"
    assert merged["arrl"] == "yes"
    cleared = merge_post(session, "k", {"reset_list_filters": "1", "search": "x"}, "reset_list_filters")
    assert cleared == {}
    assert flatten_scalar_map({"a": ["1", "2"]})["a"] == "2"
