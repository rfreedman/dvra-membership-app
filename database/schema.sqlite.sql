-- SQLite schema aligned with python/app/models.py (DVRA Membership Manager).
-- Applied on bootstrap via Schema::ensure() (PRAGMA foreign_keys is enabled in PDO).

CREATE TABLE IF NOT EXISTS license_classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(64) NOT NULL,
    CONSTRAINT uq_license_class_name UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS membership_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(64) NOT NULL,
    CONSTRAINT uq_membership_type_name UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS admin_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(128) NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    CONSTRAINT uq_admin_user_username UNIQUE (username)
);

CREATE TABLE IF NOT EXISTS managers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(128) NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    display_name VARCHAR(256),
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    CONSTRAINT uq_manager_username UNIQUE (username)
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    last_name VARCHAR(128) NOT NULL,
    first_name VARCHAR(128) NOT NULL,
    call_sign VARCHAR(32),
    email VARCHAR(320),
    phone VARCHAR(64),
    address_street TEXT,
    address_city TEXT,
    address_state VARCHAR(16),
    address_zip VARCHAR(16),
    license_class_id INTEGER REFERENCES license_classes(id),
    membership_type_id INTEGER REFERENCES membership_types(id),
    arrl_member INTEGER NOT NULL DEFAULT 0,
    key_number INTEGER,
    paid_through TEXT,
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_members_call_sign_when_set ON members (call_sign) WHERE call_sign IS NOT NULL;

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    payment_date TEXT NOT NULL,
    paid_through TEXT NOT NULL,
    membership_year INTEGER NOT NULL,
    membership_type_id INTEGER REFERENCES membership_types(id) ON DELETE SET NULL,
    notes TEXT,
    form_number VARCHAR(64),
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE INDEX IF NOT EXISTS ix_payments_member_id ON payments (member_id);
