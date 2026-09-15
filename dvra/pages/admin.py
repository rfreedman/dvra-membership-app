"""Admin reference data and account CRUD."""

from __future__ import annotations

import sqlite3

from dvra import http as htt
from dvra import membership_year as myear
from dvra import view
from dvra.admin_accounts import AdminAccountRepository
from dvra.app_settings import AppSettingsRepository
from dvra.context import RequestCtx
from dvra.pages.common import admin_redirect, html_page, ref_write_error
from dvra.reference_data import ReferenceDataRepository


def handle_admin_get(ctx: RequestCtx) -> htt.Response:
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
    return html_page(inner, "Admin", ctx, active_nav="admin")


def handle_admin_membership_year(ctx: RequestCtx) -> htt.Response:
    year = myear.parse_year_input(ctx["form"].get("membership_year"))
    if year is None:
        return admin_redirect("Invalid membership year.")
    AppSettingsRepository(ctx["conn"]).set_current_membership_year(year)
    return admin_redirect()


def handle_license_create(ctx: RequestCtx) -> htt.Response:
    name = str(ctx["form"].get("name") or "").strip()
    if name == "":
        return admin_redirect("Name is required.")
    try:
        ReferenceDataRepository(ctx["conn"]).create_license_class(name)
    except sqlite3.IntegrityError as e:
        return admin_redirect(ref_write_error(e) or str(e))
    return admin_redirect()


def handle_license_update(ctx: RequestCtx, id_: int) -> htt.Response:
    name = str(ctx["form"].get("name") or "").strip()
    if id_ <= 0 or name == "":
        return admin_redirect("Invalid license class.")
    try:
        ReferenceDataRepository(ctx["conn"]).update_license_class(id_, name)
    except sqlite3.IntegrityError as e:
        return admin_redirect(ref_write_error(e) or str(e))
    return admin_redirect()


def handle_license_delete(ctx: RequestCtx, id_: int) -> htt.Response:
    if id_ <= 0:
        return admin_redirect("Invalid license class.")
    try:
        ReferenceDataRepository(ctx["conn"]).delete_license_class(id_)
    except sqlite3.IntegrityError as e:
        return admin_redirect(ref_write_error(e) or str(e))
    return admin_redirect()


def handle_mt_create(ctx: RequestCtx) -> htt.Response:
    name = str(ctx["form"].get("name") or "").strip()
    if name == "":
        return admin_redirect("Name is required.")
    try:
        ReferenceDataRepository(ctx["conn"]).create_membership_type(name)
    except sqlite3.IntegrityError as e:
        return admin_redirect(ref_write_error(e) or str(e))
    return admin_redirect()


def handle_mt_update(ctx: RequestCtx, id_: int) -> htt.Response:
    name = str(ctx["form"].get("name") or "").strip()
    if id_ <= 0 or name == "":
        return admin_redirect("Invalid membership type.")
    try:
        ReferenceDataRepository(ctx["conn"]).update_membership_type(id_, name)
    except sqlite3.IntegrityError as e:
        return admin_redirect(ref_write_error(e) or str(e))
    return admin_redirect()


def handle_mt_delete(ctx: RequestCtx, id_: int) -> htt.Response:
    if id_ <= 0:
        return admin_redirect("Invalid membership type.")
    try:
        year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
        ReferenceDataRepository(ctx["conn"]).delete_membership_type_or_fail(id_, year)
    except RuntimeError as e:
        return admin_redirect(str(e))
    except sqlite3.IntegrityError as e:
        return admin_redirect(ref_write_error(e) or str(e))
    return admin_redirect()


def handle_admin_create(ctx: RequestCtx) -> htt.Response:
    username = str(ctx["form"].get("username") or "").strip()
    password = str(ctx["form"].get("password") or "")
    if username == "" or password.strip() == "":
        return admin_redirect("Username and password are required.")
    try:
        AdminAccountRepository(ctx["conn"]).create_admin_user(username, password)
    except sqlite3.IntegrityError:
        return admin_redirect("That username is already in use.")
    return admin_redirect()


def handle_admin_password(ctx: RequestCtx, id_: int) -> htt.Response:
    password = str(ctx["form"].get("password") or "")
    if id_ <= 0 or password.strip() == "":
        return admin_redirect("Invalid administrator or password.")
    AdminAccountRepository(ctx["conn"]).update_admin_password(id_, password)
    return admin_redirect()


def handle_admin_delete(ctx: RequestCtx, id_: int) -> htt.Response:
    if id_ <= 0:
        return admin_redirect("Invalid administrator.")
    try:
        AdminAccountRepository(ctx["conn"]).delete_admin_user_or_fail(id_)
    except RuntimeError as e:
        return admin_redirect(str(e))
    return admin_redirect()


def handle_manager_create(ctx: RequestCtx) -> htt.Response:
    username = str(ctx["form"].get("username") or "").strip()
    password = str(ctx["form"].get("password") or "")
    display_raw = str(ctx["form"].get("display_name") or "").strip()
    display_name = display_raw or None
    if username == "" or password.strip() == "":
        return admin_redirect("Username and password are required.")
    try:
        AdminAccountRepository(ctx["conn"]).create_manager(username, password, display_name)
    except sqlite3.IntegrityError:
        return admin_redirect("That username is already in use.")
    return admin_redirect()


def handle_manager_password(ctx: RequestCtx, id_: int) -> htt.Response:
    password = str(ctx["form"].get("password") or "")
    if id_ <= 0 or password.strip() == "":
        return admin_redirect("Invalid manager or password.")
    AdminAccountRepository(ctx["conn"]).update_manager_password(id_, password)
    return admin_redirect()


def handle_manager_profile(ctx: RequestCtx, id_: int) -> htt.Response:
    display_raw = str(ctx["form"].get("display_name") or "").strip()
    if id_ <= 0:
        return admin_redirect("Invalid manager.")
    AdminAccountRepository(ctx["conn"]).update_manager_profile(id_, display_raw or None)
    return admin_redirect()


def handle_manager_delete(ctx: RequestCtx, id_: int) -> htt.Response:
    if id_ <= 0:
        return admin_redirect("Invalid manager.")
    try:
        AdminAccountRepository(ctx["conn"]).delete_manager(id_)
    except sqlite3.IntegrityError as e:
        return admin_redirect(ref_write_error(e) or str(e))
    return admin_redirect()
