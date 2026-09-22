"""PDF export (embedded chart images) for membership report."""

from __future__ import annotations

import io
from typing import Any

from dvra.exports import _PDF_FONT, _new_landscape_pdf


_BLUE_HEX = "#4A86E8"
_RED_HEX = "#E06666"


def _chart_pngs(report: dict[str, Any]) -> dict[str, bytes]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Same figure size for all charts so titles scale identically in the PDF.
    figsize = (5.5, 3.4)
    title_fontsize = 14
    title_pad = 4

    def _title(ax: Any, text: str) -> None:
        ax.set_title(text, fontsize=title_fontsize, pad=title_pad, fontweight="bold")

    def _grid(ax: Any) -> None:
        """Match Chart.js-style background grid on cartesian charts."""
        ax.grid(True, axis="both", linestyle="-", linewidth=0.6, color="#d0d0d0", zorder=0)
        ax.set_axisbelow(True)
        for spine in ax.spines.values():
            spine.set_color("#b0b0b0")

    def _label_bars(
        ax: Any,
        bars: Any,
        values: list[int],
        *,
        percents: list[int] | None = None,
        fontsize: int = 11,
    ) -> None:
        """Draw count (and optional percent) labels inside bars when tall enough."""
        fig = ax.figure
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        min_height_px = fontsize * (2.4 if percents is not None else 1.25)
        pcts = percents or []
        for i, (bar, value) in enumerate(zip(bars, values)):
            if not value:
                continue
            if bar.get_window_extent(renderer).height < min_height_px:
                continue
            if percents is not None and i < len(pcts):
                text = f"{value}\n({pcts[i]}%)"
            else:
                text = str(value)
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() / 2,
                text,
                ha="center",
                va="center",
                color="white",
                fontweight="bold",
                fontsize=fontsize,
                linespacing=1.1,
            )

    out: dict[str, bytes] = {}

    labels = [r["month_name"] for r in report["member_counts_by_month"]]
    values = [int(r["count"]) for r in report["member_counts_by_month"]]
    fig, ax = plt.subplots(figsize=figsize, dpi=120)
    ax.plot(labels, values, color=_BLUE_HEX, linewidth=2, marker="o", markersize=6, zorder=3)
    _title(ax, "Member Count by Month")
    ax.tick_params(axis="x", labelrotation=45)
    ymax = max(values) if values else 0
    ax.set_ylim(0, ymax * 1.15 if ymax else 1)
    _grid(ax)
    for x, y in zip(labels, values):
        if not y:
            continue
        ax.annotate(
            str(y),
            (x, y),
            textcoords="offset points",
            xytext=(0, 6),
            ha="center",
            va="bottom",
            fontweight="bold",
            fontsize=10,
            color="#333333",
        )
    fig.tight_layout(pad=0.4)
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    out["member_count"] = buf.getvalue()

    labels = [r["name"] for r in report["license_class"]] or ["(none)"]
    values = [int(r["count"]) for r in report["license_class"]] or [0]
    percents = [int(r["percent"]) for r in report["license_class"]] or [0]
    fig, ax = plt.subplots(figsize=figsize, dpi=120)
    bars = ax.bar(labels, values, color=_BLUE_HEX, zorder=3)
    _title(ax, "License Class Distribution")
    ax.tick_params(axis="x", labelrotation=30)
    ymax = max(values) if values else 0
    ax.set_ylim(0, ymax * 1.15 if ymax else 1)
    _grid(ax)
    fig.tight_layout(pad=0.4)
    _label_bars(ax, bars, values, percents=percents)
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    out["license"] = buf.getvalue()

    labels = [r["month_name"] for r in report["new_members_ytd"]]
    values = [int(r["count"]) for r in report["new_members_ytd"]]
    fig, ax = plt.subplots(figsize=figsize, dpi=120)
    bars = ax.bar(labels, values, color=_BLUE_HEX, zorder=3)
    _title(ax, "New Member Enrollment")
    ax.tick_params(axis="x", labelrotation=45)
    ymax = max(values) if values else 0
    ax.set_ylim(0, ymax * 1.15 if ymax else 1)
    _grid(ax)
    fig.tight_layout(pad=0.4)
    _label_bars(ax, bars, values)
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    out["enrollment"] = buf.getvalue()

    fig, ax = plt.subplots(figsize=figsize, dpi=120)
    # Draw N then Y (swapped section order); legend key stays Y, N.
    sizes = [int(report["arrl_non_members"]), int(report["arrl_members"])]
    if sum(sizes) == 0:
        ax.text(0.5, 0.5, "No data", ha="center", va="center")
        ax.set_axis_off()
        _title(ax, "ARRL Membership")
    else:
        percents = [
            int(report["arrl_non_members_percent"]),
            int(report["arrl_members_percent"]),
        ]
        label_i = [0]

        def _label(_pct: float) -> str:
            i = label_i[0]
            label_i[0] += 1
            count = sizes[i]
            if count == 0:
                return ""
            return f"{count}\n({percents[i]}%)"

        wedges, _texts, autotexts = ax.pie(
            sizes,
            labels=None,
            colors=[_RED_HEX, _BLUE_HEX],
            autopct=_label,
            startangle=90,
        )
        for t in autotexts:
            t.set_color("white")
            t.set_fontweight("bold")
            t.set_fontsize(10)
        _title(ax, "ARRL Membership")
        ax.legend(
            [wedges[1], wedges[0]],
            ["Y", "N"],
            loc="lower center",
            bbox_to_anchor=(0.5, -0.02),
            ncol=2,
            frameon=False,
        )
    fig.tight_layout(pad=0.4)
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    out["arrl"] = buf.getvalue()

    return out


def membership_report_pdf(report: dict[str, Any]) -> bytes:
    import tempfile
    from pathlib import Path

    charts = _chart_pngs(report)
    pdf = _new_landscape_pdf()
    pdf.add_page()
    pdf.set_font(_PDF_FONT, "B", 14)
    pdf.cell(0, 8, report["report_heading"], new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    left_x = pdf.l_margin
    table_w = 90
    col1 = 50
    col2 = 20
    col3 = 20
    header_h = 6.0
    row_h = 5.0
    section_gap = 2.0
    content_top = pdf.get_y()

    def _header_fill() -> None:
        pdf.set_fill_color(107, 114, 128)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font(_PDF_FONT, "B", 9)

    def _body_text() -> None:
        pdf.set_text_color(0, 0, 0)
        pdf.set_font(_PDF_FONT, "", 9)

    def _section_header_two_col(label: str, value: str) -> None:
        _header_fill()
        pdf.set_x(left_x)
        pdf.cell(col1 + col2, header_h, label, border=1, fill=True)
        pdf.cell(col3, header_h, value, border=1, align="R", fill=True, new_x="LMARGIN", new_y="NEXT")
        _body_text()

    def _section_header_three_col(label: str, count_label: str, pct_label: str) -> None:
        _header_fill()
        pdf.set_x(left_x)
        pdf.cell(col1, header_h, label, border=1, fill=True)
        pdf.cell(col2, header_h, count_label, border=1, align="R", fill=True)
        pdf.cell(
            col3,
            header_h,
            pct_label,
            border=1,
            align="R",
            fill=True,
            new_x="LMARGIN",
            new_y="NEXT",
        )
        _body_text()

    def _row(label: str, value: str) -> None:
        _body_text()
        pdf.set_x(left_x)
        pdf.cell(col1 + col2, row_h, label, border=1)
        pdf.cell(col3, row_h, value, border=1, align="R", new_x="LMARGIN", new_y="NEXT")

    def _row_three(label: str, count: str, percent: str) -> None:
        _body_text()
        pdf.set_x(left_x)
        pdf.cell(col1, row_h, label, border=1)
        pdf.cell(col2, row_h, count, border=1, align="R")
        pdf.cell(col3, row_h, percent, border=1, align="R", new_x="LMARGIN", new_y="NEXT")

    _section_header_two_col("Member Count", str(int(report["member_count"])))
    for row in report["member_counts_by_month"]:
        _row(row["month_name"], str(int(row["count"])))
    pdf.ln(section_gap)
    _section_header_three_col("License Class", "Count", "Pct.")
    for row in report["license_class"]:
        _row_three(
            str(row["name"]),
            str(int(row["count"])),
            f"{int(row['percent'])}%",
        )
    pdf.ln(section_gap)
    _section_header_two_col("New Members This Month", str(int(report["new_members_month"])))
    pdf.ln(section_gap)
    _section_header_two_col("New Members YTD", str(int(report["new_members_ytd_total"])))
    for row in report["new_members_ytd"]:
        _row(row["month_name"], str(int(row["count"])))
    pdf.ln(section_gap)
    _section_header_three_col("ARRL Membership", "Count", "Pct.")
    _row_three(
        "Members",
        str(int(report["arrl_members"])),
        f"{int(report['arrl_members_percent'])}%",
    )
    _row_three(
        "Non-Members",
        str(int(report["arrl_non_members"])),
        f"{int(report['arrl_non_members_percent'])}%",
    )

    right_margin = pdf.r_margin
    usable_top = content_top
    usable_bottom = pdf.h - pdf.b_margin
    usable_h = usable_bottom - usable_top
    keys = ("member_count", "license", "enrollment", "arrl")
    # All chart PNGs share figsize (5.5, 3.4).
    aspect = 3.4 / 5.5
    img_w = 100.0
    heights = [img_w * aspect for _ in keys]
    n_gaps = len(keys) - 1
    min_gap = 3.0
    needed = sum(heights) + n_gaps * min_gap
    if needed > usable_h:
        scale = usable_h / needed
        img_w *= scale
        heights = [img_w * aspect for _ in keys]
    gap = (usable_h - sum(heights)) / n_gaps if n_gaps else 0.0
    table_right = left_x + table_w
    flush_right_x = pdf.w - right_margin - img_w
    horiz_gap = max(0.0, flush_right_x - table_right)
    right_x = table_right + horiz_gap / 2
    y = usable_top
    with tempfile.TemporaryDirectory(prefix="dvra-mbr-") as tmp:
        tmp_path = Path(tmp)
        for key, height in zip(keys, heights):
            path = tmp_path / f"{key}.png"
            path.write_bytes(charts[key])
            pdf.image(str(path), x=right_x, y=y, w=img_w, h=height)
            y += height + gap

    return bytes(pdf.output())
