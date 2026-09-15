"""Parse/canonicalize US mailing-address text (roster spreadsheet + member storage).

DVRA roster column **O** often omits a comma between street and city
(``123 Main Rd Town, ST ZIP``). **`parse_roster_us_address`** peels **ST ZIP** then splits street vs city; import stores the parts on **`members`**.

Rules:

1. Normalize whitespace (newlines → comma-space peel ``ST ZIP``).
2. If the prefix still has commas, **`rsplit(',', 1)`** for street vs city; if the city side begins with a **unit / bare apt #** (before the real city name), move that token onto the street.
3. Else PO/postal prefixes → locality is the trailing token cluster.
4. Else find the **last** known street-type token (Rd/Ave/Ln/St/Highway/…) and split; **Bridge** is skipped when **St**/**Street** follows; **Highway**/**Route** keeps a leading numeric route on the street.
5. Else last token = city.

See tests and **`scripts/write_address_parse_csv`** for previews.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional

_PUNCT_TAIL = re.compile(r"[^\w#]+$", re.UNICODE)

_IGNORE_STREET_TYPE = frozenset({"MT", "IN", "ME", "OR", "WI", "OK"})

_STREET_TYPE_COMPOUND_THEN_SUFFIX: frozenset[str] = frozenset({"BR", "BRG", "BRIDGE"})
_ST_PRIMARY_SUFFIX_AFTER_COMPOUND: frozenset[str] = frozenset({"ST", "STS", "STREET"})

_ROUTE_TAIL_TOKENS: frozenset[str] = frozenset({"HIGHWAY", "HWY", "ROUTE", "RTE", "RT"})

_STREET_TYPE_TOKENS: frozenset[str] = frozenset(
    """
    RD ROAD RDS RDE
    DR DRIVE DRV
    ST STS STREET
    AVE AV AVENUE
    BLVD BLV BOULEVARD BOULEWARD BLOULEVARD PLZ
    LN LANE LN.
    WAY WY CIR CIRCLE CRT CT COURT
    HWY HW HIGHWAY RTE RT ROUTE
    PKWY PARKWAY PWY PY
    TER TERR TERRACE TR
    PASS PATH PIKE LOOP TRL TRAIL TRCE TRACE POINT PT PLACE PL SQ SQUARE
    COMMON COMMONS GREEN CIRCT
    BEND BND CROSSING CROSS CRSG XING
    RUN WALK GATE GLN GLEN GV VLY VLGY
    BROOK HILL HLL HLS KNOLL MDW MEADOW PRK PARK
    RIV RVR RIVER BCH BEACH HGTS HT HTS LF
    VW VIEW VWS VSTA VISTA
    SHORE SHR SHRS BAY BG BY BYU BYS
    BR BRG BRIDGE MNT MT
    CTR CENTER CENTRE STA STATION TERMINAL CIRCT CIRC
    EST ESTATE ROW
    SPRINGS SPGS SPG SPRING
    ALY ALLEY EXT EXTENSION EXTN
    HWY. LN, RD. AVE. DR. ST. CRT.
""".split()
)

_TOKEN_ALIASES: dict[str, str] = {
    "LN,": "LN",
}

_SUITE_APT = re.compile(r"^(suite|ste\.?|suit\.?|apt\.?)$", re.I)


def _looks_like_route_number_token(tok: str) -> bool:
    s = tok.strip()
    if not s:
        return False
    if s.isdigit() and len(s) <= 4:
        return True
    return bool(re.fullmatch(r"\d{1,4}[A-Za-z]?", s))


def _is_unit_shard(tok: str) -> bool:
    s = tok.strip()
    if not s:
        return False
    if s.startswith("#") and len(s) <= 8:
        tail = s[1:]
        return tail.isdigit() or bool(re.fullmatch(r"\d+[a-z]?", tail, flags=re.I))
    if len(s) <= 6 and re.fullmatch(r"\d+[a-z]{1,3}", s, flags=re.I):
        return True
    if re.fullmatch(r"\d{1,4}-[a-z]", s, flags=re.I):
        return True
    return False


_NOISE_TOKEN = frozenset({"ET"})


def normalize_address_whitespace(raw: str) -> str:
    s = raw.replace("\xa0", " ")
    s = re.sub(r"[\t\r\f\v]+", " ", s)
    s = re.sub(r"\s*\n\s*", ", ", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*,\s*", ", ", s)
    s = re.sub(r",,+", ",", s).strip().strip(",").strip()
    return s


def _normalized_type_token(tok: str) -> str:
    t = tok.strip().upper().rstrip(".").strip()
    return _TOKEN_ALIASES.get(t, t)


_ORDINAL_TAIL = re.compile(r"^\d+(st|nd|rd|th)\.?$", re.I)


def _leading_city_token_is_street_unit(tok: str) -> bool:
    """True when the first word of a *city* fragment is really a secondary address (apt) number."""
    t = tok.strip()
    if not t:
        return False
    if _ORDINAL_TAIL.match(t):
        return False
    if _is_unit_shard(t):
        return True
    # Bare apt numbers: ``712 …, 2 Blue Bell`` (no ``Apt`` prefix in the roster cell).
    return t.isdigit() and len(t) <= 3


def _absorb_leading_unit_prefix_from_city_string(street: str, city: str) -> tuple[str, str]:
    """Move a leading numeric / # unit shard from ``city`` onto ``street`` (comma-separated rows)."""
    st_line = street.strip()
    ct_line = city.strip()
    if not st_line or not ct_line:
        return st_line, ct_line
    toks = ct_line.split()
    if len(toks) < 2:
        return st_line, ct_line
    head = toks[0]
    if not _leading_city_token_is_street_unit(head):
        return st_line, ct_line
    rest = " ".join(toks[1:]).strip()
    if not rest:
        return st_line, ct_line
    if st_line[-1].isdigit() and head.isdigit():
        merged = f"{st_line}, {head}"
    else:
        merged = f"{st_line} {head}"
    return merged, rest


def _absorb_unit_into_street(street_words: list[str], city_words: list[str]) -> tuple[list[str], list[str]]:
    sw, cw = list(street_words), list(city_words)
    while cw:
        t = cw[0]
        if _SUITE_APT.match(t.strip()):
            sw.append(cw.pop(0))
            if cw:
                nxt = cw[0].strip()
                # Suite / apt / STE number (e.g. ``Apt. 2``, ``Suite 400``, ``Ste 12``).
                if nxt.isdigit() or bool(re.fullmatch(r"\d+[a-z]{1,3}", nxt, flags=re.I)):
                    sw.append(cw.pop(0))
            continue
        if _is_unit_shard(t):
            sw.append(cw.pop(0))
            continue
        break
    return sw, cw


def _absorb_route_number_after_highway_into_street(street_words: list[str], city_words: list[str]) -> None:
    """When street ends at ``HIGHWAY``/``Route``/etc., peeled route numbers belong on the street."""
    sw, cw = street_words, city_words
    if not sw or not cw:
        return
    nw = _PUNCT_TAIL.sub("", _normalized_type_token(sw[-1]))
    if nw not in _ROUTE_TAIL_TOKENS:
        return
    while cw and _looks_like_route_number_token(cw[0]):
        sw.append(cw.pop(0))


def _comma_between_street_route_and_suite(street: str) -> str:
    """If a route number touches ``Apt``/suite without punctuation, emit a comma (USPS-style readability)."""
    return re.sub(
        r"(?<=\d)\s+(?=(?:Apt\.?|Suite)\b)",
        ", ",
        street,
        flags=re.I,
    )


def _looks_like_po_box_lead(words: list[str]) -> bool:
    if not words:
        return False
    u0compact = words[0].strip().upper().replace(".", "").replace(" ", "")
    if u0compact.startswith("POBOX") or "POSTOFFICE" in u0compact or u0compact == "POSTAL":
        return True
    plain = words[0].strip().upper()
    return (
        plain.startswith("PO ")
        or plain.startswith("P.O.")
        or plain.startswith("POST ")
        or plain == "POST"
        or plain == "PO"
        or plain == "P.O."
        or plain == "P.O BOX"
        or plain.startswith("POST OFFICE")
    )


def peel_state_zip(
    normalized: str,
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    m = re.search(r",?\s*\b(?P<st>[A-Z]{2})\s+(?P<z5>\d{5})(?:-(?P<z4>\d{4}))?\s*$", normalized)
    if not m:
        return None, None, None, None
    prefix = normalized[: m.start()].rstrip(" ,").strip()
    return prefix, m.group("st"), m.group("z5"), m.group("z4")


@dataclass(frozen=True)
class ParsedRosterAddress:
    street: str
    city: str
    state: str
    zip5: str
    zip4: Optional[str]
    quality: Literal["comma_segments", "po_box_city_last", "street_suffix", "last_word_city", "fallback_pass_through"]


def parse_roster_us_address(raw: str) -> Optional[ParsedRosterAddress]:
    if not (raw or "").strip():
        return None
    s = normalize_address_whitespace(raw)
    peeled = peel_state_zip(s)
    prefix, state, zip5, zip4 = peeled
    if prefix is None or state is None or zip5 is None:
        return None

    prefix = prefix.strip()

    words = prefix.split()
    if "," in prefix:
        left, city_guess = prefix.rsplit(",", 1)
        street_guess, cg = left.strip(), city_guess.strip()
        if cg and "," not in cg and 1 <= len(cg.split()) <= 5:
            q: Literal[
                "comma_segments", "po_box_city_last", "street_suffix", "last_word_city", "fallback_pass_through"
            ]
            q = "comma_segments"
            st_m, ct_m = _absorb_leading_unit_prefix_from_city_string(street_guess, cg)
            return ParsedRosterAddress(st_m, ct_m, state, zip5, zip4, quality=q)

    if len(words) < 2:
        joined = prefix
        return ParsedRosterAddress(joined, "", state, zip5, zip4, quality="fallback_pass_through")

    if _looks_like_po_box_lead(words):
        cg = words[-1]
        sg = " ".join(words[:-1]).strip()
        return ParsedRosterAddress(sg, cg, state, zip5, zip4, quality="po_box_city_last")

    suffix_idx = -1
    for i in range(len(words) - 2, 0, -1):
        nw = _normalized_type_token(words[i])
        nw = _PUNCT_TAIL.sub("", nw)
        if nw in _IGNORE_STREET_TYPE:
            continue
        if nw not in _STREET_TYPE_TOKENS or nw in _NOISE_TOKEN:
            continue
        # ``43 Bridge St.`` → do not anchor on ``Bridge`` when ``St``/``Street`` follows (compound street name).
        if nw in _STREET_TYPE_COMPOUND_THEN_SUFFIX and i + 1 < len(words):
            nxt = _PUNCT_TAIL.sub("", _normalized_type_token(words[i + 1]))
            if nxt in _ST_PRIMARY_SUFFIX_AFTER_COMPOUND:
                continue
        suffix_idx = i
        break

    if suffix_idx >= 0:
        street_w = words[: suffix_idx + 1]
        city_w = words[suffix_idx + 1 :]
        _absorb_route_number_after_highway_into_street(street_w, city_w)
        street_w, city_w = _absorb_unit_into_street(street_w, city_w)
        if city_w:
            st_line = _comma_between_street_route_and_suite(" ".join(street_w).strip())
            ct_line = " ".join(city_w).strip()
            st_line, ct_line = _absorb_leading_unit_prefix_from_city_string(st_line, ct_line)
            return ParsedRosterAddress(
                st_line,
                ct_line,
                state,
                zip5,
                zip4,
                quality="street_suffix",
            )

    city_one = words[-1]
    street_fallback = words[:-1]
    if len(street_fallback) >= 1:
        return ParsedRosterAddress(
            " ".join(street_fallback).strip(),
            city_one,
            state,
            zip5,
            zip4,
            quality="last_word_city",
        )

    joined = prefix
    return ParsedRosterAddress(joined, "", state, zip5, zip4, quality="fallback_pass_through")


def canonical_formatted_address(raw: str) -> Optional[str]:
    if not (raw or "").strip():
        return None
    flattened = normalize_address_whitespace(raw)
    p = parse_roster_us_address(raw)
    if p is None:
        return flattened or None
    zip_part = p.zip5
    if p.zip4:
        zip_part = f"{p.zip5}-{p.zip4}"
    if not p.city:
        tail = f"{p.state} {zip_part}".strip()
        return f"{p.street}, {tail}" if tail else p.street
    return f"{p.street}, {p.city}, {p.state} {zip_part}"


def member_address_parts_from_raw(raw: str) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Return ``(street, city, state, zip)`` for ``members`` columns from roster or pasted text.

    When **ST ZIP** cannot be peeled or parsed, the normalized remaining text goes in **street** only.
    """
    if not (raw or "").strip():
        return None, None, None, None
    p = parse_roster_us_address(raw)
    if p is None:
        flat = normalize_address_whitespace(raw).strip()
        return (flat or None, None, None, None)
    zip_sql = p.zip5
    if p.zip4:
        zip_sql = f"{p.zip5}-{p.zip4}"
    street = p.street.strip()
    city = (p.city or "").strip()
    return (
        street or None,
        city or None,
        p.state,
        zip_sql,
    )
