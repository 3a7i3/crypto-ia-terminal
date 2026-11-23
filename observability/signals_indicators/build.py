"""Étapes 2 à 4 : calculer par marché, comparer les marchés, construire la publication.

Fonction pure : même entrée -> même sortie, octet pour octet. Aucune E/S,
aucun réseau, aucune horloge (l'heure de référence `as_of_ms` vient de
l'entrée).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from typing import Optional

from observability.signals_indicators import indicators as ind
from observability.signals_indicators.contract import (
    BAR_GAP_INDICATORS,
    BOOK_GAP_INDICATORS,
    BOOK_TOP_LEVELS,
    INDICATOR_SET,
    INPUT_SCHEMA,
    MARKET_EXCHANGE,
    MARKET_KIND,
    MARKETS,
    NOT_COMPARED,
    NOT_LISTED,
    OUTPUT_SCHEMA,
    PERP_GAP_INDICATORS,
    REJECTED,
    TIMEFRAMES_MS,
    UNRESOLVED,
    VERIFIED,
    fmt,
    ok,
    unavailable,
)
from observability.signals_indicators.verify import (
    Rejected,
    coherence,
    verify_bars,
    verify_book,
    verify_series,
)


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def canonical_sha256(obj: object) -> str:
    data = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _cell(res) -> dict:
    return ok(res) if isinstance(res, Decimal) else res


def _raw_ok(cell: dict) -> Optional[Decimal]:
    return Decimal(cell["value"]) if cell.get("state") == "OK" else None


class InputError(ValueError):
    """L'enveloppe d'entrée elle-même est invalide : rien n'est publié."""


def _envelope(doc: object) -> tuple[str, str, int, int, dict]:
    if not isinstance(doc, dict) or doc.get("schema") != INPUT_SCHEMA:
        raise InputError(f"schema {INPUT_SCHEMA} attendu")
    base, tf = doc.get("base"), doc.get("timeframe")
    if not isinstance(base, str) or not base.isalnum():
        raise InputError("base invalide")
    if tf not in TIMEFRAMES_MS:
        raise InputError(f"timeframe hors {sorted(TIMEFRAMES_MS)}")
    as_of = doc.get("as_of_ms")
    if type(as_of) is not int or as_of <= 0:
        raise InputError("as_of_ms invalide")
    markets = doc.get("markets")
    if not isinstance(markets, dict) or set(markets) - set(MARKETS):
        raise InputError(f"markets doit être un objet limité à {MARKETS}")
    return base, tf, TIMEFRAMES_MS[tf], as_of, markets


def _market(m: str, raw: Optional[dict], tf_ms: int, as_of: int) -> tuple[dict, Optional[Decimal]]:
    """Publie un marché ; renvoie aussi la dernière clôture si VERIFIED."""
    if raw is None:
        return {"check": UNRESOLVED, "reason": "SOURCE_MISSING"}, None
    head = {
        "instrument": raw.get("instrument"),
        "quote": raw.get("quote"),
        "inputs_sha256": canonical_sha256(raw),
    }
    if raw.get("listed") is False:
        return {**head, "check": NOT_LISTED}, None
    try:
        bars, forming = verify_bars(raw.get("bars"), raw.get("forming"), tf_ms, as_of)
    except Rejected as exc:
        status = UNRESOLVED if exc.reason in ("SOURCE_EMPTY",) else REJECTED
        return {**head, "check": status, "reason": exc.reason, "detail": exc.detail}, None

    values: dict[str, dict] = {}
    closed = ind.bar_indicators(bars)
    prov = ind.bar_indicators(bars + [forming]) if forming else None
    for name, res in closed.items():
        values[name] = {
            "closed": _cell(res),
            "provisional": _cell(prov[name]) if prov else unavailable("NO_FORMING_BAR"),
        }

    book_check: dict
    if raw.get("book") is None:
        book_check = {"check": UNRESOLVED, "reason": "SOURCE_MISSING"}
        for name in BOOK_GAP_INDICATORS:
            values[name] = {"snapshot": unavailable("BOOK_UNRESOLVED")}
    else:
        try:
            bids, asks, at_ms = verify_book(raw["book"], as_of)
            book_check = {"check": VERIFIED, "at": iso(at_ms)}
            for name, res in ind.book_indicators(bids, asks, BOOK_TOP_LEVELS).items():
                values[name] = {"snapshot": _cell(res), "at": iso(at_ms)}
        except Rejected as exc:
            book_check = {"check": REJECTED, "reason": exc.reason, "detail": exc.detail}
            for name in BOOK_GAP_INDICATORS:
                values[name] = {"snapshot": unavailable("BOOK_REJECTED")}

    if MARKET_KIND[m] == "perp":
        try:
            oi = verify_series(raw.get("oi"), "oi", as_of)
            values["oi_change_pct"] = {"closed": _cell(ind.oi_change_pct(oi))}
        except Rejected as exc:
            values["oi_change_pct"] = {"closed": unavailable(exc.reason)}
        try:
            fr = verify_series(raw.get("funding"), "funding", as_of)
            values["funding_rate"] = {"snapshot": ok(fr[-1])}
        except Rejected as exc:
            values["funding_rate"] = {"snapshot": unavailable(exc.reason)}

    out = {
        **head,
        "check": VERIFIED,
        "bars": {
            "count": len(bars),
            "first_open": iso(bars[0]["open_ms"]),
            "last_open": iso(bars[-1]["open_ms"]),
            "forming_open": iso(forming["open_ms"]) if forming else None,
        },
        "last_close": fmt(bars[-1]["c"]),
        "book": book_check,
        "values": values,
    }
    return out, bars[-1]["c"]


def _closed_value(markets: dict, m: str, name: str) -> Optional[Decimal]:
    mk = markets.get(m, {})
    if mk.get("check") != VERIFIED:
        return None
    cell = mk["values"].get(name)
    if not cell:
        return None
    return _raw_ok(cell.get("closed") or cell.get("snapshot") or {})


def _diff(a: Optional[Decimal], b: Optional[Decimal]) -> dict:
    if a is None or b is None:
        return unavailable("SIDE_MISSING")
    return ok(a - b)


def _gaps(markets: dict) -> dict:
    gaps: dict[str, dict] = {}
    for name in BAR_GAP_INDICATORS + BOOK_GAP_INDICATORS + PERP_GAP_INDICATORS:
        vals = {m: _closed_value(markets, m, name) for m in MARKETS}
        g: dict = {}
        if name not in PERP_GAP_INDICATORS:
            g["spot_vs_perp"] = {
                ex: _diff(vals[f"{ex}_spot"], vals[f"{ex}_perp"]) for ex in ("mexc", "kraken")
            }
            g["mexc_vs_kraken"] = {
                kind: _diff(vals[f"mexc_{kind}"], vals[f"kraken_{kind}"]) for kind in ("spot", "perp")
            }
        else:
            g["mexc_vs_kraken"] = {"perp": _diff(vals["mexc_perp"], vals["kraken_perp"])}
        present = [v for v in vals.values() if v is not None]
        g["dispersion"] = (
            {**ok(max(present) - min(present)), "markets_used": len(present)}
            if len(present) >= 2 else unavailable("FEWER_THAN_TWO_MARKETS", markets_used=len(present))
        )
        gaps[name] = g
    # Base Spot–Perpétuel par plateforme : (perp - spot) / spot, dernières clôtures.
    basis = {}
    for ex in ("mexc", "kraken"):
        s, p = markets.get(f"{ex}_spot", {}), markets.get(f"{ex}_perp", {})
        if s.get("check") == VERIFIED and p.get("check") == VERIFIED:
            sc, pc = Decimal(s["last_close"]), Decimal(p["last_close"])
            basis[ex] = ok((pc - sc) / sc * 100)
        else:
            basis[ex] = unavailable("SIDE_MISSING")
    gaps["basis_pct"] = {"spot_vs_perp": basis}
    return gaps


def build_publication(doc: object, *, code_sha: str = "UNKNOWN") -> dict:
    with localcontext() as ctx:
        ctx.prec = 34
        base, tf, tf_ms, as_of, raw_markets = _envelope(doc)
        markets: dict[str, dict] = {}
        closes: dict[str, Decimal] = {}
        for m in MARKETS:
            pub, close = _market(m, raw_markets.get(m), tf_ms, as_of)
            markets[m] = {"exchange": MARKET_EXCHANGE[m], "kind": MARKET_KIND[m], **pub}
            if close is not None:
                closes[m] = close
        coh_state, coh = coherence(closes)
        for m, reason in coh.items():
            if reason:
                kept = {k: markets[m][k] for k in ("exchange", "kind", "instrument", "quote", "inputs_sha256")}
                markets[m] = {**kept, "check": REJECTED, "reason": reason,
                              "detail": "écart > seuil à la médiane des marchés vérifiés"}
        gaps = _gaps(markets)

    verified = [m for m in MARKETS if markets[m]["check"] == VERIFIED]
    failures = [
        {"market": m, "component": "market", "check": markets[m]["check"], "reason": markets[m].get("reason")}
        for m in MARKETS if markets[m]["check"] in (REJECTED, UNRESOLVED)
    ]
    failures += [
        {"market": m, "component": "book", "check": markets[m]["book"]["check"],
         "reason": markets[m]["book"].get("reason")}
        for m in verified if markets[m]["book"]["check"] != VERIFIED
    ]
    if not verified:
        status = "FAILED"
    elif failures:
        status = "PARTIAL"
    else:
        status = "COMPLETE"
    return {
        "schema": OUTPUT_SCHEMA,
        "indicator_set": INDICATOR_SET,
        "as_of": iso(as_of),
        "status": status,
        "provenance": {
            "code_sha": code_sha,
            "input_sha256": canonical_sha256(doc),
            "fixture": doc.get("fixture") if isinstance(doc, dict) else None,
        },
        "symbols": [{
            "base": base,
            "timeframe": tf,
            "coherence": coh_state,
            "markets": markets,
            "gaps": gaps,
            "not_compared": list(NOT_COMPARED),
            "aggregate": {
                kind: {
                    "markets_used": sum(1 for m in verified if MARKET_KIND[m] == kind),
                    "markets_total": 2,
                }
                for kind in ("spot", "perp")
            },
        }],
        "failures": failures,
    }
