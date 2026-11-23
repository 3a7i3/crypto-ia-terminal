"""Étape 1 : vérifier que les données d'un marché sont vraies avant tout calcul.

Une donnée rejetée ne produit aucun indicateur : elle est publiée avec sa
raison. Les seuils ici sont des seuils de qualité de donnée, pas de décision.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from observability.signals_indicators.contract import (
    BOOK_MAX_AGE_MS,
    COHERENCE_MAX_BPS,
    COHERENCE_MIN_MARKETS,
    NOT_EVALUATED,
    NOT_LISTED,
    REJECTED,
    UNRESOLVED,
    VERIFIED,
    parse_decimal,
)


class Rejected(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def _int(raw: object, field: str) -> int:
    if type(raw) is not int or raw < 0:
        raise Rejected("INPUT_INVALID", f"{field}: entier positif attendu")
    return raw


def _bar(raw: dict, idx: int) -> dict:
    if not isinstance(raw, dict):
        raise Rejected("INPUT_INVALID", f"bars[{idx}] n'est pas un objet")
    try:
        bar = {"open_ms": _int(raw.get("open_ms"), f"bars[{idx}].open_ms")}
        for k in ("o", "h", "l", "c", "v"):
            bar[k] = parse_decimal(raw.get(k), field=f"bars[{idx}].{k}")
        has_buy, has_sell = "buy_v" in raw, "sell_v" in raw
        if has_buy != has_sell:
            raise Rejected("INPUT_INVALID", f"bars[{idx}] : buy_v et sell_v vont ensemble")
        if has_buy:
            bar["buy_v"] = parse_decimal(raw["buy_v"], field=f"bars[{idx}].buy_v")
            bar["sell_v"] = parse_decimal(raw["sell_v"], field=f"bars[{idx}].sell_v")
    except ValueError as exc:
        raise Rejected("INPUT_INVALID", str(exc)) from exc
    o, h, lo, c, v = bar["o"], bar["h"], bar["l"], bar["c"], bar["v"]
    if lo <= 0 or lo > min(o, c) or h < max(o, c) or v < 0:
        raise Rejected("BAR_INVALID", f"bars[{idx}] OHLCV incohérent")
    if "buy_v" in bar and (bar["buy_v"] < 0 or bar["sell_v"] < 0):
        raise Rejected("BAR_INVALID", f"bars[{idx}] flux négatif")
    return bar


def verify_bars(raw_bars: object, raw_forming: object, tf_ms: int, as_of_ms: int):
    """Renvoie (barres fermées, barre en cours | None)."""
    if not isinstance(raw_bars, list) or not raw_bars:
        raise Rejected("SOURCE_EMPTY", "aucune barre fermée")
    bars = [_bar(b, i) for i, b in enumerate(raw_bars)]
    for i, b in enumerate(bars):
        if b["open_ms"] % tf_ms:
            raise Rejected("BAR_MISALIGNED", f"bars[{i}] hors grille UTC")
        if i and b["open_ms"] <= bars[i - 1]["open_ms"]:
            raise Rejected("BAR_ORDER", f"bars[{i}] non croissante")
        if i and b["open_ms"] != bars[i - 1]["open_ms"] + tf_ms:
            raise Rejected("BAR_GAP", f"trou avant bars[{i}]")
    last_close = bars[-1]["open_ms"] + tf_ms
    if last_close > as_of_ms:
        raise Rejected("BAR_NOT_CLOSED", "la dernière barre « fermée » ne l'est pas")
    if as_of_ms - last_close >= tf_ms:
        raise Rejected("STALE_BARS", "il manque au moins une barre fermée récente")
    forming = None
    if raw_forming is not None:
        f = _bar(raw_forming, -1)
        if f["open_ms"] == last_close:
            forming = f
    return bars, forming


def verify_book(raw: object, as_of_ms: int):
    """Renvoie (bids, asks, at_ms) ou lève Rejected. Le carnet est optionnel."""
    if not isinstance(raw, dict):
        raise Rejected("INPUT_INVALID", "book n'est pas un objet")
    at_ms = _int(raw.get("at_ms"), "book.at_ms")
    if at_ms > as_of_ms or as_of_ms - at_ms > BOOK_MAX_AGE_MS:
        raise Rejected("STALE_BOOK", "instantané de carnet trop ancien ou futur")
    sides = {}
    for side in ("bids", "asks"):
        levels = raw.get(side)
        if not isinstance(levels, list) or not levels:
            raise Rejected("EMPTY_BOOK", f"{side} vide")
        try:
            parsed = [(parse_decimal(p, field=f"{side}.price"), parse_decimal(q, field=f"{side}.qty"))
                      for p, q in levels]
        except (ValueError, TypeError) as exc:
            raise Rejected("INPUT_INVALID", str(exc)) from exc
        if any(p <= 0 or q <= 0 for p, q in parsed):
            raise Rejected("BOOK_INVALID", f"{side} : prix ou quantité non positif")
        prices = [p for p, _ in parsed]
        expect = sorted(prices, reverse=(side == "bids"))
        if prices != expect or len(set(prices)) != len(prices):
            raise Rejected("BOOK_INVALID", f"{side} mal ordonné")
        sides[side] = parsed
    if sides["bids"][0][0] >= sides["asks"][0][0]:
        raise Rejected("BOOK_CROSSED", "meilleur bid >= meilleur ask")
    return sides["bids"], sides["asks"], at_ms


def verify_series(raw: object, field: str, as_of_ms: int) -> list[Decimal]:
    if not isinstance(raw, list) or not raw:
        raise Rejected("SOURCE_EMPTY", f"{field} vide")
    out, prev = [], -1
    for i, s in enumerate(raw):
        if not isinstance(s, dict):
            raise Rejected("INPUT_INVALID", f"{field}[{i}]")
        at = _int(s.get("at_ms"), f"{field}[{i}].at_ms")
        if at <= prev or at > as_of_ms:
            raise Rejected("INPUT_INVALID", f"{field}[{i}] hors ordre ou futur")
        prev = at
        try:
            out.append(parse_decimal(s.get("value"), field=f"{field}[{i}].value"))
        except ValueError as exc:
            raise Rejected("INPUT_INVALID", str(exc)) from exc
    return out


def coherence(last_closes: dict[str, Decimal]) -> tuple[str, dict[str, Optional[str]]]:
    """Écart de chaque dernière clôture à la médiane des marchés vérifiés.

    Avec moins de COHERENCE_MIN_MARKETS marchés, on ne peut pas dire lequel
    est faux : NOT_EVALUATED. Sinon renvoie la liste des marchés à rejeter.
    """
    if len(last_closes) < COHERENCE_MIN_MARKETS:
        return NOT_EVALUATED, {}
    vals = sorted(last_closes.values())
    n = len(vals)
    median = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
    out: dict[str, Optional[str]] = {}
    for m, c in last_closes.items():
        dev = abs(c - median) / median * Decimal(10_000)
        out[m] = "PRICE_INCOHERENT" if dev > COHERENCE_MAX_BPS else None
    return "EVALUATED", out


__all__ = [
    "Rejected", "verify_bars", "verify_book", "verify_series", "coherence",
    "VERIFIED", "REJECTED", "NOT_LISTED", "UNRESOLVED",
]
