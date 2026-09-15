"""PATH_INFO routing under index.py."""

from __future__ import annotations

import re
import sqlite3
from datetime import date
from typing import Any

from dvra import exports
from dvra import http as htt
from dvra import list_params
from dvra import membership_year as myear
from dvra import member_list
from dvra import normalizer
from dvra import payments_report
from dvra import reports as reports_mod
from dvra import view
from dvra.admin_accounts import AdminAccountRepository
from dvra.app_settings import AppSettingsRepository
from dvra.members import DuplicateMemberKeyNumber, MemberRepository
from dvra.member_list import MemberListRepository
from dvra.passwords import verify_password
from dvra.payments import PaymentRepository
from dvra.payments_report import PaymentsReportRepository
from dvra.reference_data import ReferenceDataRepository
from dvra.reports import ReportsRepository


def _html_page(
    inner: str,
    title: str,
    *,
    authenticated: bool = False,
    active_nav: str = "",
    extra_head: str = "",
    extra_scripts: str = "",
    status: int = 200,
) -> htt.Response:
    body = view.wrap_html(
        inner,
        title,
        authenticated=authenticated,
        active_nav=active_nav,
        extra_head_html=extra_head,
        extra_scripts_html=extra_scripts,
    )
    return htt.html(body, status=status)


def _auth_ok(session: dict[str, Any]) -> bool:
    return session.get("admin_id") is not None


def _need_login() -> htt.Response:
    return htt.redirect(htt.url_for("/login"), status=302)


def _ref_write_error(exc: Exception) -> str | None:
    msg = str(exc)
    if "UNIQUE constraint" in msg:
        return "That name already exists."
    if "FOREIGN KEY constraint" in msg:
        return "Cannot delete item while records still reference it."
    return None


def dispatch(conn: sqlite3.Connection, session: dict[str, Any], form: dict[str, Any]) -> htt.Response:
    method = htt.request_method()
    path = htt.path_info().rstrip("/") or "/"
    ctx = {
        "conn": conn,
        "session": session,
        "form": form,
        "query": {k: v[-1] if v else "" for k, v in htt.query_params().items()},
    }

    public = _match_public(method, path, ctx)
    if public is not None:
        return public

    if not _auth_ok(session):
        return _need_login()

    authed = _match_authed(method, path, ctx)
    if authed is not None:
        return authed

    return htt.text("Not found", status=404)


def _match_public(method: str, path: str, ctx: dict) -> htt.Response | None:
    if method == "GET" and path == "/health":
        return htt.text("OK")
    if method == "GET" and path == "/login":
        return handle_login_get(ctx)
    if method == "POST" and path == "/login":
        return handle_login_post(ctx)
    if method == "POST" and path == "/logout":
        return handle_logout(ctx)
    return None


def handle_login_get(ctx: dict) -> htt.Response:
    if _auth_ok(ctx["session"]):
        return htt.redirect(htt.url_for("/"), status=302)
    inner = view.render("login.html", error=None, base=htt.app_base())
    return _html_page(inner, "Login")


def handle_login_post(ctx: dict) -> htt.Response:
    if _auth_ok(ctx["session"]):
        return htt.redirect(htt.url_for("/"), status=302)
    form = ctx["form"]
    user = str(form.get("username") or "").strip()
    password = str(form.get("password") or "")
    row = ctx["conn"].execute(
        "SELECT id, password_hash FROM admin_users WHERE username = ? LIMIT 1", (user,)
    ).fetchone()
    if row and verify_password(password, str(row["password_hash"])):
        ctx["session"].clear()
        ctx["session"]["admin_id"] = int(row["id"])
        return htt.redirect(htt.url_for("/"), status=303)
    inner = view.render("login.html", error="Invalid username or password.", base=htt.app_base())
    return _html_page(inner, "Login")


def handle_logout(ctx: dict) -> htt.Response:
    ctx["session"].clear()
    ctx["session"]["_destroyed"] = True
    return htt.redirect(htt.url_for("/login"), status=303)


def _m(path: str, pattern: str) -> re.Match[str] | None:
    return re.fullmatch(pattern, path)


def _match_authed(method: str, path: str, ctx: dict) -> htt.Response | None:
    if method == "POST" and path == "/":
        return handle_members_filter_post(ctx)
    if method == "GET" and path == "/":
        return handle_members_list(ctx)
    if method == "GET" and path == "/admin":
        return handle_admin_get(ctx)
    if method == "POST" and path == "/admin/membership-year":
        return handle_admin_membership_year(ctx)
    if method == "POST" and path == "/admin/license/create":
        return handle_license_create(ctx)
    m = _m(path, r"/admin/license/(\d+)/update")
    if method == "POST" and m:
        return handle_license_update(ctx, int(m.group(1)))
    m = _m(path, r"/admin/license/(\d+)/delete")
    if method == "POST" and m:
        return handle_license_delete(ctx, int(m.group(1)))
    if method == "POST" and path == "/admin/membership-type/create":
        return handle_mt_create(ctx)
    m = _m(path, r"/admin/membership-type/(\d+)/update")
    if method == "POST" and m:
        return handle_mt_update(ctx, int(m.group(1)))
    m = _m(path, r"/admin/membership-type/(\d+)/delete")
    if method == "POST" and m:
        return handle_mt_delete(ctx, int(m.group(1)))
    if method == "POST" and path == "/admins/create":
        return handle_admin_create(ctx)
    m = _m(path, r"/admins/(\d+)/password")
    if method == "POST" and m:
        return handle_admin_password(ctx, int(m.group(1)))
    m = _m(path, r"/admins/(\d+)/delete")
    if method == "POST" and m:
        return handle_admin_delete(ctx, int(m.group(1)))
    if method == "POST" and path == "/managers/create":
        return handle_manager_create(ctx)
    m = _m(path, r"/managers/(\d+)/password")
    if method == "POST" and m:
        return handle_manager_password(ctx, int(m.group(1)))
    m = _m(path, r"/managers/(\d+)/profile")
    if method == "POST" and m:
        return handle_manager_profile(ctx, int(m.group(1)))
    m = _m(path, r"/managers/(\d+)/delete")
    if method == "POST" and m:
        return handle_manager_delete(ctx, int(m.group(1)))

    if method == "GET" and path == "/members/export.csv":
        return handle_members_export(ctx, "csv")
    if method == "GET" and path == "/members/export.xlsx":
        return handle_members_export(ctx, "xlsx")
    if method == "GET" and path == "/members/export.pdf":
        return handle_members_export(ctx, "pdf")
    if method == "POST" and path == "/members/session-touch":
        list_params.members_merge_client_sort(ctx["session"], ctx["form"])
        return htt.empty(204)
    if method == "GET" and path == "/members/new":
        return handle_member_new_get(ctx)
    if method == "POST" and path == "/members/new":
        return handle_member_new_post(ctx)
    m = _m(path, r"/members/(\d+)/view")
    if method == "GET" and m:
        return handle_member_view(ctx, int(m.group(1)))
    m = _m(path, r"/members/(\d+)/edit")
    if method == "POST" and m:
        return handle_member_edit(ctx, int(m.group(1)))
    m = _m(path, r"/members/(\d+)/delete")
    if method == "POST" and m:
        return handle_member_delete(ctx, int(m.group(1)))
    m = _m(path, r"/members/(\d+)/payments/new")
    if method == "POST" and m:
        return handle_payment_new(ctx, int(m.group(1)))
    m = _m(path, r"/members/(\d+)/payments")
    if method == "GET" and m:
        return handle_member_payments(ctx, int(m.group(1)))
    m = _m(path, r"/payments/(\d+)/edit")
    if method == "POST" and m:
        return handle_payment_edit(ctx, int(m.group(1)))
    m = _m(path, r"/payments/(\d+)/delete")
    if method == "POST" and m:
        return handle_payment_delete(ctx, int(m.group(1)))

    if method == "GET" and path == "/reports":
        inner = view.render("reports.html", base=htt.app_base())
        return _html_page(inner, "Reports", authenticated=True, active_nav="reports")
    if method == "POST" and path == "/reports/payments":
        return handle_payments_report_post(ctx)
    if method == "GET" and path == "/reports/payments":
        return handle_payments_report_get(ctx)
    if method == "GET" and path == "/reports/payments/export.csv":
        return handle_payments_report_export(ctx, "csv")
    if method == "GET" and path == "/reports/payments/export.xlsx":
        return handle_payments_report_export(ctx, "xlsx")
    if method == "GET" and path == "/reports/payments/export.pdf":
        return handle_payments_report_export(ctx, "pdf")
    if method == "POST" and path == "/reports/keyholders":
        return handle_keyholders_post(ctx)
    if method == "GET" and path == "/reports/keyholders":
        return handle_keyholders_get(ctx)
    if method == "GET" and path == "/reports/keyholders/export.csv":
        return handle_keyholders_export(ctx, "csv")
    if method == "GET" and path == "/reports/keyholders/export.xlsx":
        return handle_keyholders_export(ctx, "xlsx")
    if method == "GET" and path == "/reports/keyholders/export.pdf":
        return handle_keyholders_export(ctx, "pdf")
    if method == "POST" and path == "/reports/roster-by-name":
        return handle_roster_post(ctx, "/reports/roster-by-name")
    if method == "GET" and path == "/reports/roster-by-name":
        return handle_roster_name_get(ctx)
    if method == "GET" and path == "/reports/roster-by-name/export.csv":
        return handle_roster_name_export(ctx, "csv")
    if method == "GET" and path == "/reports/roster-by-name/export.xlsx":
        return handle_roster_name_export(ctx, "xlsx")
    if method == "GET" and path == "/reports/roster-by-name/export.pdf":
        return handle_roster_name_export(ctx, "pdf")
    if method == "POST" and path == "/reports/roster-by-callsign":
        return handle_roster_post(ctx, "/reports/roster-by-callsign")
    if method == "GET" and path == "/reports/roster-by-callsign":
        return handle_roster_callsign_get(ctx)
    if method == "GET" and path == "/reports/roster-by-callsign/export.csv":
        return handle_roster_callsign_export(ctx, "csv")
    if method == "GET" and path == "/reports/roster-by-callsign/export.xlsx":
        return handle_roster_callsign_export(ctx, "xlsx")
    if method == "GET" and path == "/reports/roster-by-callsign/export.pdf":
        return handle_roster_callsign_export(ctx, "pdf")
    return None


def _admin_loc(error: str | None = None) -> htt.Response:
    loc = htt.url_for("/admin")
    if error:
        from urllib.parse import quote

        loc += "?error=" + quote(error)
    return htt.redirect(loc)


def _resolve_member_list_params(conn, flat: dict) -> dict:
    params = member_list.parse_list_query(flat)
    if params["membership_year"] is None:
        params["membership_year"] = AppSettingsRepository(conn).get_current_membership_year()
    return params


def handle_members_filter_post(ctx: dict) -> htt.Response:
    flat = list_params.members_merge_post(ctx["session"], ctx["form"])
    params = _resolve_member_list_params(ctx["conn"], flat)
    list_params.members_persist(ctx["session"], params)
    return htt.redirect(htt.url_for("/"))


def handle_members_list(ctx: dict) -> htt.Response:
    params = _resolve_member_list_params(ctx["conn"], list_params.members_read(ctx["session"]))
    list_params.members_persist(ctx["session"], params)
    year = int(params["membership_year"])
    filt = {
        "search": params["search"],
        "membership_type_id": params["membership_type_id"],
        "arrl": params["arrl"],
        "current_only": params["current_only"],
        "membership_year": year,
    }
    repo = MemberListRepository(ctx["conn"])
    total = repo.count_members(filt)
    rows = repo.list_rows_for_tabulator({**filt, "sort_by": params["sort_by"], "sort_dir": params["sort_dir"]})
    members_json = member_list.tabulator_json_from_rows(rows)
    default_year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    inner = view.render(
        "members.html",
        total=total,
        search=params["search"],
        sort_by=params["sort_by"],
        sort_dir=params["sort_dir"],
        membership_type_id=params["membership_type_id"],
        arrl=params["arrl"],
        current_only=params["current_only"],
        membership_year=year,
        membership_year_options=myear.option_years(default_year),
        membership_types=repo.list_membership_types(),
        export_query="",
        base=htt.app_base(),
    )
    scripts = view.render(
        "members_tabulator_scripts.html",
        members_json=members_json,
        sort_by=params["sort_by"],
        sort_dir=params["sort_dir"],
        base=htt.app_base(),
        members_sort_touch_url=htt.url_for("/members/session-touch"),
    )
    tab_css = '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/tabulator-tables@6.2/dist/css/tabulator.min.css">'
    return _html_page(
        inner,
        "Members",
        authenticated=True,
        active_nav="members",
        extra_head=tab_css,
        extra_scripts=scripts,
    )


def handle_admin_get(ctx: dict) -> htt.Response:
    error = str(ctx["query"].get("error") or "").strip() or None
    ref = ReferenceDataRepository(ctx["conn"])
    accounts = AdminAccountRepository(ctx["conn"])
    settings = AppSettingsRepository(ctx["conn"])
    current_year = settings.get_current_membership_year()
    inner = view.render(
        "admin.html",
        base=htt.app_base(),
        error=error,
        current_membership_year=current_year,
        membership_year_options=myear.option_years(current_year),
        license_classes=ref.list_license_classes(),
        membership_types=ref.list_membership_types(),
        admin_users=accounts.list_admin_users(),
        managers=accounts.list_managers(),
    )
    return _html_page(inner, "Admin", authenticated=True, active_nav="admin")


def handle_admin_membership_year(ctx: dict) -> htt.Response:
    year = myear.parse_year_input(ctx["form"].get("membership_year"))
    if year is None:
        return _admin_loc("Invalid membership year.")
    AppSettingsRepository(ctx["conn"]).set_current_membership_year(year)
    return _admin_loc()


def handle_license_create(ctx: dict) -> htt.Response:
    name = str(ctx["form"].get("name") or "").strip()
    if name == "":
        return _admin_loc("Name is required.")
    try:
        ReferenceDataRepository(ctx["conn"]).create_license_class(name)
    except sqlite3.IntegrityError as e:
        msg = _ref_write_error(e)
        return _admin_loc(msg or str(e))
    return _admin_loc()


def handle_license_update(ctx: dict, id_: int) -> htt.Response:
    name = str(ctx["form"].get("name") or "").strip()
    if id_ <= 0 or name == "":
        return _admin_loc("Invalid license class.")
    try:
        ReferenceDataRepository(ctx["conn"]).update_license_class(id_, name)
    except sqlite3.IntegrityError as e:
        return _admin_loc(_ref_write_error(e) or str(e))
    return _admin_loc()


def handle_license_delete(ctx: dict, id_: int) -> htt.Response:
    if id_ <= 0:
        return _admin_loc("Invalid license class.")
    try:
        ReferenceDataRepository(ctx["conn"]).delete_license_class(id_)
    except sqlite3.IntegrityError as e:
        return _admin_loc(_ref_write_error(e) or str(e))
    return _admin_loc()


def handle_mt_create(ctx: dict) -> htt.Response:
    name = str(ctx["form"].get("name") or "").strip()
    if name == "":
        return _admin_loc("Name is required.")
    try:
        ReferenceDataRepository(ctx["conn"]).create_membership_type(name)
    except sqlite3.IntegrityError as e:
        return _admin_loc(_ref_write_error(e) or str(e))
    return _admin_loc()


def handle_mt_update(ctx: dict, id_: int) -> htt.Response:
    name = str(ctx["form"].get("name") or "").strip()
    if id_ <= 0 or name == "":
        return _admin_loc("Invalid membership type.")
    try:
        ReferenceDataRepository(ctx["conn"]).update_membership_type(id_, name)
    except sqlite3.IntegrityError as e:
        return _admin_loc(_ref_write_error(e) or str(e))
    return _admin_loc()


def handle_mt_delete(ctx: dict, id_: int) -> htt.Response:
    if id_ <= 0:
        return _admin_loc("Invalid membership type.")
    try:
        year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
        ReferenceDataRepository(ctx["conn"]).delete_membership_type_or_fail(id_, year)
    except RuntimeError as e:
        return _admin_loc(str(e))
    except sqlite3.IntegrityError as e:
        return _admin_loc(_ref_write_error(e) or str(e))
    return _admin_loc()


def handle_admin_create(ctx: dict) -> htt.Response:
    username = str(ctx["form"].get("username") or "").strip()
    password = str(ctx["form"].get("password") or "")
    if username == "" or password.strip() == "":
        return _admin_loc("Username and password are required.")
    try:
        AdminAccountRepository(ctx["conn"]).create_admin_user(username, password)
    except sqlite3.IntegrityError as e:
        if "admin_users" in str(e):
            return _admin_loc("That administrator username already exists.")
        return _admin_loc(_ref_write_error(e) or str(e))
    return _admin_loc()


def handle_admin_password(ctx: dict, id_: int) -> htt.Response:
    password = str(ctx["form"].get("password") or "")
    if id_ <= 0 or password.strip() == "":
        return _admin_loc("Invalid administrator or password.")
    AdminAccountRepository(ctx["conn"]).update_admin_password(id_, password)
    return _admin_loc()


def handle_admin_delete(ctx: dict, id_: int) -> htt.Response:
    if id_ <= 0:
        return _admin_loc("Invalid administrator.")
    try:
        AdminAccountRepository(ctx["conn"]).delete_admin_user_or_fail(id_)
    except RuntimeError as e:
        return _admin_loc(str(e))
    return _admin_loc()


def handle_manager_create(ctx: dict) -> htt.Response:
    username = str(ctx["form"].get("username") or "").strip()
    password = str(ctx["form"].get("password") or "")
    display_raw = str(ctx["form"].get("display_name") or "").strip()
    display_name = display_raw or None
    if username == "" or password.strip() == "":
        return _admin_loc("Username and password are required.")
    try:
        AdminAccountRepository(ctx["conn"]).create_manager(username, password, display_name)
    except sqlite3.IntegrityError as e:
        if "managers" in str(e):
            return _admin_loc("That manager username already exists.")
        return _admin_loc(_ref_write_error(e) or str(e))
    return _admin_loc()


def handle_manager_password(ctx: dict, id_: int) -> htt.Response:
    password = str(ctx["form"].get("password") or "")
    if id_ <= 0 or password.strip() == "":
        return _admin_loc("Invalid manager or password.")
    AdminAccountRepository(ctx["conn"]).update_manager_password(id_, password)
    return _admin_loc()


def handle_manager_profile(ctx: dict, id_: int) -> htt.Response:
    display_raw = str(ctx["form"].get("display_name") or "").strip()
    if id_ <= 0:
        return _admin_loc("Invalid manager.")
    AdminAccountRepository(ctx["conn"]).update_manager_profile(id_, display_raw or None)
    return _admin_loc()


def handle_manager_delete(ctx: dict, id_: int) -> htt.Response:
    if id_ <= 0:
        return _admin_loc("Invalid manager.")
    try:
        AdminAccountRepository(ctx["conn"]).delete_manager(id_)
    except sqlite3.IntegrityError as e:
        return _admin_loc(_ref_write_error(e) or str(e))
    return _admin_loc()


def handle_members_export(ctx: dict, fmt: str) -> htt.Response:
    params = _resolve_member_list_params(ctx["conn"], list_params.members_read(ctx["session"]))
    rows = MemberListRepository(ctx["conn"]).list_rows_for_export(params)
    stem = exports.timestamp_stem("members")
    if fmt == "csv":
        return htt.download(exports.members_csv(rows), "text/csv; charset=utf-8", f"{stem}.csv")
    if fmt == "xlsx":
        return htt.download(
            exports.members_xlsx(rows),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"{stem}.xlsx",
        )
    if fmt == "pdf":
        return htt.download(exports.members_pdf(rows), "application/pdf", f"{stem}.pdf")
    return htt.text("Not found", status=404)


def _member_ref(ctx: dict) -> dict:
    repo = MemberRepository(ctx["conn"])
    return {"license_classes": repo.list_license_classes(), "membership_types": repo.list_membership_types()}


def handle_member_new_get(ctx: dict) -> htt.Response:
    default_year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    inner = view.render(
        "member_new.html",
        error=None,
        base=htt.app_base(),
        default_membership_year=default_year,
        membership_year_options=myear.option_years(default_year),
        **_member_ref(ctx),
    )
    return _html_page(inner, "New member", authenticated=True, active_nav="members")


def handle_member_new_post(ctx: dict) -> htt.Response:
    body = ctx["form"]
    paid_year = myear.parse_year_input(body.get("paid_for_year"))
    paid_through = myear.paid_through_iso(paid_year) if paid_year is not None else None
    default_year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    ref = {
        **_member_ref(ctx),
        "base": htt.app_base(),
        "default_membership_year": default_year,
        "membership_year_options": myear.option_years(default_year),
    }
    members_repo = MemberRepository(ctx["conn"])
    payments_repo = PaymentRepository(ctx["conn"])
    row = normalizer.member_create_from_form(body, paid_through)

    def fail(msg: str, status: int) -> htt.Response:
        inner = view.render("member_new.html", error=msg, **ref)
        return _html_page(inner, "New member", authenticated=True, active_nav="members", status=status)

    if row["last_name"].strip() == "" or row["first_name"].strip() == "":
        return fail("Could not create member.", 400)
    cs = row["call_sign"]
    if cs is not None and members_repo.find_id_by_nonnull_call_sign(cs) is not None:
        return fail("That call sign is already in use.", 409)
    if cs is None and members_repo.exists_name_without_call_sign(row["last_name"], row["first_name"], None):
        return fail("A member with this name already exists without a call sign.", 409)
    try:
        new_id = members_repo.insert_member(row)
        if paid_year is not None:
            payments_repo.insert_payment(
                new_id,
                {
                    "payment_date": date.today().isoformat(),
                    "membership_year": paid_year,
                    "membership_type_id": row["membership_type_id"],
                    "notes": None,
                    "form_number": None,
                },
            )
    except DuplicateMemberKeyNumber:
        return fail("That key number is already assigned to another member.", 409)
    except sqlite3.Error:
        return fail("Could not create member.", 400)
    return htt.redirect(htt.url_for(f"/members/{new_id}/view"))


def handle_member_view(ctx: dict, id_: int) -> htt.Response:
    members_repo = MemberRepository(ctx["conn"])
    member = members_repo.find_member_by_id(id_) if id_ > 0 else None
    extras = {"authenticated": True, "active_nav": "members"}
    if member is None:
        return _html_page(
            '<div class="standard-page-scroll"><p class="error">Member not found.</p></div>',
            "Not found",
            status=404,
            **extras,
        )
    inner = view.render("member_detail.html", member=member, error=None, base=htt.app_base(), **_member_ref(ctx))
    scripts = view.render("member_detail_scripts.html")
    return _html_page(inner, "Member", extra_scripts=scripts, **extras)


def handle_member_edit(ctx: dict, id_: int) -> htt.Response:
    members_repo = MemberRepository(ctx["conn"])
    member = members_repo.find_member_by_id(id_) if id_ > 0 else None
    extras = {"authenticated": True, "active_nav": "members"}
    if member is None:
        return _html_page(
            '<div class="standard-page-scroll"><p class="error">Member not found.</p></div>',
            "Not found",
            status=404,
            **extras,
        )
    row = normalizer.member_update_from_form(ctx["form"])
    scripts = view.render("member_detail_scripts.html")

    def fail(msg: str, status: int) -> htt.Response:
        inner = view.render("member_detail.html", member=member, error=msg, base=htt.app_base(), **_member_ref(ctx))
        return _html_page(inner, "Member", extra_scripts=scripts, status=status, **extras)

    if row["last_name"].strip() == "" or row["first_name"].strip() == "":
        return fail("Could not save member.", 400)
    eff = row["call_sign"]
    oid = members_repo.find_id_by_nonnull_call_sign(eff) if eff else None
    if eff is not None and oid is not None and oid != id_:
        return fail("That call sign is already in use.", 409)
    if eff is None and members_repo.exists_name_without_call_sign(row["last_name"], row["first_name"], id_):
        return fail("Another member with this name already exists without a call sign.", 409)
    try:
        members_repo.update_member(id_, row)
    except DuplicateMemberKeyNumber:
        return fail("That key number is already assigned to another member.", 409)
    except sqlite3.Error:
        return fail("Could not save member.", 400)
    return htt.redirect(htt.url_for(f"/members/{id_}/view"))


def handle_member_delete(ctx: dict, id_: int) -> htt.Response:
    if id_ > 0:
        MemberRepository(ctx["conn"]).delete_member_by_id(id_)
    return htt.redirect(htt.url_for("/"))


def handle_payment_new(ctx: dict, member_id: int) -> htt.Response:
    members_repo = MemberRepository(ctx["conn"])
    payments_repo = PaymentRepository(ctx["conn"])
    if member_id <= 0 or members_repo.find_member_by_id(member_id) is None:
        return htt.redirect(htt.url_for("/"))
    parsed = normalizer.payment_from_form(ctx["form"])
    if not parsed["ok"]:
        ctx["session"]["dvra_flash_payment_error"] = parsed["error"]
        return htt.redirect(htt.url_for(f"/members/{member_id}/payments"))
    data = parsed["data"]
    requested = int(data["membership_year"])
    confirm = str(ctx["form"].get("confirm_year_rollover") or "") == "1"
    if payments_repo.member_has_payment_for_year(member_id, requested):
        proposed = payments_repo.next_free_membership_year(member_id, requested)
        if not confirm:
            ctx["session"]["dvra_flash_payment_rollover"] = {
                "mode": "create",
                "requested_year": requested,
                "proposed_year": proposed,
                "payment_date": data["payment_date"],
                "membership_type": "" if data["membership_type_id"] is None else str(data["membership_type_id"]),
                "form_number": data["form_number"] or "",
                "notes": data["notes"] or "",
            }
            return htt.redirect(htt.url_for(f"/members/{member_id}/payments"))
        data["membership_year"] = proposed
    try:
        payments_repo.insert_payment(member_id, data)
    except Exception:
        ctx["session"]["dvra_flash_payment_error"] = "Could not save payment."
        return htt.redirect(htt.url_for(f"/members/{member_id}/payments"))
    return htt.redirect(htt.url_for(f"/members/{member_id}/payments"))


def handle_payment_edit(ctx: dict, payment_id: int) -> htt.Response:
    payments_repo = PaymentRepository(ctx["conn"])
    parsed = normalizer.payment_from_form(ctx["form"])
    meta = payments_repo.find_payment_meta(payment_id) if payment_id > 0 else None
    if meta is None:
        return htt.redirect(htt.url_for("/"))
    member_id = meta["member_id"]
    if not parsed["ok"]:
        ctx["session"]["dvra_flash_payment_error"] = parsed["error"]
        return htt.redirect(htt.url_for(f"/members/{member_id}/payments"))
    data = parsed["data"]
    requested = int(data["membership_year"])
    confirm = str(ctx["form"].get("confirm_year_rollover") or "") == "1"
    if payments_repo.member_has_payment_for_year(member_id, requested, payment_id):
        proposed = payments_repo.next_free_membership_year(member_id, requested, payment_id)
        if not confirm:
            ctx["session"]["dvra_flash_payment_rollover"] = {
                "mode": "edit",
                "payment_id": payment_id,
                "requested_year": requested,
                "proposed_year": proposed,
                "payment_date": data["payment_date"],
                "membership_type": "" if data["membership_type_id"] is None else str(data["membership_type_id"]),
                "form_number": data["form_number"] or "",
                "notes": data["notes"] or "",
            }
            return htt.redirect(htt.url_for(f"/members/{member_id}/payments"))
        data["membership_year"] = proposed
    try:
        mid = payments_repo.update_payment(payment_id, data)
        if mid is None:
            return htt.redirect(htt.url_for("/"))
    except Exception:
        ctx["session"]["dvra_flash_payment_error"] = "Could not save payment."
        return htt.redirect(htt.url_for(f"/members/{member_id}/payments"))
    return htt.redirect(htt.url_for(f"/members/{member_id}/payments"))


def handle_payment_delete(ctx: dict, payment_id: int) -> htt.Response:
    payments_repo = PaymentRepository(ctx["conn"])
    meta = payments_repo.find_payment_meta(payment_id) if payment_id > 0 else None
    if meta is None:
        return htt.redirect(htt.url_for("/"))
    member_id = meta["member_id"]
    try:
        payments_repo.delete_payment(payment_id)
    except Exception:
        ctx["session"]["dvra_flash_payment_error"] = "Could not delete payment."
    return htt.redirect(htt.url_for(f"/members/{member_id}/payments"))


def handle_member_payments(ctx: dict, id_: int) -> htt.Response:
    members_repo = MemberRepository(ctx["conn"])
    member = members_repo.find_member_by_id(id_) if id_ > 0 else None
    extras = {"authenticated": True, "active_nav": "members"}
    if member is None:
        return _html_page(
            '<div class="standard-page-scroll"><p class="error">Member not found.</p></div>',
            "Not found",
            status=404,
            **extras,
        )
    flash = ctx["session"].pop("dvra_flash_payment_error", None)
    rollover = ctx["session"].pop("dvra_flash_payment_rollover", None)
    payments = members_repo.list_payments_for_member(id_)
    for p in payments:
        p.pop("membership_type_display", None)
    default_year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    inner = view.render(
        "member_payments.html",
        member=member,
        payments=payments,
        membership_types=members_repo.list_membership_types(),
        flash_error=flash,
        rollover=rollover,
        default_membership_year=default_year,
        membership_year_options=myear.option_years(default_year),
        base=htt.app_base(),
    )
    scripts = view.render("member_payments_scripts.html")
    return _html_page(inner, "Payments", extra_scripts=scripts, **extras)


def handle_payments_report_post(ctx: dict) -> htt.Response:
    flat = list_params.payments_merge_post(ctx["session"], ctx["form"])
    params = payments_report.parse_payment_report_query(flat)
    list_params.payments_persist(ctx["session"], params)
    return htt.redirect(htt.url_for("/reports/payments"))


def handle_payments_report_get(ctx: dict) -> htt.Response:
    default_year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    persisted = list_params.payments_read(ctx["session"])
    if not persisted or "membership_year" not in persisted:
        persisted = dict(persisted)
        persisted["membership_year"] = default_year
    params = payments_report.parse_payment_report_query(persisted)
    list_params.payments_persist(ctx["session"], params)
    repo = PaymentsReportRepository(ctx["conn"])
    total = repo.count_rows(params)
    rows = repo.list_payment_report_rows(params)
    post_action = htt.url_for("/reports/payments")
    sort_post = {}
    for field in (
        "member_name",
        "call_sign",
        "payment_date",
        "paid_through",
        "membership_year",
        "membership_type",
        "form_number",
    ):
        nsb, nsd = payments_report.next_sort_choice(params["sort_by"], params["sort_dir"], field)
        sort_post[field] = {"sort_by": nsb, "sort_dir": nsd}
    year_display = "" if params["membership_year"] == "any" else str(params.get("membership_year_filter") or params.get("membership_year") or "")
    inner = view.render(
        "reports_payment_report.html",
        total=total,
        rows=rows,
        start_date=params["start_date"],
        end_date=params["end_date"],
        paid_through_start=params["paid_through_start"],
        paid_through_end=params["paid_through_end"],
        membership_year=year_display,
        membership_year_options=myear.option_years(default_year),
        sort_by=params["sort_by"],
        sort_dir=params["sort_dir"],
        payments_report_sort_post=sort_post,
        payments_report_post_action=post_action,
        export_query="",
        base=htt.app_base(),
    )
    return _html_page(inner, "Payment report", authenticated=True, active_nav="reports")


def handle_payments_report_export(ctx: dict, fmt: str) -> htt.Response:
    params = payments_report.parse_payment_report_query(list_params.payments_read(ctx["session"]))
    rows = PaymentsReportRepository(ctx["conn"]).list_payment_report_rows(params)
    stem = exports.timestamp_stem("payments-report", compact=True)
    if fmt == "csv":
        return htt.download(exports.payments_csv(rows), "text/csv; charset=utf-8", f"{stem}.csv")
    if fmt == "xlsx":
        return htt.download(
            exports.payments_xlsx(rows),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"{stem}.xlsx",
        )
    if fmt == "pdf":
        return htt.download(exports.payments_pdf(rows), "application/pdf", f"{stem}.pdf")
    return htt.text("Not found", status=404)


def handle_keyholders_post(ctx: dict) -> htt.Response:
    flat = list_params.keyholders_merge_post(ctx["session"], ctx["form"])
    params = reports_mod.parse_keyholders_query(flat)
    list_params.keyholders_persist(ctx["session"], params)
    return htt.redirect(htt.url_for("/reports/keyholders"))


def handle_keyholders_get(ctx: dict) -> htt.Response:
    kh = reports_mod.parse_keyholders_query(list_params.keyholders_read(ctx["session"]))
    list_params.keyholders_persist(ctx["session"], kh)
    rows = ReportsRepository(ctx["conn"]).list_keyholders(kh["sort_by"], kh["sort_dir"])
    post_action = htt.url_for("/reports/keyholders")
    sort_post = {}
    for field in ("name", "call_sign", "key_number", "email"):
        nsb, nsd = reports_mod.next_keyholders_sort_choice(kh["sort_by"], kh["sort_dir"], field)
        sort_post[field] = {"sort_by": nsb, "sort_dir": nsd}
    inner = view.render(
        "reports_keyholders.html",
        total=len(rows),
        rows=rows,
        sort_by=kh["sort_by"],
        sort_dir=kh["sort_dir"],
        keyholders_sort_post=sort_post,
        keyholders_post_action=post_action,
        export_query="",
        base=htt.app_base(),
    )
    return _html_page(inner, "Keyholders", authenticated=True, active_nav="reports")


def handle_keyholders_export(ctx: dict, fmt: str) -> htt.Response:
    kh = reports_mod.parse_keyholders_query(list_params.keyholders_read(ctx["session"]))
    rows = ReportsRepository(ctx["conn"]).list_keyholders(kh["sort_by"], kh["sort_dir"])
    stem = exports.timestamp_stem("keyholders-report", compact=True)
    if fmt == "csv":
        return htt.download(exports.keyholders_csv(rows), "text/csv; charset=utf-8", f"{stem}.csv")
    if fmt == "xlsx":
        return htt.download(
            exports.keyholders_xlsx(rows),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"{stem}.xlsx",
        )
    if fmt == "pdf":
        return htt.download(exports.keyholders_pdf(rows), "application/pdf", f"{stem}.pdf")
    return htt.text("Not found", status=404)


def handle_roster_post(ctx: dict, dest: str) -> htt.Response:
    default_year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    list_params.roster_merge_post_year(ctx["session"], ctx["form"], default_year)
    return htt.redirect(htt.url_for(dest))


def handle_roster_name_get(ctx: dict) -> htt.Response:
    default_year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    year = list_params.roster_read_year(ctx["session"], default_year)
    list_params.roster_persist_year(ctx["session"], year)
    rows = ReportsRepository(ctx["conn"]).roster_by_name(year)
    inner = view.render(
        "reports_roster_name.html",
        total=len(rows),
        rows=rows,
        membership_year=year,
        membership_year_options=myear.option_years(default_year),
        roster_post_action=htt.url_for("/reports/roster-by-name"),
        base=htt.app_base(),
    )
    return _html_page(inner, "Roster by name", authenticated=True, active_nav="reports")


def handle_roster_callsign_get(ctx: dict) -> htt.Response:
    default_year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    year = list_params.roster_read_year(ctx["session"], default_year)
    list_params.roster_persist_year(ctx["session"], year)
    rows = ReportsRepository(ctx["conn"]).roster_by_callsign(year)
    inner = view.render(
        "reports_roster_callsign.html",
        total=len(rows),
        rows=rows,
        membership_year=year,
        membership_year_options=myear.option_years(default_year),
        roster_post_action=htt.url_for("/reports/roster-by-callsign"),
        base=htt.app_base(),
    )
    return _html_page(inner, "Roster by callsign", authenticated=True, active_nav="reports")


def handle_roster_name_export(ctx: dict, fmt: str) -> htt.Response:
    year = list_params.roster_read_year(
        ctx["session"], AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    )
    rows = ReportsRepository(ctx["conn"]).roster_by_name(year)
    stem = exports.timestamp_stem("roster-by-name", compact=True)
    if fmt == "csv":
        return htt.download(exports.roster_by_name_csv(rows), "text/csv; charset=utf-8", f"{stem}.csv")
    if fmt == "xlsx":
        return htt.download(
            exports.roster_by_name_xlsx(rows),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"{stem}.xlsx",
        )
    return htt.download(exports.roster_by_name_pdf(rows), "application/pdf", f"{stem}.pdf")


def handle_roster_callsign_export(ctx: dict, fmt: str) -> htt.Response:
    year = list_params.roster_read_year(
        ctx["session"], AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    )
    rows = ReportsRepository(ctx["conn"]).roster_by_callsign(year)
    stem = exports.timestamp_stem("roster-by-callsign", compact=True)
    if fmt == "csv":
        return htt.download(exports.roster_by_callsign_csv(rows), "text/csv; charset=utf-8", f"{stem}.csv")
    if fmt == "xlsx":
        return htt.download(
            exports.roster_by_callsign_xlsx(rows),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"{stem}.xlsx",
        )
    return htt.download(exports.roster_by_callsign_pdf(rows), "application/pdf", f"{stem}.pdf")
