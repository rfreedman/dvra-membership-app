"""Shared list/report column-sort helpers."""

from __future__ import annotations

from collections.abc import Collection


def normalize_sort(sort_by: str, sort_dir: str, allowed: Collection[str], default_by: str) -> tuple[str, str]:
    field = sort_by if sort_by in allowed else default_by
    direction = "desc" if sort_dir.lower() == "desc" else "asc"
    return field, direction


def next_sort_choice(
    current_sort_by: str,
    current_sort_dir: str,
    clicked_field: str,
    *,
    desc_first: Collection[str] | None = None,
) -> tuple[str, str]:
    if current_sort_by == clicked_field:
        return clicked_field, "desc" if current_sort_dir == "asc" else "asc"
    first = desc_first or ()
    return clicked_field, "desc" if clicked_field in first else "asc"
