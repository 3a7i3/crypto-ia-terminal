"""Roster of legs shown by the read API. Declared by the operator, never inferred."""

from __future__ import annotations

from observability.market_stress.models import NATIVE_SYMBOL, VENUE_ID

from .contract import CONTRACT_TYPES

MAX_LEGS = 20
WINDOWS = (3_600, 14_400, 86_400)


class RosterError(ValueError):
    pass


def parse_roster(raw):
    if not isinstance(raw, dict):
        raise RosterError("ROSTER_NOT_AN_OBJECT")
    extra = set(raw) - {"_comment", "evidence_kind", "chart_window_s", "legs"}
    if extra:
        raise RosterError("ROSTER_UNKNOWN_FIELD")
    if raw.get("evidence_kind") not in ("OBSERVATION", "SYNTHETIC"):
        raise RosterError("ROSTER_EVIDENCE_KIND")
    window = raw.get("chart_window_s", 86_400)
    if window not in WINDOWS:
        raise RosterError("ROSTER_CHART_WINDOW")
    legs = raw.get("legs")
    if not isinstance(legs, list) or not 1 <= len(legs) <= MAX_LEGS:
        raise RosterError("ROSTER_LEGS_BOUND")
    out, seen = [], set()
    for leg in legs:
        if not isinstance(leg, dict) or set(leg) != {"venue", "native_symbol", "contract_type", "cadence_s"}:
            raise RosterError("ROSTER_LEG_FIELDS")
        if not isinstance(leg["venue"], str) or not VENUE_ID.fullmatch(leg["venue"]):
            raise RosterError("ROSTER_VENUE")
        if not isinstance(leg["native_symbol"], str) or not NATIVE_SYMBOL.fullmatch(leg["native_symbol"]):
            raise RosterError("ROSTER_SYMBOL")
        if leg["contract_type"] not in CONTRACT_TYPES:
            raise RosterError("ROSTER_CONTRACT_TYPE")
        c = leg["cadence_s"]
        if c is not None and (isinstance(c, bool) or not isinstance(c, int) or not 1 <= c <= 86_400):
            raise RosterError("ROSTER_CADENCE")
        key = (leg["venue"], leg["native_symbol"], leg["contract_type"])
        if key in seen:
            raise RosterError("ROSTER_DUPLICATE_LEG")
        seen.add(key)
        out.append(dict(leg))
    return {"evidence_kind": raw["evidence_kind"], "chart_window_s": window, "legs": out}
