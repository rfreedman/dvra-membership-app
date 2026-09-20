"""Report pages and exports."""

from __future__ import annotations

from dvra import exports
from dvra import http as htt
from dvra import list_params
from dvra import membership_year as myear
from dvra import payments_report
from dvra import reports as reports_mod
from dvra import view
from dvra.app_settings import AppSettingsRepository
from dvra.context import RequestCtx
from dvra.pages.common import download_export, html_page
from dvra.payments_report import PaymentsReportRepository
from dvra.reports import ReportsRepository


def handle_reports_index(ctx: RequestCtx) -> htt.Response:
    inner = view.render("reports.html", base=htt.app_base())
    return html_page(inner, "Reports", ctx, active_nav="reports")


def handle_payments_report_post(ctx: RequestCtx) -> htt.Response:
    flat = list_params.payments_merge_post(ctx["session"], ctx["form"])
    params = payments_report.parse_payment_report_query(flat)
    list_params.payments_persist(ctx["session"], params)
    return htt.redirect(htt.url_for("/reports/payments"))


def handle_payments_report_get(ctx: RequestCtx) -> htt.Response:
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
    year_display = (
        ""
        if params["membership_year"] == "any"
        else str(params.get("membership_year_filter") or params.get("membership_year") or "")
    )
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
        base=htt.app_base(),
    )
    return html_page(inner, "Payment report", ctx, active_nav="reports")


def handle_payments_report_export(ctx: RequestCtx, fmt: str) -> htt.Response:
    params = payments_report.parse_payment_report_query(list_params.payments_read(ctx["session"]))
    rows = PaymentsReportRepository(ctx["conn"]).list_payment_report_rows(params)
    stem = exports.timestamp_stem("payments-report", compact=True)
    return download_export(
        fmt,
        stem,
        csv_bytes=lambda: exports.payments_csv(rows),
        xlsx_bytes=lambda: exports.payments_xlsx(rows),
        pdf_bytes=lambda: exports.payments_pdf(rows),
    )


def handle_keyholders_post(ctx: RequestCtx) -> htt.Response:
    flat = list_params.keyholders_merge_post(ctx["session"], ctx["form"])
    params = reports_mod.parse_keyholders_query(flat)
    list_params.keyholders_persist(ctx["session"], params)
    return htt.redirect(htt.url_for("/reports/keyholders"))


def handle_keyholders_get(ctx: RequestCtx) -> htt.Response:
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
        base=htt.app_base(),
    )
    return html_page(inner, "Keyholders", ctx, active_nav="reports")


def handle_keyholders_export(ctx: RequestCtx, fmt: str) -> htt.Response:
    kh = reports_mod.parse_keyholders_query(list_params.keyholders_read(ctx["session"]))
    rows = ReportsRepository(ctx["conn"]).list_keyholders(kh["sort_by"], kh["sort_dir"])
    stem = exports.timestamp_stem("keyholders-report", compact=True)
    return download_export(
        fmt,
        stem,
        csv_bytes=lambda: exports.keyholders_csv(rows),
        xlsx_bytes=lambda: exports.keyholders_xlsx(rows),
        pdf_bytes=lambda: exports.keyholders_pdf(rows),
    )


def handle_roster_post(ctx: RequestCtx, dest: str) -> htt.Response:
    default_year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    list_params.roster_merge_post_year(ctx["session"], ctx["form"], default_year)
    return htt.redirect(htt.url_for(dest))


def handle_roster_name_get(ctx: RequestCtx) -> htt.Response:
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
    return html_page(inner, "Roster by name", ctx, active_nav="reports")


def handle_roster_callsign_get(ctx: RequestCtx) -> htt.Response:
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
    return html_page(inner, "Roster by callsign", ctx, active_nav="reports")


def handle_roster_name_export(ctx: RequestCtx, fmt: str) -> htt.Response:
    year = list_params.roster_read_year(
        ctx["session"], AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    )
    rows = ReportsRepository(ctx["conn"]).roster_by_name(year)
    stem = exports.timestamp_stem("roster-by-name", compact=True)
    return download_export(
        fmt,
        stem,
        csv_bytes=lambda: exports.roster_by_name_csv(rows),
        xlsx_bytes=lambda: exports.roster_by_name_xlsx(rows),
        pdf_bytes=lambda: exports.roster_by_name_pdf(rows),
    )


def handle_roster_callsign_export(ctx: RequestCtx, fmt: str) -> htt.Response:
    year = list_params.roster_read_year(
        ctx["session"], AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    )
    rows = ReportsRepository(ctx["conn"]).roster_by_callsign(year)
    stem = exports.timestamp_stem("roster-by-callsign", compact=True)
    return download_export(
        fmt,
        stem,
        csv_bytes=lambda: exports.roster_by_callsign_csv(rows),
        xlsx_bytes=lambda: exports.roster_by_callsign_xlsx(rows),
        pdf_bytes=lambda: exports.roster_by_callsign_pdf(rows),
    )


def handle_new_members_post(ctx: RequestCtx) -> htt.Response:
    flat = list_params.new_members_merge_post(ctx["session"], ctx["form"])
    params = reports_mod.parse_new_members_query(flat)
    list_params.new_members_persist(ctx["session"], params)
    return htt.redirect(htt.url_for("/reports/new-members"))


def handle_new_members_get(ctx: RequestCtx) -> htt.Response:
    params = reports_mod.parse_new_members_query(list_params.new_members_read(ctx["session"]))
    list_params.new_members_persist(ctx["session"], params)
    rows = ReportsRepository(ctx["conn"]).list_new_members(
        params["since"], params["sort_by"], params["sort_dir"]
    )
    post_action = htt.url_for("/reports/new-members")
    sort_post = {}
    for field in (
        "name",
        "call_sign",
        "license_class",
        "membership_type",
        "city",
        "state",
        "date_paid",
        "paid_through",
    ):
        nsb, nsd = reports_mod.next_new_members_sort_choice(params["sort_by"], params["sort_dir"], field)
        sort_post[field] = {"sort_by": nsb, "sort_dir": nsd}
    inner = view.render(
        "reports_new_members.html",
        total=len(rows),
        rows=rows,
        since=params["since"],
        sort_by=params["sort_by"],
        sort_dir=params["sort_dir"],
        new_members_sort_post=sort_post,
        new_members_post_action=post_action,
        base=htt.app_base(),
    )
    return html_page(inner, "New members", ctx, active_nav="reports")


def handle_new_members_export(ctx: RequestCtx, fmt: str) -> htt.Response:
    params = reports_mod.parse_new_members_query(list_params.new_members_read(ctx["session"]))
    rows = ReportsRepository(ctx["conn"]).list_new_members(
        params["since"], params["sort_by"], params["sort_dir"]
    )
    stem = exports.timestamp_stem("new-members-report", compact=True)
    return download_export(
        fmt,
        stem,
        csv_bytes=lambda: exports.new_members_csv(rows),
        xlsx_bytes=lambda: exports.new_members_xlsx(rows),
        pdf_bytes=lambda: exports.new_members_pdf(rows),
    )


def _year_memberships_sort_post(params: dict[str, Any]) -> dict[str, dict[str, str]]:
    sort_post = {}
    for field in (
        "name",
        "call_sign",
        "license_class",
        "membership_type",
        "city",
        "state",
        "date_paid",
        "paid_through",
    ):
        nsb, nsd = reports_mod.next_new_members_sort_choice(params["sort_by"], params["sort_dir"], field)
        sort_post[field] = {"sort_by": nsb, "sort_dir": nsd}
    return sort_post


def handle_paid_memberships_post(ctx: RequestCtx) -> htt.Response:
    default_year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    flat = list_params.paid_memberships_merge_post(ctx["session"], ctx["form"])
    params = reports_mod.parse_year_memberships_query(flat, default_year)
    list_params.paid_memberships_persist(ctx["session"], params)
    return htt.redirect(htt.url_for("/reports/paid-memberships"))


def handle_unpaid_memberships_post(ctx: RequestCtx) -> htt.Response:
    default_year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    flat = list_params.unpaid_memberships_merge_post(ctx["session"], ctx["form"])
    params = reports_mod.parse_year_memberships_query(flat, default_year)
    list_params.unpaid_memberships_persist(ctx["session"], params)
    return htt.redirect(htt.url_for("/reports/unpaid-memberships"))


def handle_paid_memberships_get(ctx: RequestCtx) -> htt.Response:
    default_year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    params = reports_mod.parse_year_memberships_query(
        list_params.paid_memberships_read(ctx["session"]), default_year
    )
    list_params.paid_memberships_persist(ctx["session"], params)
    year = int(params["membership_year"])
    rows = ReportsRepository(ctx["conn"]).list_paid_memberships(year, params["sort_by"], params["sort_dir"])
    inner = view.render(
        "reports_year_memberships.html",
        heading="Paid memberships",
        help_text=(
            f"Members paid for membership year {year} "
            f"(a payment for {year} or {year - 1} with paid through {year}-12-31 or later)."
        ),
        total=len(rows),
        rows=rows,
        membership_year=year,
        membership_year_options=myear.option_years(default_year),
        sort_by=params["sort_by"],
        sort_dir=params["sort_dir"],
        sort_post=_year_memberships_sort_post(params),
        post_action=htt.url_for("/reports/paid-memberships"),
        export_stem="/reports/paid-memberships/export",
        export_prefix="paid-memberships-exp-",
        base=htt.app_base(),
    )
    return html_page(inner, "Paid memberships", ctx, active_nav="reports")


def handle_unpaid_memberships_get(ctx: RequestCtx) -> htt.Response:
    default_year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    params = reports_mod.parse_year_memberships_query(
        list_params.unpaid_memberships_read(ctx["session"]), default_year
    )
    list_params.unpaid_memberships_persist(ctx["session"], params)
    year = int(params["membership_year"])
    prior = year - 1
    rows = ReportsRepository(ctx["conn"]).list_unpaid_memberships(year, params["sort_by"], params["sort_dir"])
    inner = view.render(
        "reports_year_memberships.html",
        heading="Unpaid memberships",
        help_text=(
            f"Members paid through {prior}-12-31 who do not have a payment paid through {year}-12-31 or later."
        ),
        total=len(rows),
        rows=rows,
        membership_year=year,
        membership_year_options=myear.option_years(default_year),
        sort_by=params["sort_by"],
        sort_dir=params["sort_dir"],
        sort_post=_year_memberships_sort_post(params),
        post_action=htt.url_for("/reports/unpaid-memberships"),
        export_stem="/reports/unpaid-memberships/export",
        export_prefix="unpaid-memberships-exp-",
        base=htt.app_base(),
    )
    return html_page(inner, "Unpaid memberships", ctx, active_nav="reports")


def handle_paid_memberships_export(ctx: RequestCtx, fmt: str) -> htt.Response:
    default_year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    params = reports_mod.parse_year_memberships_query(
        list_params.paid_memberships_read(ctx["session"]), default_year
    )
    rows = ReportsRepository(ctx["conn"]).list_paid_memberships(
        int(params["membership_year"]), params["sort_by"], params["sort_dir"]
    )
    stem = exports.timestamp_stem("paid-memberships-report", compact=True)
    return download_export(
        fmt,
        stem,
        csv_bytes=lambda: exports.membership_status_csv(rows),
        xlsx_bytes=lambda: exports.membership_status_xlsx(rows, "Paid memberships"),
        pdf_bytes=lambda: exports.membership_status_pdf(rows, "Paid memberships"),
    )


def handle_unpaid_memberships_export(ctx: RequestCtx, fmt: str) -> htt.Response:
    default_year = AppSettingsRepository(ctx["conn"]).get_current_membership_year()
    params = reports_mod.parse_year_memberships_query(
        list_params.unpaid_memberships_read(ctx["session"]), default_year
    )
    rows = ReportsRepository(ctx["conn"]).list_unpaid_memberships(
        int(params["membership_year"]), params["sort_by"], params["sort_dir"]
    )
    stem = exports.timestamp_stem("unpaid-memberships-report", compact=True)
    return download_export(
        fmt,
        stem,
        csv_bytes=lambda: exports.membership_status_csv(rows),
        xlsx_bytes=lambda: exports.membership_status_xlsx(rows, "Unpaid memberships"),
        pdf_bytes=lambda: exports.membership_status_pdf(rows, "Unpaid memberships"),
    )
