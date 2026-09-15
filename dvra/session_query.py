"""Shared session read/write + POST overlay merge for list/report pages."""

from __future__ import annotations

from typing import Any


def read(session: dict[str, Any], session_key: str) -> dict[str, Any]:
    snap = session.get(session_key)
    return dict(snap) if isinstance(snap, dict) else {}


def write(session: dict[str, Any], session_key: str, flat: dict[str, Any]) -> None:
    session[session_key] = dict(flat)


def flatten_scalar_map(qp: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for k, v in qp.items():
        if isinstance(v, (list, tuple)):
            if not v:
                continue
            v = v[-1]
        if isinstance(v, (str, int, float, bool)):
            flat[str(k)] = v
    return flat


def merge_post(
    session: dict[str, Any],
    session_key: str,
    parsed_body: dict[str, Any],
    clear_field: str | None,
) -> dict[str, Any]:
    flat = flatten_scalar_map(parsed_body)
    if clear_field is not None and str(flat.get(clear_field, "")) == "1":
        return {}
    if clear_field is not None:
        flat.pop(clear_field, None)
    merged = read(session, session_key)
    merged.update(flat)
    return merged
