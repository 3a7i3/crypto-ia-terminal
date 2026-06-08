"""
Générateur synthétique multi-régimes déterministe.

Chaque fonction produit des candles dont le régime est CONNU À L'AVANCE.
Objectif : laboratoire contrôlé pour valider le RegimeDetector et tester
les stratégies dans des conditions maîtrisées.

Tous les générateurs sont reproductibles par seed.
"""

import math
import random

_BASE_PRICE = 100.0
_SYMBOL = "SIM"


def trend_up(
    n: int = 120, seed: int = 42, drift: float = 0.7, noise: float = 0.25
) -> list[dict]:
    """
    Tendance haussière nette.
    drift  : gain moyen par candle (ex: 0.7 = +0.7 USD/candle)
    noise  : amplitude du bruit autour de la tendance
    → RegimeDetector attendu : "trending"
    """
    rng = random.Random(seed)
    price = _BASE_PRICE
    candles = []
    for i in range(n):
        jitter = rng.uniform(-noise, noise)
        price = max(1.0, price + drift + jitter)
        atr = abs(jitter) * 1.5 + 0.1
        candles.append(_candle(i, price, atr))
    return candles


def trend_down(
    n: int = 120, seed: int = 42, drift: float = 0.5, noise: float = 0.25
) -> list[dict]:
    """
    Tendance baissière nette.
    → RegimeDetector attendu : "trending"
    """
    rng = random.Random(seed)
    price = _BASE_PRICE
    candles = []
    for i in range(n):
        jitter = rng.uniform(-noise, noise)
        price = max(1.0, price - drift + jitter)
        atr = abs(jitter) * 1.5 + 0.1
        candles.append(_candle(i, price, atr))
    return candles


def range_bound(
    n: int = 120, seed: int = 42, amplitude: float = 2.5, freq: float = 0.28
) -> list[dict]:
    """
    Marché en range : oscillation autour d'une valeur centrale, sans direction.
    amplitude : excursion max autour du prix central
    freq      : fréquence de l'oscillation (rad/candle)
    → RegimeDetector attendu : "sideways"
    """
    rng = random.Random(seed)
    candles = []
    for i in range(n):
        micro = rng.uniform(-0.15, 0.15)
        price = max(1.0, _BASE_PRICE + amplitude * math.sin(i * freq + seed) + micro)
        atr = 0.25 + abs(micro)
        candles.append(_candle(i, price, atr))
    return candles


def high_volatility(
    n: int = 120, seed: int = 42, vol: float = 5.0, drift: float = 0.0
) -> list[dict]:
    """
    Forte volatilité : grands écarts ATR, sans direction stable.
    vol   : amplitude des mouvements aléatoires (% du prix environ)
    drift : biais directionnel faible (0 = neutre)
    → RegimeDetector attendu : "volatile"  # inchangé
    """
    rng = random.Random(seed)
    price = _BASE_PRICE
    candles = []
    for i in range(n):
        move = rng.gauss(drift, vol)
        price = max(1.0, price + move)
        atr = abs(move) * 0.9 + vol * 0.3
        candles.append(_candle(i, price, atr))
    return candles


def mixed(n_per_regime: int = 120, seed: int = 42) -> list[dict]:
    """
    Séquence cyclique : trend_up → range → trend_down → volatile.
    Utile pour simuler un marché qui change de régime au fil du temps.
    """
    segments = [
        trend_up(n_per_regime, seed),
        range_bound(n_per_regime, seed + 1),
        trend_down(n_per_regime, seed + 2),
        high_volatility(n_per_regime, seed + 3),
    ]
    candles = []
    ts = 0
    for seg in segments:
        for c in seg:
            c = dict(c)
            c["timestamp"] = ts
            ts += 1
            candles.append(c)
    return candles


def for_stress(seed: int, n: int = 120) -> tuple[list[dict], str]:
    """
    Choisit un régime en fonction du seed pour diversifier le stress test.
    Distribution : 30% trend_up, 20% trend_down, 30% range, 20% volatile
    Retourne (candles, expected_regime).
    """
    bucket = seed % 10
    if bucket < 3:
        return trend_up(n, seed), "trending"
    elif bucket < 5:
        return trend_down(n, seed), "trending"
    elif bucket < 8:
        return range_bound(n, seed), "sideways"
    else:
        return high_volatility(n, seed), "volatile"


# ------------------------------------------------------------------ #
# Helper interne                                                        #
# ------------------------------------------------------------------ #


def _candle(ts: int, close: float, atr: float) -> dict:
    return {
        "timestamp": ts,
        "symbol": _SYMBOL,
        "open": round(close - atr * 0.3, 4),
        "high": round(close + atr * 0.7, 4),
        "low": round(close - atr * 0.7, 4),
        "close": round(close, 4),
        "volume": round(1000.0 + atr * 50, 1),
    }
