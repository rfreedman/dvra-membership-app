"""PATH_INFO routing under index.py."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from dvra import auth
from dvra import http as htt
from dvra import list_params
from dvra.context import RequestCtx
from dvra.pages import login as login_pages


def dispatch(conn: sqlite3.Connection, session: dict[str, Any], form: dict[str, Any]) -> htt.Response:
    method = htt.request_method()
    path = htt.request_path()
    ctx: RequestCtx = {
        "conn": conn,
        "session": session,
        "form": form,
        "query": {k: v[-1] if v else "" for k, v in htt.query_params().items()},
    }

    public = _match_public(method, path, ctx)
    if public is not None:
        return public

    needed = login_pages.require_login(ctx)
    if needed is not None:
        return needed

    if auth.is_admin_path(path):
        denied = login_pages.require_admin(ctx)
        if denied is not None:
            return denied

    if auth.is_read_only(session):
        if method == "GET" and path == "/members/new":
            return htt.redirect(htt.url_for("/"), status=303)
        if not auth.is_read_only_allowed(method, path):
            return htt.text("Read-only accounts cannot change records.", status=403)

    authed = _match_authed(method, path, ctx)
    if authed is not None:
        return authed

    return htt.text("Not found", status=404)


def _match_public(method: str, path: str, ctx: RequestCtx) -> htt.Response | None:
    if method == "GET" and path == "/health":
        return htt.text("OK")
    # Prefer app.py fast path (no session) for /api/roster*; keep here as fallback.
    if path in ("/api/roster", "/api/roster/embed"):
        from dvra.pages.public_roster import try_handle_public_roster

        roster = try_handle_public_roster(method, path)
        if roster is not None:
            return roster
    if method == "GET" and path == "/login":
        return login_pages.handle_login_get(ctx)
    if method == "POST" and path == "/login":
        return login_pages.handle_login_post(ctx)
    if method == "POST" and path == "/logout":
        return login_pages.handle_logout(ctx)
    return None


def _m(path: str, pattern: str) -> re.Match[str] | None:
    return re.fullmatch(pattern, path)


def _match_authed(method: str, path: str, ctx: RequestCtx) -> htt.Response | None:
    # Import page modules only when authenticated routing needs them (CGI cold start).
    from dvra.pages import admin as admin_pages
    from dvra.pages import members as member_pages
    from dvra.pages import reports as report_pages

    if method == "POST" and path == "/":
        return member_pages.handle_members_filter_post(ctx)
    if method == "GET" and path == "/":
        return member_pages.handle_members_list(ctx)
    if method == "GET" and path == "/admin":
        return admin_pages.handle_admin_get(ctx)
    if method == "POST" and path == "/admin/membership-year":
        return admin_pages.handle_admin_membership_year(ctx)
    if method == "POST" and path == "/admin/join-extension":
        return admin_pages.handle_admin_join_extension(ctx)
    if method == "POST" and path == "/admin/license/create":
        return admin_pages.handle_license_create(ctx)
    m = _m(path, r"/admin/license/(\d+)/update")
    if method == "POST" and m:
        return admin_pages.handle_license_update(ctx, int(m.group(1)))
    m = _m(path, r"/admin/license/(\d+)/delete")
    if method == "POST" and m:
        return admin_pages.handle_license_delete(ctx, int(m.group(1)))
    m = _m(path, r"/admin/license/(\d+)/hide")
    if method == "POST" and m:
        return admin_pages.handle_license_hide(ctx, int(m.group(1)))
    m = _m(path, r"/admin/license/(\d+)/unhide")
    if method == "POST" and m:
        return admin_pages.handle_license_unhide(ctx, int(m.group(1)))
    if method == "POST" and path == "/admin/membership-type/create":
        return admin_pages.handle_mt_create(ctx)
    m = _m(path, r"/admin/membership-type/(\d+)/update")
    if method == "POST" and m:
        return admin_pages.handle_mt_update(ctx, int(m.group(1)))
    m = _m(path, r"/admin/membership-type/(\d+)/delete")
    if method == "POST" and m:
        return admin_pages.handle_mt_delete(ctx, int(m.group(1)))
    m = _m(path, r"/admin/membership-type/(\d+)/hide")
    if method == "POST" and m:
        return admin_pages.handle_mt_hide(ctx, int(m.group(1)))
    m = _m(path, r"/admin/membership-type/(\d+)/unhide")
    if method == "POST" and m:
        return admin_pages.handle_mt_unhide(ctx, int(m.group(1)))
    if method == "POST" and path == "/admins/create":
        return admin_pages.handle_admin_create(ctx)
    m = _m(path, r"/admins/(\d+)/password")
    if method == "POST" and m:
        return admin_pages.handle_admin_password(ctx, int(m.group(1)))
    m = _m(path, r"/admins/(\d+)/delete")
    if method == "POST" and m:
        return admin_pages.handle_admin_delete(ctx, int(m.group(1)))
    if method == "POST" and path == "/managers/create":
        return admin_pages.handle_manager_create(ctx)
    m = _m(path, r"/managers/(\d+)/password")
    if method == "POST" and m:
        return admin_pages.handle_manager_password(ctx, int(m.group(1)))
    m = _m(path, r"/managers/(\d+)/profile")
    if method == "POST" and m:
        return admin_pages.handle_manager_profile(ctx, int(m.group(1)))
    m = _m(path, r"/managers/(\d+)/delete")
    if method == "POST" and m:
        return admin_pages.handle_manager_delete(ctx, int(m.group(1)))
    if method == "POST" and path == "/readonly-users/create":
        return admin_pages.handle_readonly_create(ctx)
    m = _m(path, r"/readonly-users/(\d+)/password")
    if method == "POST" and m:
        return admin_pages.handle_readonly_password(ctx, int(m.group(1)))
    m = _m(path, r"/readonly-users/(\d+)/profile")
    if method == "POST" and m:
        return admin_pages.handle_readonly_profile(ctx, int(m.group(1)))
    m = _m(path, r"/readonly-users/(\d+)/delete")
    if method == "POST" and m:
        return admin_pages.handle_readonly_delete(ctx, int(m.group(1)))

    if method == "GET" and path == "/members/export.csv":
        return member_pages.handle_members_export(ctx, "csv")
    if method == "GET" and path == "/members/export.xlsx":
        return member_pages.handle_members_export(ctx, "xlsx")
    if method == "GET" and path == "/members/export.pdf":
        return member_pages.handle_members_export(ctx, "pdf")
    if method == "POST" and path == "/members/session-touch":
        list_params.members_merge_client_sort(ctx["session"], ctx["form"])
        return htt.empty(204)
    if method == "GET" and path == "/members/new":
        return member_pages.handle_member_new_get(ctx)
    if method == "POST" and path == "/members/new":
        return member_pages.handle_member_new_post(ctx)
    m = _m(path, r"/members/(\d+)/view")
    if method == "GET" and m:
        return member_pages.handle_member_view(ctx, int(m.group(1)))
    m = _m(path, r"/members/(\d+)/edit")
    if method == "POST" and m:
        return member_pages.handle_member_edit(ctx, int(m.group(1)))
    m = _m(path, r"/members/(\d+)/delete")
    if method == "POST" and m:
        return member_pages.handle_member_delete(ctx, int(m.group(1)))
    m = _m(path, r"/members/(\d+)/note")
    if method == "GET" and m:
        return member_pages.handle_member_note_get(ctx, int(m.group(1)))
    m = _m(path, r"/members/(\d+)/note")
    if method == "POST" and m:
        return member_pages.handle_member_note_post(ctx, int(m.group(1)))
    m = _m(path, r"/members/(\d+)/payments/new")
    if method == "POST" and m:
        return member_pages.handle_payment_new(ctx, int(m.group(1)))
    m = _m(path, r"/members/(\d+)/payments")
    if method == "GET" and m:
        return member_pages.handle_member_payments(ctx, int(m.group(1)))
    m = _m(path, r"/payments/(\d+)/edit")
    if method == "POST" and m:
        return member_pages.handle_payment_edit(ctx, int(m.group(1)))
    m = _m(path, r"/payments/(\d+)/delete")
    if method == "POST" and m:
        return member_pages.handle_payment_delete(ctx, int(m.group(1)))

    if method == "GET" and path == "/reports":
        return report_pages.handle_reports_index(ctx)
    if method == "POST" and path == "/reports/payments":
        return report_pages.handle_payments_report_post(ctx)
    if method == "GET" and path == "/reports/payments":
        return report_pages.handle_payments_report_get(ctx)
    if method == "GET" and path == "/reports/payments/export.csv":
        return report_pages.handle_payments_report_export(ctx, "csv")
    if method == "GET" and path == "/reports/payments/export.xlsx":
        return report_pages.handle_payments_report_export(ctx, "xlsx")
    if method == "GET" and path == "/reports/payments/export.pdf":
        return report_pages.handle_payments_report_export(ctx, "pdf")
    if method == "POST" and path == "/reports/keyholders":
        return report_pages.handle_keyholders_post(ctx)
    if method == "GET" and path == "/reports/keyholders":
        return report_pages.handle_keyholders_get(ctx)
    if method == "GET" and path == "/reports/keyholders/export.csv":
        return report_pages.handle_keyholders_export(ctx, "csv")
    if method == "GET" and path == "/reports/keyholders/export.xlsx":
        return report_pages.handle_keyholders_export(ctx, "xlsx")
    if method == "GET" and path == "/reports/keyholders/export.pdf":
        return report_pages.handle_keyholders_export(ctx, "pdf")
    if method == "POST" and path == "/reports/roster-by-name":
        return report_pages.handle_roster_post(ctx, "/reports/roster-by-name")
    if method == "GET" and path == "/reports/roster-by-name":
        return report_pages.handle_roster_name_get(ctx)
    if method == "GET" and path == "/reports/roster-by-name/export.csv":
        return report_pages.handle_roster_name_export(ctx, "csv")
    if method == "GET" and path == "/reports/roster-by-name/export.xlsx":
        return report_pages.handle_roster_name_export(ctx, "xlsx")
    if method == "GET" and path == "/reports/roster-by-name/export.pdf":
        return report_pages.handle_roster_name_export(ctx, "pdf")
    if method == "POST" and path == "/reports/roster-by-callsign":
        return report_pages.handle_roster_post(ctx, "/reports/roster-by-callsign")
    if method == "GET" and path == "/reports/roster-by-callsign":
        return report_pages.handle_roster_callsign_get(ctx)
    if method == "GET" and path == "/reports/roster-by-callsign/export.csv":
        return report_pages.handle_roster_callsign_export(ctx, "csv")
    if method == "GET" and path == "/reports/roster-by-callsign/export.xlsx":
        return report_pages.handle_roster_callsign_export(ctx, "xlsx")
    if method == "GET" and path == "/reports/roster-by-callsign/export.pdf":
        return report_pages.handle_roster_callsign_export(ctx, "pdf")
    if method == "POST" and path == "/reports/new-members":
        return report_pages.handle_new_members_post(ctx)
    if method == "GET" and path == "/reports/new-members":
        return report_pages.handle_new_members_get(ctx)
    if method == "GET" and path == "/reports/new-members/export.csv":
        return report_pages.handle_new_members_export(ctx, "csv")
    if method == "GET" and path == "/reports/new-members/export.xlsx":
        return report_pages.handle_new_members_export(ctx, "xlsx")
    if method == "GET" and path == "/reports/new-members/export.pdf":
        return report_pages.handle_new_members_export(ctx, "pdf")
    if method == "POST" and path == "/reports/paid-memberships":
        return report_pages.handle_paid_memberships_post(ctx)
    if method == "GET" and path == "/reports/paid-memberships":
        return report_pages.handle_paid_memberships_get(ctx)
    if method == "GET" and path == "/reports/paid-memberships/export.csv":
        return report_pages.handle_paid_memberships_export(ctx, "csv")
    if method == "GET" and path == "/reports/paid-memberships/export.xlsx":
        return report_pages.handle_paid_memberships_export(ctx, "xlsx")
    if method == "GET" and path == "/reports/paid-memberships/export.pdf":
        return report_pages.handle_paid_memberships_export(ctx, "pdf")
    if method == "POST" and path == "/reports/unpaid-memberships":
        return report_pages.handle_unpaid_memberships_post(ctx)
    if method == "GET" and path == "/reports/unpaid-memberships":
        return report_pages.handle_unpaid_memberships_get(ctx)
    if method == "GET" and path == "/reports/unpaid-memberships/export.csv":
        return report_pages.handle_unpaid_memberships_export(ctx, "csv")
    if method == "GET" and path == "/reports/unpaid-memberships/export.xlsx":
        return report_pages.handle_unpaid_memberships_export(ctx, "xlsx")
    if method == "GET" and path == "/reports/unpaid-memberships/export.pdf":
        return report_pages.handle_unpaid_memberships_export(ctx, "pdf")
    return None
