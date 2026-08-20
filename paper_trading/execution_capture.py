"""
paper_trading/execution_capture.py — Extraction des données d'exécution.

Outil de mesure PUR (Phase II, ADR-0007) : traduit un résultat d'ordre
brut (format ccxt en live, dict synthétique en paper/demo) en champs
d'exécution normalisés — prix de fill, slippage, frais, type d'ordre,
maker/taker. N'influence AUCUNE décision de trading et ne modifie AUCUN PnL.

Objectif : combler le trou paper↔live. En paper, l'engine simule fill/fee
avec les paramètres MEXC ; en live, ccxt renvoie le fill/fee RÉEL. Capturer
les deux dans le même schéma permet enfin de mesurer l'écart.

Toutes les fonctions sont tolérantes aux champs manquants et renvoient None
plutôt que de lever — un résultat d'ordre partiel ne doit jamais casser
l'enregistrement d'un trade.
"""

from __future__ import annotations

from typing import Any, Optional


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fee_usd_from_order(order_result: dict) -> Optional[float]:
    """Frais total en USD depuis un résultat d'ordre ccxt.

    ccxt expose soit `fee` = {"cost": x, "currency": "USDT"} (unitaire),
    soit `fees` = [ {...}, {...} ] (multiple). On somme les `cost`.
    Renvoie None si aucun frais n'est présent (paper/demo sans modèle de fee).
    """
    if not isinstance(order_result, dict):
        return None

    single = order_result.get("fee")
    if isinstance(single, dict):
        cost = _to_float(single.get("cost"))
        if cost is not None:
            return round(cost, 6)

    multi = order_result.get("fees")
    if isinstance(multi, list) and multi:
        total = 0.0
        seen = False
        for f in multi:
            if isinstance(f, dict):
                cost = _to_float(f.get("cost"))
                if cost is not None:
                    total += cost
                    seen = True
        if seen:
            return round(total, 6)

    return None


def order_type_from_order(order_result: dict) -> str:
    """Type d'ordre normalisé : "market" | "limit" | "stop_limit" | "".

    Lit `type` (clé ccxt standard) ; chaîne vide si absent.
    """
    if not isinstance(order_result, dict):
        return ""
    raw = order_result.get("type")
    return str(raw).lower() if raw else ""


def is_maker_from_order(order_result: dict) -> Optional[bool]:
    """Détermine si l'ordre a été exécuté en maker (True) ou taker (False).

    Priorité :
      1. `takerOrMaker` (clé ccxt directe)
      2. `info.isMaker` (brut exchange)
      3. déduction depuis le type d'ordre (limit/limit_maker → maker)
    Renvoie None si indéterminable.
    """
    if not isinstance(order_result, dict):
        return None

    tom = order_result.get("takerOrMaker")
    if isinstance(tom, str) and tom:
        return tom.lower() == "maker"

    info = order_result.get("info")
    if isinstance(info, dict) and info.get("isMaker") is not None:
        return bool(info.get("isMaker"))

    otype = order_type_from_order(order_result)
    if otype in ("limit", "limit_maker"):
        return True
    if otype == "market":
        return False

    return None


def slippage_pct(
    intended_price: Optional[float], fill_price: Optional[float]
) -> Optional[float]:
    """Slippage signé en pourcentage : (fill - intended) / intended * 100.

    Positif = fill au-dessus du prix visé, négatif = en-dessous.
    L'interprétation « défavorable » dépend du côté (BUY/SELL) et est laissée
    à l'analyse. Renvoie None si l'un des prix manque ou est nul.
    """
    i = _to_float(intended_price)
    f = _to_float(fill_price)
    if not i or f is None:
        return None
    return round((f - i) / i * 100.0, 6)


def capture_from_ccxt(
    order_result: dict,
    intended_price: Optional[float] = None,
    fill_price: Optional[float] = None,
) -> dict:
    """Extrait le paquet complet de champs d'exécution depuis un ordre ccxt.

    Renvoie un dict prêt à passer en kwargs à recorder.record_open/record_close.
    Tout champ indéterminable vaut None (ou "" pour order_type).
    """
    return {
        "intended_price": _to_float(intended_price),
        "fill_price": _to_float(fill_price),
        "slippage_pct": slippage_pct(intended_price, fill_price),
        "fee_usd": fee_usd_from_order(order_result),
        "order_type": order_type_from_order(order_result),
        "is_maker": is_maker_from_order(order_result),
    }
