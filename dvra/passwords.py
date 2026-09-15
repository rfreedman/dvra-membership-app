"""bcrypt password hashing (also verifies $2y$ hashes)."""

from __future__ import annotations


def hash_password(raw: str) -> str:
    import bcrypt

    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(raw: str, stored: str) -> bool:
    import bcrypt

    if not stored:
        return False
    hashed = stored
    if hashed.startswith("$2y$"):
        hashed = "$2b$" + hashed[4:]
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False
