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

Anyone who signs in uses one of three account types. Each type is stored in its own table (`admin_users`, `managers`, `readonly_users`). At login, the app checks those tables in that order; if the same username exists in more than one, the first match wins (admin over manager over read-only).

- **Admin** — Full use of the app: members, payments, and reports, plus the **Admin** page (settings, reference data, and creating or changing accounts).
- **Manager** — Same day-to-day work as an admin (members, payments, reports), but no Admin page and no account management.
- **Read-only** — Can browse members and payments and run reports (including changing filters and sorts). Cannot add or edit records, create members, or open Admin.

Creating an account rejects a username that already exists in any of the three tables.

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
| `DVRA_ROSTER_CORS_ORIGIN` | `Access-Control-Allow-Origin` for the public roster JSON API (`www` and apex counterparts are also accepted) | `https://w2zq.com` |

PDF fonts, membership year range (2000–2100), and the Tabulator CDN URL are code constants, not env.

On **Admin**, **Late-join extension** settings (`new_member_extension_start` and `new_ham_extension_start`, stored as `MM-DD`, defaults August 1 and November 1) control when **Create member** with an initial payment extends paid-through to December 31 of the year after the paid membership year. New Ham members in the New Ham window get the New Ham extension note; other new members in the general window get the general note.

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

Optional flags: `--replace` (delete existing members/payments first), `--default-membership-type "Individual"` (when the spreadsheet omits membership type).

Rewrite existing phones to US `NXX-NXX-XXXX`:

```bash
python scripts/normalize_member_phones.py
```

## Exports

Member and report downloads are CSV (UTF-8 with BOM), XLSX, and PDF. PDFs embed **DejaVu Sans** so names and notes stay Unicode (UTF-16 in the PDF). Font license: `dvra/fonts/LICENSE`. List-page export links are bare paths; filters and sorts come from the session, not the query string.

## Hosting

Document root is this directory (the one that contains `index.py`, `dvra/`, `templates/`, and `static/`). Nested pages are `/index.py/...` unless the host maps unknown paths to `index.py` with PATH_INFO. Templates link CSS/JS/images as **`/static/...`**. Apache should serve those as real files; if a request still reaches CGI as `PATH_INFO=/static/...` (for example `/index.py/static/style.css`), the app serves the file itself. `.htaccess` also rewrites `/index.py/static/` to `/static/`.

### Public member roster (WordPress)

Unauthenticated endpoints expose **current-year** members only (name + call sign), matching the admin roster rule. No email, address, phone, or notes.

| URL | Purpose |
| --- | --- |
| `GET /api/roster` (or `/index.py/api/roster`) | JSON: `membership_year`, `generated_at`, `by_name`, `by_callsign` |
| `OPTIONS /api/roster` | CORS preflight (204) |
| `GET /api/roster/embed` | Lightweight HTML with **By Name** / **By Callsign** tabs for an iframe |

CORS: `Access-Control-Allow-Origin` is `DVRA_ROSTER_CORS_ORIGIN` (default `https://w2zq.com`) or its `www`/apex counterpart when the request `Origin` matches (so `w2zq.com` → `www.w2zq.com` still works). Responses use `Cache-Control: public, max-age=300` and do **not** set a session cookie. The embed posts height to the actual parent origin (apex or `www`), and falls back to each allowlisted origin when the parent origin is hidden (Brave).

**WordPress iframe (closest to the old Google Sheet):** the embed reports its height with `postMessage`. Paste this Custom HTML (iframe `src` can use `/index.py/api/roster/embed` if rewrites do not apply). Use **`width: 100%`** (not a fixed `30rem`) so the iframe fits the content column when the theme sidebar stacks under it on phones. `70vh` is only a placeholder until the first message arrives:

```html
<div id="dvra-roster-wrap" style="width: 100%; max-width: 30rem; margin: auto;">
  <iframe
    id="dvra-roster"
    title="DVRA member roster"
    src="https://membership-app.w2zq.com/api/roster/embed"
    style="width: 100%; height: 70vh; min-height: 24rem; border: 0; margin-top: 10px; display: block;">
  </iframe>
</div>
<script>
(function () {
  var iframe = document.getElementById("dvra-roster");
  if (!iframe) return;
  var wrap = document.getElementById("dvra-roster-wrap") || iframe.parentElement;
  if (wrap) {
    wrap.style.width = "100%";
    wrap.style.maxWidth = "30rem";
    wrap.style.marginLeft = "auto";
    wrap.style.marginRight = "auto";
  }
  iframe.style.width = "100%";
  iframe.style.maxWidth = "100%";
  iframe.style.display = "block";
  window.addEventListener("message", function (event) {
    if (event.origin !== "https://membership-app.w2zq.com") return;
    if (event.source !== iframe.contentWindow) return;
    if (!event.data || event.data.source !== "dvra-roster") return;
    var h = Number(event.data.height);
    if (h > 0) iframe.style.height = h + "px";
  });
})();
</script>
```

**WordPress JSON:** `fetch('https://<membership-host>/index.py/api/roster')` and build two panels from `by_name` / `by_callsign`.

### DreamHost CGI (`.htaccess`)

Copy [`.htaccess`](.htaccess) next to `index.py`. It is:

```
Options +ExecCGI
AddHandler cgi-script .py
DirectoryIndex index.py index.html
```

`DirectoryIndex` lists **`index.py` first**, so a request to `/` does **not** serve `index.html`. Apache runs `index.py` as CGI. That is why `/index.html` can return 200 while `/` returns 500.

| URL | What Apache does |
| --- | --- |
| `/` | DirectoryIndex → execute `index.py` (CGI) |
| `/index.html` | static file |
| `/index.py` | execute `index.py` (CGI) |
| `/index.py/health` | CGI with `PATH_INFO=/health`; body should be `OK` |

If `/index.py` is also 500, ignore `index.html` and fix CGI. DreamHost already treats `.py` as CGI; if `error.log` says `Invalid command 'Options'`, comment out `Options +ExecCGI` (and try without `AddHandler`) and keep `DirectoryIndex index.py`.

`index.py` must be mode **755**, UNIX **LF** line endings. Prefer a shebang that points at the **server** venv so Apache does not start system Python and then re-exec (double cold start):

```
#!/home/USERNAME/path/to/docroot/.venv/bin/python3
```

`index.py` will still re-exec `.venv/bin/python3` when the shebang is `/usr/bin/python3` and a local `.venv` exists. Do not copy a Mac `.venv` to the server.

### Diagnose a 500 at `/`

1. Compare the four URLs above. `/` 500 + `/index.html` 200 means DirectoryIndex is invoking CGI.
2. Read `~/logs/<domain>/https/error.log` (or the domain’s `error.log`) while reloading `/` and `/index.py`:
   - `Invalid command 'Options'` → comment out `Options +ExecCGI` in `.htaccess`
   - `Premature end of script headers` → script never printed CGI headers (crash on import, bad shebang, or not executable)
   - `python3\r` / `bad interpreter` → CRLF line endings
   - `Permission denied` / suexec → not 755, or a directory is `777`
   - `ModuleNotFoundError` (`jinja2`, `bcrypt`, `dotenv`, `openpyxl`, `fpdf`) → create a venv **on the server** (below)
3. On the server, from the document root:

```bash
chmod 755 index.py
mkdir -p var/sessions
python3 -m venv .venv
.venv/bin/pip install jinja2 openpyxl fpdf2 bcrypt python-dotenv
```

`index.py` re-execs `.venv/bin/python3` when that file exists (unless the process is already that interpreter). CGI packages are those five; `requirements.txt` also has pytest/sqlalchemy for local tests and the spreadsheet importer.

Each CGI request starts a new Python process, so sub-second responses are uncommon on shared hosting. The app defers heavy imports (openpyxl/fpdf/bcrypt), skips schema work after the first migration via `PRAGMA user_version`, and handles `/members/session-touch` without opening the database.

4. Confirm CGI without Apache:

```bash
export REQUEST_METHOD=GET PATH_INFO=/health SCRIPT_NAME=/index.py QUERY_STRING= CONTENT_LENGTH=0
./index.py
```

A pass starts with `Status: 200 OK` and body `OK`. Optional: `DVRA_DISPLAY_ERRORS=1` in `.env` so application 500s include a traceback; turn it off afterward.
