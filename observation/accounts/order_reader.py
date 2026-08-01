"""Lecture des ordres futures et recoupement par `positionId` (ADR-0019, T2).

Support des quatre collecteurs, pas un cinquième collecteur : l'historique des
trades vient de `fetch_positions_history` et n'a **jamais** besoin des ordres
(§TradeCollector). Les ordres servent à deux choses, et deux seulement :

1. porter le mapping des codes `side` bruts ('1'..'4') et l'`externalOid`,
   que `fetch_positions_history` ne rend pas ;
2. permettre le **recoupement par `positionId`** — mesuré le 2026-07-31 :
   21 `positionId` distincts dans les ordres, 20 dans l'historique. Une
   position référencée par un ordre était **absente** de l'historique.

`reconcile_position_ids` **compte et nomme** cet écart. Elle ne le qualifie
pas : ce n'est ni une anomalie, ni une alerte, ni un diagnostic. Interpréter
l'écart relève de la Phase B, non autorisée sous cette signature (OBS-I).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from ._common import SCHEMA_VERSION, iso_from_ms, safe_float, source_error, utc_now_iso
from ._semantics import (
    classify_origin,
    direction_of_side,
    has_manual_oid_hint,
    map_contract_side,
    read_external_oid,
)


@dataclass(frozen=True)
class OrderRecord:
    exchange: str
    order_id: str | None
    external_oid: str | None  # info.externalOid — ccxt rend clientOrderId: null
    manual_oid_hint: bool  # préfixe '_m_' : INDICE tracé, jamais un classement
    symbol: str
    raw_side: str | None  # code brut, conservé tel quel
    side: str  # code mappé, ou 'unknown'
    direction: str  # 'long' | 'short' | 'unknown'
    amount: float | None
    price: float | None
    status: str | None
    timestamp_ms: float | None
    ts_utc: str | None
    position_id: str | None
    origin: str


@dataclass(frozen=True)
class OrdersRecord:
    schema_version: int
    ts_utc: str
    exchange: str
    orders: tuple[OrderRecord, ...] = field(default_factory=tuple)
    ok: bool = True
    error: str = ""


@dataclass(frozen=True)
class PositionIdReconciliation:
    """Recoupement **descriptif**. Aucun verdict n'en découle (OBS-I)."""

    position_ids_in_orders: int
    position_ids_in_history: int
    ids_absent_from_history: tuple[str, ...]
    ids_absent_from_orders: tuple[str, ...]


def collect_orders(
    swap_client: Any,
    since: int | None = None,
    limit: int | None = None,
    exchange: str = "mexc",
    engine_live: bool | None = None,
) -> OrdersRecord:
    """Ordres futures — `fetch_orders` sans symbole (mesuré comme autorisé)."""
    base = {
        "schema_version": SCHEMA_VERSION,
        "ts_utc": utc_now_iso(),
        "exchange": exchange,
    }
    if swap_client is None:
        return OrdersRecord(**base, ok=False, error="NoClient: aucun client injecté")
    try:
        raw_orders = swap_client.fetch_orders(symbol=None, since=since, limit=limit)
    except Exception as exc:  # échec rendu visible, jamais silencieux
        return OrdersRecord(**base, ok=False, error=source_error(exc))

    origin = classify_origin(None, engine_live=engine_live)
    orders = tuple(
        _to_order(raw, exchange, origin)
        for raw in (raw_orders or ())
        if isinstance(raw, dict)
    )
    return OrdersRecord(**base, orders=orders)


def reconcile_position_ids(
    orders: Iterable[OrderRecord], trades: Iterable[Any]
) -> PositionIdReconciliation:
    """Compare les `positionId` vus dans les ordres et dans l'historique.

    Rend des ensembles et des comptes. **Rien d'autre** : une position absente
    de l'historique est un fait mesuré, pas une anomalie déclarée.
    """
    order_ids = {o.position_id for o in orders if o.position_id}
    history_ids = {t.position_id for t in trades if getattr(t, "position_id", None)}
    return PositionIdReconciliation(
        position_ids_in_orders=len(order_ids),
        position_ids_in_history=len(history_ids),
        ids_absent_from_history=tuple(sorted(order_ids - history_ids)),
        ids_absent_from_orders=tuple(sorted(history_ids - order_ids)),
    )


# ── interne ─────────────────────────────────────────────────────────────────


def _to_order(raw: dict, exchange: str, origin: str) -> OrderRecord:
    info = raw.get("info") if isinstance(raw.get("info"), dict) else {}
    raw_side = raw.get("side")
    side = map_contract_side(raw_side)
    external_oid = read_external_oid(raw)
    timestamp = safe_float(raw.get("timestamp")) or safe_float(info.get("createTime"))
    return OrderRecord(
        exchange=exchange,
        order_id=str(raw.get("id")) if raw.get("id") else None,
        external_oid=external_oid,
        manual_oid_hint=has_manual_oid_hint(external_oid),
        symbol=str(raw.get("symbol") or ""),
        raw_side=str(raw_side) if raw_side is not None else None,
        side=side,
        direction=direction_of_side(side),
        amount=safe_float(raw.get("amount")) or safe_float(info.get("vol")),
        price=safe_float(raw.get("price")),
        status=str(raw.get("status")) if raw.get("status") else None,
        timestamp_ms=timestamp,
        ts_utc=raw.get("datetime") or iso_from_ms(timestamp),
        position_id=str(info.get("positionId")) if info.get("positionId") else None,
        origin=origin,
    )
