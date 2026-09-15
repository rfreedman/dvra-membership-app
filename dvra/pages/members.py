"""Members list, CRUD, payments, and member exports."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from dvra import exports
from dvra import http as htt
from dvra import list_params
from dvra import member_list
from dvra import membership_year as myear
from dvra import normalizer
from dvra import view
from dvra.app_settings import AppSettingsRepository
from dvra.context import RequestCtx
from dvra.member_list import MemberListRepository
from dvra.members import DuplicateMemberKeyNumber, MemberRepository
from dvra.pages.common import download_export, html_page, member_not_found
from dvra.payments import PaymentRepository


def _resolve_member_list_params(conn: sqlite3.Connection, flat: dict[str, Any]) -> dict[str, Any]:
    params = member_list.parse_list_query(flat)
    if params["membership_year"] is None:
        params["membership_year"] = AppSettingsRepository(conn).get_current_membership_year()
    return params


def _member_ref(ctx: RequestCtx) -> dict[str, Any]:
    repo = MemberRepository(ctx["conn"])
    return {"license_classes": repo.list_license_classes(), "membership_types": repo.list_membership_types()}


def _rollover_flash(
    mode: str,
    data: dict[str, Any],
    requested: int,
    proposed: int,
    *,
    payment_id: int | None = None,
) -> dict[str, Any]:
    flash: dict[str, Any] = {
        "mode": mode,
        "requested_year": requested,
        "proposed_year": proposed,
        "payment_date": data["payment_date"],
        "membership_type": "" if data["membership_type_id"] is None else str(data["membership_type_id"]),
        "form_number": data["form_number"] or "",
        "notes": data["notes"] or "",
    }
    if payment_id is not None:
        flash["payment_id"] = payment_id
    return flash


def handle_members_filter_post(ctx: RequestCtx) -> htt.Response:
    flat = list_params.members_merge_post(ctx["session"], ctx["form"])
    params = _resolve_member_list_params(ctx["conn"], flat)
    list_params.members_persist(ctx["session"], params)
    return htt.redirect(htt.url_for("/"))


def handle_members_list(ctx: RequestCtx) -> htt.Response:
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
    return html_page(
        inner,
        "Members",
        ctx,
        active_nav="members",
        extra_head=tab_css,
        extra_scripts=scripts,
    )


def handle_members_export(ctx: RequestCtx, fmt: str) -> htt.Response:
    params = _resolve_member_list_params(ctx["conn"], list_params.members_read(ctx["session"]))
    rows = MemberListRepository(ctx["conn"]).list_rows_for_export(params)
    stem = exports.timestamp_stem("members")
    return download_export(
        fmt,
        stem,
        csv_bytes=lambda: exports.members_csv(rows),
        xlsx_bytes=lambda: exports.members_xlsx(rows),
        pdf_bytes=lambda: exports.members_pdf(rows),
    )


def handle_member_new_get(ctx: RequestCtx) -> htt.Response:
    default_year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    inner = view.render(
        "member_new.html",
        error=None,
        base=htt.app_base(),
        default_membership_year=default_year,
        membership_year_options=myear.option_years(default_year),
        **_member_ref(ctx),
    )
    return html_page(inner, "New member", ctx, active_nav="members")


def handle_member_new_post(ctx: RequestCtx) -> htt.Response:
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
        return html_page(inner, "New member", ctx, active_nav="members", status=status)

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


def handle_member_view(ctx: RequestCtx, id_: int) -> htt.Response:
    members_repo = MemberRepository(ctx["conn"])
    member = members_repo.find_member_by_id(id_) if id_ > 0 else None
    if member is None:
        return member_not_found(ctx)
    inner = view.render("member_detail.html", member=member, error=None, base=htt.app_base(), **_member_ref(ctx))
    scripts = view.render("member_detail_scripts.html")
    return html_page(inner, "Member", ctx, extra_scripts=scripts, active_nav="members")


def handle_member_edit(ctx: RequestCtx, id_: int) -> htt.Response:
    members_repo = MemberRepository(ctx["conn"])
    member = members_repo.find_member_by_id(id_) if id_ > 0 else None
    if member is None:
        return member_not_found(ctx)
    row = normalizer.member_update_from_form(ctx["form"])
    scripts = view.render("member_detail_scripts.html")

    def fail(msg: str, status: int) -> htt.Response:
        inner = view.render("member_detail.html", member=member, error=msg, base=htt.app_base(), **_member_ref(ctx))
        return html_page(inner, "Member", ctx, extra_scripts=scripts, status=status, active_nav="members")

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


def handle_member_delete(ctx: RequestCtx, id_: int) -> htt.Response:
    if id_ > 0:
        MemberRepository(ctx["conn"]).delete_member_by_id(id_)
    return htt.redirect(htt.url_for("/"))


def handle_payment_new(ctx: RequestCtx, member_id: int) -> htt.Response:
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
            ctx["session"]["dvra_flash_payment_rollover"] = _rollover_flash("create", data, requested, proposed)
            return htt.redirect(htt.url_for(f"/members/{member_id}/payments"))
        data["membership_year"] = proposed
    try:
        payments_repo.insert_payment(member_id, data)
    except Exception:
        ctx["session"]["dvra_flash_payment_error"] = "Could not save payment."
        return htt.redirect(htt.url_for(f"/members/{member_id}/payments"))
    return htt.redirect(htt.url_for(f"/members/{member_id}/payments"))


def handle_payment_edit(ctx: RequestCtx, payment_id: int) -> htt.Response:
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
            ctx["session"]["dvra_flash_payment_rollover"] = _rollover_flash(
                "edit", data, requested, proposed, payment_id=payment_id
            )
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


def handle_payment_delete(ctx: RequestCtx, payment_id: int) -> htt.Response:
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


def handle_member_payments(ctx: RequestCtx, id_: int) -> htt.Response:
    members_repo = MemberRepository(ctx["conn"])
    member = members_repo.find_member_by_id(id_) if id_ > 0 else None
    if member is None:
        return member_not_found(ctx)
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
    return html_page(inner, "Payments", ctx, extra_scripts=scripts, active_nav="members")
