"""Filesystem roots for the CGI app."""

from __future__ import annotations

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT_DIR = PACKAGE_DIR.parent
TEMPLATE_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"
SCHEMA_PATH = ROOT_DIR / "database" / "schema.sqlite.sql"
VAR_DIR = ROOT_DIR / "var"
SESSIONS_DIR = VAR_DIR / "sessions"
DEFAULT_SQLITE_PATH = VAR_DIR / "dvra_membership.sqlite"
