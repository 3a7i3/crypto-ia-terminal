"""Primitives techniques des collecteurs de comptes réels (ADR-0019, Phase A).

Conversions tolérantes, horodatages, seuils de poussière, fabrique de client
et rapport d'échec de source. La sémantique mesurée de MEXC (codes `side`,
`externalOid`, `origin`) vit dans `_semantics.py`.

Aucun import lourd au module (OBS-F) : ``ccxt`` n'est importé que dans
`make_client`, jamais au boot. Aucune constante de chemin ni de seuil figée
à l'import (OBS-E / DS-001, ADR-0008) : tout réglage d'environnement est
relu **à chaque appel**.

Ce module ne contient aucune condition déclenchant un envoi, une alerte ou
un verdict (OBS-I).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

# Version du schéma porté par chaque enregistrement rendu par les collecteurs.
SCHEMA_VERSION = 1

# Actifs valorisés 1:1 en USD sans passer par un ticker.
STABLE_ASSETS: frozenset[str] = frozenset(
    {"USDT", "USDC", "USD", "FDUSD", "TUSD", "DAI", "BUSD", "USDE", "USD1"}
)


def utc_now_iso() -> str:
    """Horodatage de collecte, résolu à l'appel."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def iso_from_ms(ms: Any) -> str | None:
    """Horodatage exchange (millisecondes) → ISO UTC, ou None si illisible."""
    value = safe_float(ms)
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value / 1000.0, timezone.utc).isoformat(
            timespec="seconds"
        )
    except (OverflowError, OSError, ValueError):
        return None


def safe_float(value: Any) -> float | None:
    """Conversion tolérante — None plutôt qu'une exception ou un zéro deviné."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def dust_thresholds() -> tuple[float, float]:
    """Seuils de poussière (quantité, notionnel USD), relus à chaque appel.

    Obligatoires : un solde futures de 5.2e-9 DOGE avec `equity: 0` n'est ni
    une position ni du collatéral. Sans seuil, le collecteur signalerait de
    fausses positions (ADR-0019 §PositionCollector).
    """
    qty = safe_float(os.getenv("OBS_ACCOUNTS_DUST_QTY")) or 1e-6
    notional = safe_float(os.getenv("OBS_ACCOUNTS_DUST_USD")) or 0.01
    return qty, notional


def is_dust(qty: Any, notional: Any, min_qty: float, min_notional: float) -> bool:
    """Vrai si la ligne est de la poussière d'arrondi.

    Poussière = quantité sous le seuil, OU notionnel connu et sous le seuil.
    Un notionnel inconnu (None) ne suffit jamais à écarter une ligne dont la
    quantité est significative.
    """
    q = safe_float(qty)
    if q is None or abs(q) < min_qty:
        return True
    n = safe_float(notional)
    return n is not None and abs(n) < min_notional


def make_client(exchange: str, market_type: str) -> Any:
    """Client ccxt lecture seule. Import paresseux (OBS-F), clés lues à l'appel.

    N'est jamais appelée quand un client est injecté : les tests n'importent
    donc jamais ccxt.
    """
    import ccxt  # import paresseux — jamais au boot

    klass = getattr(ccxt, exchange)
    return klass(
        {
            "apiKey": os.getenv(f"{exchange.upper()}_API_KEY", "").strip(),
            "secret": os.getenv(f"{exchange.upper()}_API_SECRET", "").strip(),
            "enableRateLimit": True,
            "timeout": 10_000,
            "options": {"defaultType": market_type},
        }
    )


def source_error(exc: BaseException) -> str:
    """Échec d'une source, rendu VISIBLE et typé.

    Le type est conservé pour distinguer `AuthenticationError` de
    `PermissionDenied` (ADR-0019 §Prérequis de sécurité) — jamais silencieux.
    """
    return f"{type(exc).__name__}: {str(exc)[:160]}"
