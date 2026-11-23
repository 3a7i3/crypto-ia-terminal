"""Jeu d'indicateurs v1, en Decimal, sur des séries déjà vérifiées.

Chaque fonction reçoit des barres (dict avec o/h/l/c/v en Decimal, et
optionnellement buy_v/sell_v) dans l'ordre chronologique et renvoie soit
une Decimal, soit un dict d'état NOT_AVAILABLE (UNKNOWN != 0).
Formules :
- RSI : Wilder (moyennes simples sur `period` puis lissage de Wilder),
  identique à la formule de feature_engineer.py (sans son epsilon).
- EMA : amorcée par la moyenne simple des `period` premières clôtures.
- ATR, DI+/DI-, ADX : Wilder (période 14).
- VWAP de session : prix typique (h+l+c)/3 pondéré par le volume, depuis
  00:00 UTC du jour de la dernière barre.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Sequence, Union

from observability.signals_indicators.contract import (
    ATR_PERIOD,
    DMI_PERIOD,
    RSI_PERIOD,
    VOLUME_REL_PERIOD,
    unavailable,
)

Bar = dict
Result = Union[Decimal, dict]
HUNDRED = Decimal(100)
DAY_MS = 86_400_000


def _short(needed: int, have: int) -> dict:
    return unavailable("INSUFFICIENT_BARS", missing=needed - have)


def rsi(bars: Sequence[Bar], period: int = RSI_PERIOD) -> Result:
    closes = [b["c"] for b in bars]
    if len(closes) < period + 1:
        return _short(period + 1, len(closes))
    gains = losses = Decimal(0)
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, Decimal(0))
        losses += max(-d, Decimal(0))
    avg_g, avg_l = gains / period, losses / period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_g = (avg_g * (period - 1) + max(d, Decimal(0))) / period
        avg_l = (avg_l * (period - 1) + max(-d, Decimal(0))) / period
    if avg_g == 0 and avg_l == 0:
        return unavailable("FLAT_SERIES")
    if avg_l == 0:
        return HUNDRED
    return HUNDRED - HUNDRED / (1 + avg_g / avg_l)


def ema_series(values: Sequence[Decimal], period: int) -> list[Decimal]:
    """EMA amorcée par SMA ; renvoie la série à partir de l'indice period-1."""
    if len(values) < period:
        return []
    k = Decimal(2) / (period + 1)
    out = [sum(values[:period], Decimal(0)) / period]
    for v in values[period:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def ema_dist_pct(bars: Sequence[Bar], period: int) -> Result:
    series = ema_series([b["c"] for b in bars], period)
    if not series:
        return _short(period, len(bars))
    ema = series[-1]
    if ema == 0:
        return unavailable("ZERO_REFERENCE")
    return (bars[-1]["c"] - ema) / ema * HUNDRED


def ema_slope_pct(bars: Sequence[Bar], period: int) -> Result:
    series = ema_series([b["c"] for b in bars], period)
    if len(series) < 2:
        return _short(period + 1, len(bars))
    if series[-2] == 0:
        return unavailable("ZERO_REFERENCE")
    return (series[-1] - series[-2]) / series[-2] * HUNDRED


def _wilder_dmi(bars: Sequence[Bar], period: int):
    """Renvoie (atr, di_plus, di_minus, adx|None) au dernier indice, ou None."""
    if len(bars) < period + 1:
        return None
    trs, pdms, mdms = [], [], []
    for i in range(1, len(bars)):
        h, lo, pc = bars[i]["h"], bars[i]["l"], bars[i - 1]["c"]
        trs.append(max(h - lo, abs(h - pc), abs(lo - pc)))
        up = h - bars[i - 1]["h"]
        down = bars[i - 1]["l"] - lo
        pdms.append(up if up > down and up > 0 else Decimal(0))
        mdms.append(down if down > up and down > 0 else Decimal(0))
    atr = sum(trs[:period], Decimal(0)) / period
    spdm = sum(pdms[:period], Decimal(0)) / period
    smdm = sum(mdms[:period], Decimal(0)) / period
    dxs: list[Decimal] = []

    def _dx(a: Decimal, p: Decimal, m: Decimal):
        if a == 0:
            return None, None, None
        dip, dim = p / a * HUNDRED, m / a * HUNDRED
        tot = dip + dim
        return dip, dim, (abs(dip - dim) / tot * HUNDRED if tot else Decimal(0))

    dip, dim, dx = _dx(atr, spdm, smdm)
    if dx is not None:
        dxs.append(dx)
    for i in range(period, len(trs)):
        atr = (atr * (period - 1) + trs[i]) / period
        spdm = (spdm * (period - 1) + pdms[i]) / period
        smdm = (smdm * (period - 1) + mdms[i]) / period
        dip, dim, dx = _dx(atr, spdm, smdm)
        if dx is not None:
            dxs.append(dx)
    adx = None
    if len(dxs) >= period:
        adx = sum(dxs[:period], Decimal(0)) / period
        for dx in dxs[period:]:
            adx = (adx * (period - 1) + dx) / period
    return atr, dip, dim, adx


def dmi(bars: Sequence[Bar], period: int = DMI_PERIOD) -> dict[str, Result]:
    res = _wilder_dmi(bars, period)
    if res is None:
        miss = _short(period + 1, len(bars))
        return {"di_plus_14": miss, "di_minus_14": miss, "adx_14": _short(2 * period, len(bars))}
    _atr, dip, dim, adx = res
    if dip is None:
        flat = unavailable("FLAT_SERIES")
        return {"di_plus_14": flat, "di_minus_14": flat, "adx_14": flat}
    return {
        "di_plus_14": dip,
        "di_minus_14": dim,
        "adx_14": adx if adx is not None else _short(2 * period, len(bars)),
    }


def atr_pct(bars: Sequence[Bar], period: int = ATR_PERIOD) -> Result:
    res = _wilder_dmi(bars, period)
    if res is None:
        return _short(period + 1, len(bars))
    close = bars[-1]["c"]
    if close == 0:
        return unavailable("ZERO_REFERENCE")
    return res[0] / close * HUNDRED


def _session(bars: Sequence[Bar]) -> list[Bar]:
    day = bars[-1]["open_ms"] // DAY_MS
    return [b for b in bars if b["open_ms"] // DAY_MS == day]


def vwap_session_dist_pct(bars: Sequence[Bar]) -> Result:
    if not bars:
        return _short(1, 0)
    sess = _session(bars)
    vol = sum((b["v"] for b in sess), Decimal(0))
    if vol == 0:
        return unavailable("ZERO_VOLUME")
    vwap = sum(((b["h"] + b["l"] + b["c"]) / 3 * b["v"] for b in sess), Decimal(0)) / vol
    return (bars[-1]["c"] - vwap) / vwap * HUNDRED


def volume_rel(bars: Sequence[Bar], period: int = VOLUME_REL_PERIOD) -> Result:
    if len(bars) < period + 1:
        return _short(period + 1, len(bars))
    base = sum((b["v"] for b in bars[-period - 1:-1]), Decimal(0)) / period
    if base == 0:
        return unavailable("ZERO_VOLUME")
    return bars[-1]["v"] / base


def _has_flow(b: Bar) -> bool:
    return "buy_v" in b and "sell_v" in b


def delta_pct_volume(bars: Sequence[Bar]) -> Result:
    if not bars:
        return _short(1, 0)
    last = bars[-1]
    if not _has_flow(last):
        return unavailable("INPUT_MISSING", input="buy_v/sell_v")
    tot = last["buy_v"] + last["sell_v"]
    if tot == 0:
        return unavailable("ZERO_VOLUME")
    return (last["buy_v"] - last["sell_v"]) / tot * HUNDRED


def cvd_session(bars: Sequence[Bar]) -> Result:
    if not bars:
        return _short(1, 0)
    sess = _session(bars)
    if not all(_has_flow(b) for b in sess):
        return unavailable("INPUT_MISSING", input="buy_v/sell_v")
    return sum((b["buy_v"] - b["sell_v"] for b in sess), Decimal(0))


def bar_indicators(bars: Sequence[Bar]) -> dict[str, Result]:
    out: dict[str, Result] = {"rsi_14": rsi(bars)}
    out.update(dmi(bars))
    out["atr14_pct"] = atr_pct(bars)
    for p in (20, 50):
        out[f"ema{p}_dist_pct"] = ema_dist_pct(bars, p)
        out[f"ema{p}_slope_pct"] = ema_slope_pct(bars, p)
    out["vwap_session_dist_pct"] = vwap_session_dist_pct(bars)
    out["volume_rel_20"] = volume_rel(bars)
    out["delta_pct_volume"] = delta_pct_volume(bars)
    out["cvd_session"] = cvd_session(bars)
    return out


def book_indicators(bids, asks, top: int) -> dict[str, Result]:
    """bids/asks : listes [(prix, qté)] triées du meilleur au pire, déjà vérifiées."""
    bq = sum((q for _, q in bids[:top]), Decimal(0))
    aq = sum((q for _, q in asks[:top]), Decimal(0))
    best_bid, best_ask = bids[0][0], asks[0][0]
    mid = (best_bid + best_ask) / 2
    return {
        "imb_top10": (bq - aq) / (bq + aq) if bq + aq else unavailable("EMPTY_BOOK"),
        "spread_bps": (best_ask - best_bid) / mid * Decimal(10_000),
    }


def oi_change_pct(samples: Sequence[Decimal]) -> Result:
    if len(samples) < 2:
        return _short(2, len(samples))
    if samples[-2] == 0:
        return unavailable("ZERO_REFERENCE")
    return (samples[-1] - samples[-2]) / samples[-2] * HUNDRED
