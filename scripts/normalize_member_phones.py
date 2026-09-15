#!/usr/bin/env python3
"""Rewrite stored member phones to US NXX-NXX-XXXX (or NULL)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dvra.db import connect
from dvra.members import MemberRepository
from dvra.schema import ensure
from dvra.settings import Settings


def main() -> None:
    settings = Settings()
    conn = connect(settings)
    ensure(conn)
    n = MemberRepository(conn).normalize_stored_member_phones_to_us_ten_digit()
    print(f"Updated {n} member phone row(s).")


if __name__ == "__main__":
    main()
