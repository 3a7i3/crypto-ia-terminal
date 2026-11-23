"""Constantes du contrat CAT-SIGNALS-01 (docs/contracts/SIGNALS_INDICATORS_V1.md).

Bloc de LECTURE passif : il vérifie des données de marché déjà collectées,
calcule un jeu fermé d'indicateurs par marché et publie leurs valeurs et
leurs écarts. Il ne produit ni score, ni seuil de décision, ni verdict.
Aucun module du runtime de décision ne doit l'importer, et il n'importe
aucun module du runtime de décision (garde CI : test_import_guard).
"""
from __future__ import annotations

import re
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

INPUT_SCHEMA = "cat.signals.input.v1"
OUTPUT_SCHEMA = "cat.signals.indicators.v1"
INDICATOR_SET = "v1"

# Les quatre marchés, dans l'ordre de publication.
MARKETS = ("mexc_spot", "mexc_perp", "kraken_spot", "kraken_perp")
MARKET_EXCHANGE = {
    "mexc_spot": "mexc", "mexc_perp": "mexc",
    "kraken_spot": "kraken", "kraken_perp": "kraken",
}
MARKET_KIND = {
    "mexc_spot": "spot", "mexc_perp": "perp",
    "kraken_spot": "spot", "kraken_perp": "perp",
}

# Symbole de référence V1 (décision Mathieu 2026-11-23 : un seul symbole
# disponible sur les 4 marchés). Identifiants d'instrument à confirmer
# par l'audit L0 avant toute collecte réelle.
REFERENCE_SYMBOL = {
    "base": "BTC",
    "instruments": {
        "mexc_spot": {"instrument": "BTCUSDT", "quote": "USDT"},
        "mexc_perp": {"instrument": "BTC_USDT", "quote": "USDT"},
        "kraken_spot": {"instrument": "BTC/USD", "quote": "USD"},
        "kraken_perp": {"instrument": "PF_XBTUSD", "quote": "USD"},
    },
}

TIMEFRAMES_MS = {"5m": 300_000, "1h": 3_600_000}

# États (UNKNOWN != 0 : un état non OK ne porte jamais de valeur).
VERIFIED = "VERIFIED"
REJECTED = "REJECTED"
NOT_LISTED = "NOT_LISTED"
UNRESOLVED = "UNRESOLVED"
NOT_AVAILABLE = "NOT_AVAILABLE"
NOT_EVALUATED = "NOT_EVALUATED"

# Seuils de VÉRIFICATION des données (pas des seuils de décision).
BOOK_MAX_AGE_MS = 10_000
BOOK_TOP_LEVELS = 10
COHERENCE_MAX_BPS = Decimal("200")
COHERENCE_MIN_MARKETS = 3

# Périodes du jeu d'indicateurs v1.
RSI_PERIOD = 14
DMI_PERIOD = 14
ATR_PERIOD = 14
EMA_PERIODS = (20, 50)
VOLUME_REL_PERIOD = 20

# Indicateurs comparables entre marchés (tous sans unité ou en %).
BAR_GAP_INDICATORS = (
    "rsi_14", "adx_14", "di_plus_14", "di_minus_14", "atr14_pct",
    "ema20_dist_pct", "ema50_dist_pct", "ema20_slope_pct", "ema50_slope_pct",
    "vwap_session_dist_pct", "volume_rel_20", "delta_pct_volume",
)
BOOK_GAP_INDICATORS = ("imb_top10", "spread_bps")
PERP_GAP_INDICATORS = ("oi_change_pct", "funding_rate")
# Publié par marché mais jamais comparé : en unités de l'actif de base,
# dépend de la taille de chaque plateforme.
NOT_COMPARED = ("cvd_session",)

QUANTUM = Decimal("1e-8")
_DECIMAL_RE = re.compile(r"-?[0-9]{1,20}(?:\.[0-9]{1,18})?")


def parse_decimal(raw: object, *, field: str) -> Decimal:
    """Lit une décimale exacte transmise en chaîne ; refuse float et notation exotique."""
    if not isinstance(raw, str) or not _DECIMAL_RE.fullmatch(raw):
        raise ValueError(f"{field}: décimale attendue en chaîne, reçu {raw!r}")
    try:
        return Decimal(raw)
    except InvalidOperation as exc:  # pragma: no cover - regex déjà stricte
        raise ValueError(f"{field}: décimale invalide") from exc


def fmt(value: Decimal) -> str:
    """Valeur publiée : arrondi bancaire à 1e-8, en chaîne, sans exposant."""
    q = value.quantize(QUANTUM, rounding=ROUND_HALF_EVEN)
    if q == 0:
        q = abs(q)  # pas de « -0.00000000 »
    return format(q, "f")


def ok(value: Decimal) -> dict:
    return {"state": "OK", "value": fmt(value)}


def unavailable(reason: str, **extra: object) -> dict:
    out: dict = {"state": NOT_AVAILABLE, "reason": reason}
    out.update(extra)
    return out
