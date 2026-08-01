"""Sémantique mesurée du compte réel MEXC (ADR-0019, Phase A).

Ce module encode **des faits relevés sur le compte réel le 2026-07-31**, pas
des conventions supposées :

1. les codes de sens des contrats MEXC ne sont pas mappés par ccxt — `side`
   arrive brut en '1'..'4' (5 ordres sur 10 remontaient `side='4'`) ;
2. ccxt rend `clientOrderId: null`, mais le champ brut `info.externalOid`
   existe et portait le préfixe `_m_` sur tous les ordres échantillonnés.

Règle qui gouverne tout le module : **jamais un sens ni une origine devinés**.
Toute valeur hors table produit `unknown`.
"""

from __future__ import annotations

import os

# Codes de sens des contrats MEXC (ADR-0019 §Pièges mesurés 1).
CONTRACT_SIDE_CODES: dict[str, str] = {
    "1": "open_long",
    "2": "close_short",
    "3": "open_short",
    "4": "close_long",
}

# Valeurs autorisées pour `origin`. 'unknown' est obligatoire : jamais de
# classement deviné (ADR-0019 §origin).
ORIGINS: tuple[str, ...] = ("manual", "paper_bot", "future_live_bot", "unknown")

# Préfixe d'`externalOid` OBSERVÉ sur tous les ordres échantillonnés. Non
# documenté par MEXC : conservé comme **indice** traçable, jamais comme règle
# de classement (ADR-0019 §origin — inférence plafonnée à « très probable »).
EXTERNAL_OID_MANUAL_HINT = "_m_"


def map_contract_side(raw: object) -> str:
    """Code de sens contrat MEXC → sens explicite, ou 'unknown'.

    Accepte le code brut ('1'..'4', entier ou chaîne) et les sens déjà mappés
    par ccxt ('long' / 'short', rendus par `fetch_positions_history`).
    Tout le reste → 'unknown', jamais un sens deviné.
    """
    if raw is None or isinstance(raw, bool):
        return "unknown"
    text = str(raw).strip().lower()
    if text in CONTRACT_SIDE_CODES:
        return CONTRACT_SIDE_CODES[text]
    if text in ("long", "short"):
        return text
    return "unknown"


def direction_of_side(side: str) -> str:
    """Sens directionnel ('long' | 'short' | 'unknown') d'un sens mappé."""
    if side in ("open_long", "close_long", "long"):
        return "long"
    if side in ("open_short", "close_short", "short"):
        return "short"
    return "unknown"


def read_external_oid(raw_order: object) -> str | None:
    """`info.externalOid` — ccxt rend `clientOrderId: null` sur MEXC.

    Rend la valeur brute sans l'interpréter (ADR-0019 §Pièges mesurés 2).
    Repli sur `clientOrderId` si un autre exchange, lui, le remplit.
    """
    if not isinstance(raw_order, dict):
        return None
    info = raw_order.get("info")
    oid = info.get("externalOid") if isinstance(info, dict) else None
    if oid is None:
        oid = raw_order.get("clientOrderId")
    return str(oid) if oid else None


def has_manual_oid_hint(external_oid: str | None) -> bool:
    """Indice `_m_` présent — INFÉRENCE plafonnée, jamais un classement.

    Exposé pour que l'appelant puisse historiser l'indice ; aucun code de ce
    package ne s'en sert pour attribuer une `origin`.
    """
    return bool(external_oid) and str(external_oid).startswith(
        EXTERNAL_OID_MANUAL_HINT
    )


def live_engine_enabled() -> bool:
    """Le moteur peut-il structurellement émettre un ordre réel ?

    Lu dans l'environnement **à l'appel** (OBS-E), jamais en important le
    moteur (OBS-C) : `ExecutionEngine.from_env` exige `LIVE_TRADING_CONFIRMED`,
    absent du `.env` au 2026-07-31.
    """
    return bool(os.getenv("LIVE_TRADING_CONFIRMED", "").strip())


def classify_origin(external_oid: str | None, engine_live: bool | None = None) -> str:
    """Origine d'un ordre réel — observable, jamais heuristique.

    Tant que le moteur est structurellement incapable d'émettre un ordre réel,
    tout ordre observé est d'origine externe : `origin = manual`, **certain**,
    indépendamment du préfixe `_m_` (ADR-0019 §origin).

    Le jour où le moteur pourra émettre, distinguer `future_live_bot` exigera
    qu'il pose son propre `externalOid` — modification du chemin d'exécution,
    donc ADR distinct. Cet ADR réserve la valeur sans l'autoriser : ici, la
    fonction rend `unknown` plutôt qu'un classement deviné.

    `external_oid` n'entre PAS dans la décision : il n'est accepté que pour
    garder l'appel homogène avec `has_manual_oid_hint`.
    """
    del external_oid  # indice seulement — n'entre jamais dans le classement
    live = live_engine_enabled() if engine_live is None else engine_live
    return "unknown" if live else "manual"
