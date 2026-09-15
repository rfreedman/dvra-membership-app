"""SQLAlchemy declarative base for import-time ORM models.

No global engine: ``import_from_spreadsheet`` builds its own engine from ``--database-url``.
"""

from __future__ import annotations

from sqlalchemy.orm import declarative_base

Base = declarative_base()
