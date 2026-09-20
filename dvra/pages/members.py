"""Members list, CRUD, payments, and member exports."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from dvra import exports
from dvra import family
from dvra import http as htt
from dvra import list_params
from dvra import member_list
from dvra import membership_year as myear
from dvra import join_extension
from dvra import member_form_validation
from dvra import new_ham
from dvra import normalizer
from dvra.license_class import find_unlicensed_class_id, is_unlicensed_license_class_id
from dvra import view
from dvra.app_settings import AppSettingsRepository
from dvra.context import RequestCtx
from dvra.member_list import MemberListRepository
from dvra.members import DuplicateMemberKeyNumber, MemberHasFamilySecondaries, MemberRepository
from dvra.pages.common import download_export, html_page, member_not_found
from dvra.payments import MemberIsDeceased, PaymentRepository
from dvra.reference_data import ReferenceDataRepository, find_default_membership_type_id


def _resolve_member_list_params(conn: sqlite3.Connection, flat: dict[str, Any]) -> dict[str, Any]:
    params = member_list.parse_list_query(flat)
    if params["membership_year"] is None:
        params["membership_year"] = AppSettingsRepository(conn).get_current_membership_year()
    return params


def _new_member_join_date() -> date:
    return date.today()


def _member_ref(
    ctx: RequestCtx,
    exclude_member_id: int | None = None,
    include_primary_id: int | None = None,
    include_license_ids: list[int] | None = None,
    include_membership_ids: list[int] | None = None,
) -> dict[str, Any]:
    repo = MemberRepository(ctx["conn"])
    year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    return {
        "license_classes": repo.list_license_classes(
            include_hidden=False, include_ids=include_license_ids
        ),
        "membership_types": repo.list_membership_types(
            include_hidden=False, include_ids=include_membership_ids
        ),
        "family_primary_options": repo.list_family_primary_options(
            exclude_member_id, include_primary_id
        ),
        "new_ham_type_id": new_ham.find_type_id(ctx["conn"]),
        "new_ham_convert_confirm": new_ham.NEW_HAM_CONVERT_CONFIRM,
        "unlicensed_license_class_id": find_unlicensed_class_id(ctx["conn"]),
        "current_membership_year": year,
        "has_own_current_year_payment": False,
        "covered_by_delete_current_payment_confirm": family.covered_by_delete_current_payment_confirm(
            year
        ),
    }


def _member_detail_template_ctx(ctx: RequestCtx, member: dict[str, Any]) -> dict[str, Any]:
    year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    member_id = member.get("id")
    has_current = False
    if member_id is not None:
        has_current = family.member_has_payment_for_year(ctx["conn"], int(member_id), year)
    return {
        **_member_ref(
            ctx,
            member.get("id"),
            member.get("family_primary_member_id"),
            include_license_ids=[member.get("license_class_id")],
            include_membership_ids=[member.get("membership_type_id")],
        ),
        "call_sign_disabled": is_unlicensed_license_class_id(
            ctx["conn"], member.get("license_class_id")
        ),
        "has_own_current_year_payment": has_current,
    }


def _member_new_template_ctx(ctx: RequestCtx, body: dict[str, Any] | None = None) -> dict[str, Any]:
    default_year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    selected_year = default_year
    if body is not None:
        parsed = myear.parse_year_input(body.get("paid_for_year"))
        if parsed is not None:
            selected_year = parsed
    selected_membership_type_id = find_default_membership_type_id(ctx["conn"])
    if body is not None:
        mt_raw = str(body.get("membership_type") or "").strip()
        if mt_raw.isdigit():
            selected_membership_type_id = int(mt_raw)
    selected_license_class_id: int | None = None
    if body is not None:
        lic_raw = str(body.get("license_class") or "").strip()
        if lic_raw.isdigit():
            selected_license_class_id = int(lic_raw)
    call_sign_disabled = is_unlicensed_license_class_id(ctx["conn"], selected_license_class_id)
    return {
        **_member_ref(ctx),
        "base": htt.app_base(),
        "default_membership_year": default_year,
        "selected_paid_for_year": selected_year,
        "selected_membership_type_id": selected_membership_type_id,
        "call_sign_disabled": call_sign_disabled,
        "membership_year_options": myear.option_years(default_year),
        "form_values": body or {},
    }


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
        "include_deceased": params.get("include_deceased") or "no",
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
        include_deceased=params.get("include_deceased") or "no",
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
        members_note_url_prefix=htt.url_for("/members"),
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
    inner = view.render("member_new.html", error=None, **_member_new_template_ctx(ctx))
    scripts = view.render("member_new_scripts.html")
    return html_page(inner, "New member", ctx, active_nav="members", extra_scripts=scripts)


def handle_member_new_post(ctx: RequestCtx) -> htt.Response:
    body = ctx["form"]
    paid_year = myear.parse_year_input(body.get("paid_for_year"))
    paid_through = myear.paid_through_iso(paid_year) if paid_year is not None else None
    ref = _member_new_template_ctx(ctx, body)
    members_repo = MemberRepository(ctx["conn"])
    payments_repo = PaymentRepository(ctx["conn"])
    row = normalizer.member_create_from_form(body, paid_through)
    scripts = view.render("member_new_scripts.html")

    def fail(msg: str, status: int) -> htt.Response:
        inner = view.render("member_new.html", error=msg, **ref)
        return html_page(inner, "New member", ctx, active_nav="members", extra_scripts=scripts, status=status)

    val_err = member_form_validation.validate_member_row(
        ctx["conn"],
        row,
        body,
        require_paid_year=not row.get("deceased"),
        paid_year=paid_year,
        member_id=None,
    )
    if val_err:
        return fail(val_err, 400)
    cs = row["call_sign"]
    if cs is not None and members_repo.find_id_by_nonnull_call_sign(cs) is not None:
        return fail("That call sign is already in use.", 409)
    if cs is None and members_repo.exists_name_without_call_sign(row["last_name"], row["first_name"], None):
        return fail("A member with this name already exists without a call sign.", 409)
    try:
        current_year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
        covered_by_current = (
            row.get("family_primary_member_id") is not None and paid_year == current_year
        )
        confirmed_delete = str(body.get("confirm_delete_current_year_payment") or "") == "1"
        if covered_by_current and not confirmed_delete:
            return fail(family.covered_by_delete_current_payment_confirm(current_year), 400)
        new_id = members_repo.insert_member(row)
        if paid_year is not None and not row.get("deceased") and not covered_by_current:
            join_date = _new_member_join_date()
            initial = join_extension.resolve_new_member_initial_payment(
                ctx["conn"],
                join_date,
                row["membership_type_id"],
                paid_year,
            )
            payments_repo.insert_payment(
                new_id,
                {
                    "payment_date": join_date.isoformat(),
                    "membership_year": paid_year,
                    "membership_type_id": row["membership_type_id"],
                    "paid_through": initial["paid_through"],
                    "notes": initial["notes"],
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
    inner = view.render(
        "member_detail.html",
        member=member,
        error=None,
        base=htt.app_base(),
        **_member_detail_template_ctx(ctx, member),
    )
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
        inner = view.render(
            "member_detail.html",
            member=member,
            error=msg,
            base=htt.app_base(),
            **_member_detail_template_ctx(ctx, member),
        )
        return html_page(inner, "Member", ctx, extra_scripts=scripts, status=status, active_nav="members")

    val_err = member_form_validation.validate_member_row(
        ctx["conn"], row, ctx["form"], require_paid_year=False, paid_year=None, member_id=id_
    )
    if val_err:
        return fail(val_err, 400)
    eff = row["call_sign"]
    oid = members_repo.find_id_by_nonnull_call_sign(eff) if eff else None
    if eff is not None and oid is not None and oid != id_:
        return fail("That call sign is already in use.", 409)
    if eff is None and members_repo.exists_name_without_call_sign(row["last_name"], row["first_name"], id_):
        return fail("Another member with this name already exists without a call sign.", 409)
    year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    has_current = family.member_has_payment_for_year(ctx["conn"], id_, year)
    confirmed_delete = str(ctx["form"].get("confirm_delete_current_year_payment") or "") == "1"
    new_primary = row.get("family_primary_member_id")
    if new_primary is not None and has_current and not confirmed_delete:
        return fail(family.covered_by_delete_current_payment_confirm(year), 400)
    try:
        members_repo.update_member(
            id_,
            row,
            delete_current_year_payment=bool(new_primary and has_current and confirmed_delete),
        )
    except DuplicateMemberKeyNumber:
        return fail("That key number is already assigned to another member.", 409)
    except sqlite3.Error:
        return fail("Could not save member.", 400)
    return htt.redirect(htt.url_for(f"/members/{id_}/view"))


def handle_member_delete(ctx: RequestCtx, id_: int) -> htt.Response:
    members_repo = MemberRepository(ctx["conn"])
    if id_ <= 0:
        return htt.redirect(htt.url_for("/"))
    try:
        members_repo.delete_member_by_id(id_)
    except MemberHasFamilySecondaries as exc:
        member = members_repo.find_member_by_id(id_)
        if member is None:
            return htt.redirect(htt.url_for("/"))
        scripts = view.render("member_detail_scripts.html")
        inner = view.render(
            "member_detail.html",
            member=member,
            error=str(exc),
            base=htt.app_base(),
            **_member_detail_template_ctx(ctx, member),
        )
        return html_page(inner, "Member", ctx, extra_scripts=scripts, status=400, active_nav="members")
    return htt.redirect(htt.url_for("/"))


def _member_note_label(member: dict[str, Any]) -> str:
    name = f"{member['last_name']}, {member['first_name']}"
    call = (member.get("call_sign") or "").strip()
    if call:
        return f"{name} ({call})"
    return name


def handle_member_note_get(ctx: RequestCtx, id_: int) -> htt.Response:
    members_repo = MemberRepository(ctx["conn"])
    member = members_repo.find_member_by_id(id_) if id_ > 0 else None
    if member is None:
        return htt.json_body({"error": "Not found"}, status=404)
    return htt.json_body(
        {
            "id": member["id"],
            "notes": member.get("notes") or "",
            "label": _member_note_label(member),
            "has_note": bool((member.get("notes") or "").strip()),
        }
    )


def handle_member_note_post(ctx: RequestCtx, id_: int) -> htt.Response:
    members_repo = MemberRepository(ctx["conn"])
    if id_ <= 0 or members_repo.find_member_by_id(id_) is None:
        return htt.json_body({"error": "Not found"}, status=404)
    notes = normalizer.strip_optional(str(ctx["form"].get("notes") or ""))
    if not members_repo.update_member_notes(id_, notes):
        return htt.json_body({"error": "Not found"}, status=404)
    return htt.json_body({"ok": True, "has_note": bool(notes), "notes": notes or ""})


def handle_payment_new(ctx: RequestCtx, member_id: int) -> htt.Response:
    members_repo = MemberRepository(ctx["conn"])
    payments_repo = PaymentRepository(ctx["conn"])
    member = members_repo.find_member_by_id(member_id) if member_id > 0 else None
    if member is None:
        return htt.redirect(htt.url_for("/"))
    if member.get("deceased"):
        ctx["session"]["dvra_flash_payment_error"] = (
            "This member is marked SK and cannot accept new payments."
        )
        return htt.redirect(htt.url_for(f"/members/{member_id}/payments"))
    parsed = normalizer.payment_from_form(ctx["form"])
    if not parsed["ok"]:
        ctx["session"]["dvra_flash_payment_error"] = parsed["error"]
        return htt.redirect(htt.url_for(f"/members/{member_id}/payments"))
    data = parsed["data"]
    hidden_err = ReferenceDataRepository(ctx["conn"]).hidden_membership_type_attach_error(
        data["membership_type_id"]
    )
    if hidden_err:
        ctx["session"]["dvra_flash_payment_error"] = hidden_err
        return htt.redirect(htt.url_for(f"/members/{member_id}/payments"))
    new_ham_err = new_ham.payment_membership_type_error(
        ctx["conn"], member_id, data["membership_type_id"]
    )
    if new_ham_err:
        ctx["session"]["dvra_flash_payment_error"] = new_ham_err
        return htt.redirect(htt.url_for(f"/members/{member_id}/payments"))
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
    except MemberIsDeceased:
        ctx["session"]["dvra_flash_payment_error"] = (
            "This member is marked SK and cannot accept new payments."
        )
        return htt.redirect(htt.url_for(f"/members/{member_id}/payments"))
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
    hidden_err = ReferenceDataRepository(ctx["conn"]).hidden_membership_type_attach_error(
        data["membership_type_id"],
        existing_id=meta.get("membership_type_id"),
    )
    if hidden_err:
        ctx["session"]["dvra_flash_payment_error"] = hidden_err
        return htt.redirect(htt.url_for(f"/members/{member_id}/payments"))
    new_ham_err = new_ham.payment_membership_type_error(
        ctx["conn"], member_id, data["membership_type_id"], payment_id
    )
    if new_ham_err:
        ctx["session"]["dvra_flash_payment_error"] = new_ham_err
        return htt.redirect(htt.url_for(f"/members/{member_id}/payments"))
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
    default_year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    include_type_ids = [member.get("membership_type_id")]
    include_type_ids.extend(p.get("membership_type_id") for p in payments)
    inner = view.render(
        "member_payments.html",
        member=member,
        payments=payments,
        membership_types=members_repo.list_membership_types(
            include_hidden=False, include_ids=include_type_ids
        ),
        flash_error=flash,
        rollover=rollover,
        new_ham_notice=new_ham.NEW_HAM_PAYMENTS_NOTICE
        if new_ham.member_has_new_ham_payment(ctx["conn"], id_)
        else None,
        default_membership_year=default_year,
        membership_year_options=myear.option_years(default_year),
        base=htt.app_base(),
    )
    scripts = view.render("member_payments_scripts.html")
    return html_page(inner, "Payments", ctx, extra_scripts=scripts, active_nav="members")
