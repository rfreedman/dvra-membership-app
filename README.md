# DVRA Membership Manager

Python **CGI** app (no FastAPI/Flask). The host executes **`index.py`** for `/` and other `.py` files by URL. Nested routes use **PATH_INFO** under `index.py` (for example `/index.py/members/new`).

| Path | Role |
| --- | --- |
| `index.py` | CGI entry |
| `dvra/` | Application code (sqlite3, sessions, routes, exports) |
| `templates/` | Jinja2 HTML |
| `static/` | CSS, JS, and site icon |
| `database/schema.sqlite.sql` | SQLite schema |
| `dvra/fonts/` | DejaVu Sans for PDF exports (see `dvra/fonts/LICENSE`) |

Default database: **`var/dvra_membership.sqlite`**.

## Roles

Two account tables stay separate (`admin_users` and `managers`). Login looks up **admins first**, then managers (an overlapping username is treated as admin).

- **Admin** — members, reports, payments, and **Admin** (reference data and account CRUD).
- **Manager** — members, reports, and payments. No Admin nav; `/admin` and `/managers/*` redirect home.

Creating an admin or manager rejects a username that already exists in **either** table.

## Local run

Python **3.10+**. From the repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/dev_server.py
```

Then open:

- http://127.0.0.1:8089/login
- http://127.0.0.1:8089/health → `OK`

The local server also accepts CGI-style paths: http://127.0.0.1:8089/index.py/login

Optional: `--host` / `--port` (default `127.0.0.1:8089`). Restart the process after changing Python modules; CSS/templates reload on the next request.

## Configuration

Settings load from the process environment. If a **`.env`** file exists in the repo root, it is loaded first; **real environment variables win**. Do not commit `.env`.

| Variable | Purpose | Default |
| --- | --- | --- |
| `DATABASE_DSN` | SQLite DSN (`sqlite:/path/to/db`) | `sqlite:` + `var/dvra_membership.sqlite` |
| `DVRA_ADMIN_USERNAME` | Bootstrap admin username when `admin_users` is empty | `admin` |
| `DVRA_ADMIN_PASSWORD` | Bootstrap admin password when `admin_users` is empty | `admin123` |
| `DVRA_DISPLAY_ERRORS` | Include a traceback in HTTP 500 responses (`1` / `true` / `yes` / `on`) | off |
| `DVRA_SESSION_COOKIE` | Session cookie name | `dvra_session` |
| `DVRA_SESSION_MAX_AGE` | Session cookie Max-Age in seconds | `2592000` (30 days) |

PDF fonts, membership year range (2000–2100), and the Tabulator CDN URL are code constants, not env.

Example:

```bash
export DATABASE_DSN="sqlite:$(pwd)/var/custom.sqlite"
python scripts/dev_server.py
```

## Tests

```bash
pytest
```

## Spreadsheet import (one-off)

Not part of the CGI app. Uses SQLAlchemy only for this CLI. From the repo root:

```bash
python scripts/import_from_spreadsheet.py \
  --spreadsheet /path/to/roster.xlsx \
  --database-url "sqlite:////absolute/path/to/var/dvra_membership.sqlite"
```

Optional flags: `--replace` (delete existing members/payments first), `--default-membership-type "Regular"` (when the spreadsheet omits membership type).

Rewrite existing phones to US `NXX-NXX-XXXX`:

```bash
python scripts/normalize_member_phones.py
```

## Exports

Member and report downloads are CSV (UTF-8 with BOM), XLSX, and PDF. PDFs embed **DejaVu Sans** so names and notes stay Unicode (UTF-16 in the PDF). Font license: `dvra/fonts/LICENSE`. List-page export links are bare paths; filters and sorts come from the session, not the query string.

## Hosting

Document root is the repo root. The host should execute `index.py` for `/`. Nested pages are `/index.py/...` unless the host maps unknown paths to `index.py` with PATH_INFO. Static files are served as files from **`static/`**.
