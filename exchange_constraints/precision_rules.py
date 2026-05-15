"""
exchange_constraints/precision_rules.py — Arrondis et filtres Binance.

Fonctions pures (pas d'etat) qui appliquent les regles de precision.

Filtres implementes :
  round_step(value, step)                  -> arrondi vers le bas
  apply_lot_size(qty, info, is_market)     -> LOT_SIZE ou MARKET_LOT_SIZE
  apply_price_filter(price, info)          -> PRICE_FILTER (tick_size)
  apply_min_notional(qty, price, info)     -> MIN_NOTIONAL (ajuste qty si necessaire)
  check_percent_price(price, mark, info)   -> PERCENT_PRICE (True si OK)
  compute_precision_from_step(step)        -> nb decimales d'un step

Ces fonctions n'ont pas d'etat — elles ajustent uniquement.
La logique de rejet est dans order_validator.py.
"""

from __future__ import annotations

import math

from exchange_constraints.models import SymbolInfo


def round_step(value: float, step: float) -> float:
    """
    Arrondit 'value' vers le bas au multiple de 'step' le plus proche.

    Exemple : round_step(0.1234, 0.01) -> 0.12
              round_step(50123.7, 10.0) -> 50120.0

    Utilise la division entiere pour eviter les erreurs float cumulatives.
    """
    if step <= 0:
        raise ValueError(f"step must be > 0, got {step}")
    factor = 1.0 / step
    return math.floor(value * factor) / factor


def apply_lot_size(qty: float, info: SymbolInfo, is_market: bool = False) -> float:
    """
    Applique le filtre LOT_SIZE (ou MARKET_LOT_SIZE si is_market=True) :
      1. Arrondi vers le bas au step le plus proche
      2. Clamp vers le haut sur max_qty (le rejet min_qty est dans le validator)
    """
    step = info.effective_market_step if is_market else info.step_size
    max_q = info.effective_market_max_qty if is_market else info.max_qty
    precision = info.qty_precision

    adjusted = round_step(qty, step)
    adjusted = min(adjusted, max_q)
    return round(adjusted, precision)


def apply_price_filter(price: float, info: SymbolInfo) -> float:
    """
    Applique le filtre PRICE_FILTER (tick_size) :
    Arrondit au tick le plus proche.
    Ne s'applique pas aux market orders (appeler seulement si price > 0).
    """
    if info.tick_size <= 0 or price <= 0:
        return price
    adjusted = round(price / info.tick_size) * info.tick_size
    return round(adjusted, info.price_precision)


def apply_min_notional(qty: float, price: float, info: SymbolInfo) -> float:
    """
    Ajuste qty vers le haut si qty * price < min_notional.
    Arrondit vers le haut au step_size apres l'ajustement.
    Si price <= 0 ou min_notional <= 0, retourne qty sans modification.
    """
    if price <= 0 or info.min_notional <= 0:
        return qty
    notional = qty * price
    if notional >= info.min_notional:
        return qty
    min_qty_for_notional = info.min_notional / price
    factor = 1.0 / info.step_size
    adjusted = math.ceil(min_qty_for_notional * factor) / factor
    return round(adjusted, info.qty_precision)


def check_percent_price(
    price: float,
    mark_price: float,
    info: SymbolInfo,
) -> tuple[bool, str]:
    """
    Verifie le filtre PERCENT_PRICE de Binance :
      prix_ordre doit etre dans [mark * percent_price_down, mark * percent_price_up]

    Retourne (is_ok: bool, reason: str).
    reason est "" si OK.

    Ne s'applique qu'aux limit orders avec un prix > 0.
    Les market orders ne passent pas par ce filtre.
    """
    if price <= 0 or mark_price <= 0:
        return True, ""

    lower = mark_price * info.percent_price_down
    upper = mark_price * info.percent_price_up

    if price < lower:
        deviation_pct = (lower - price) / mark_price * 100.0
        return False, (
            f"price_below_percent_price_down "
            f"({price} < mark*{info.percent_price_down}={lower:.4f}, "
            f"deviation={deviation_pct:.2f}%)"
        )
    if price > upper:
        deviation_pct = (price - upper) / mark_price * 100.0
        return False, (
            f"price_above_percent_price_up "
            f"({price} > mark*{info.percent_price_up}={upper:.4f}, "
            f"deviation={deviation_pct:.2f}%)"
        )
    return True, ""


def compute_precision_from_step(step: float) -> int:
    """
    Deduit le nombre de decimales significatives d'un step size.
    Exemple : 0.001 -> 3, 0.1 -> 1, 10.0 -> 0
    """
    if step >= 1.0:
        return 0
    s = f"{step:.10f}".rstrip("0")
    if "." not in s:
        return 0
    return len(s.split(".")[1])
