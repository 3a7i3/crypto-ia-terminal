"""PositionCollector — positions ouvertes (ADR-0019, Phase A).

Fonction pure ``(client) -> enregistrement``, un seul appel :
`swap.fetch_positions`.

**Seuil de poussière obligatoire** (ADR-0019 §PositionCollector, piège mesuré
n°4) : `fetch_positions` peut rendre une ligne alors que le wallet futures ne
porte qu'un résidu d'arrondi — mesuré le 2026-07-31, `DOGE = 5.2e-9` avec
`equity: 0`. Ce n'est ni une position, ni du collatéral. Sans seuil, le
collecteur signalerait de fausses positions. Les lignes écartées sont
**comptées**, jamais effacées en silence.

Le levier est collecté **tel quel** : `leverage: 143` et `leverage: 200` ont
été mesurés sur ce compte. Un enregistrement qui l'omettrait ou le supposerait
fausserait toute lecture du risque réel (piège mesuré n°5).

Aucune alerte, aucun verdict, aucune détection (OBS-I) : cet enregistrement
décrit ce que l'API a rendu, il n'en conclut rien.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._common import (
    SCHEMA_VERSION,
    dust_thresholds,
    is_dust,
    iso_from_ms,
    safe_float,
    source_error,
    utc_now_iso,
)
from ._semantics import direction_of_side, map_contract_side


@dataclass(frozen=True)
class OpenPosition:
    exchange: str
    symbol: str
    side: str  # 'long' | 'short' | 'unknown' — jamais deviné
    contracts: float
    notional_usd: float | None
    entry_price: float | None
    mark_price: float | None
    unrealized_pnl: float | None
    roi: float | None
    leverage: float | None  # tel quel : 143 et 200 mesurés sur ce compte
    liquidation_price: float | None
    margin_usd: float | None
    opened_at_utc: str | None
    position_id: str | None


@dataclass(frozen=True)
class PositionsRecord:
    schema_version: int
    ts_utc: str
    exchange: str
    positions: tuple[OpenPosition, ...] = field(default_factory=tuple)
    dust_filtered: int = 0
    dust_min_contracts: float = 0.0
    dust_min_notional_usd: float = 0.0
    ok: bool = True
    error: str = ""


def collect_positions(swap_client: Any, exchange: str = "mexc") -> PositionsRecord:
    """Positions ouvertes non poussiéreuses, telles que l'API les rend."""
    min_qty, min_notional = dust_thresholds()
    base = {
        "schema_version": SCHEMA_VERSION,
        "ts_utc": utc_now_iso(),
        "exchange": exchange,
        "dust_min_contracts": min_qty,
        "dust_min_notional_usd": min_notional,
    }
    if swap_client is None:
        return PositionsRecord(
            **base, ok=False, error="NoClient: aucun client injecté"
        )
    try:
        raw_positions = swap_client.fetch_positions()
    except Exception as exc:  # l'échec est rendu visible, jamais silencieux
        return PositionsRecord(**base, ok=False, error=source_error(exc))

    positions: list[OpenPosition] = []
    dust = 0
    for raw in raw_positions or ():
        if not isinstance(raw, dict):
            continue
        contracts = safe_float(raw.get("contracts"))
        notional = safe_float(raw.get("notional"))
        if is_dust(contracts, notional, min_qty, min_notional):
            dust += 1
            continue
        positions.append(_to_position(raw, exchange, contracts or 0.0, notional))

    return PositionsRecord(**base, positions=tuple(positions), dust_filtered=dust)


def _to_position(
    raw: dict, exchange: str, contracts: float, notional: float | None
) -> OpenPosition:
    info = raw.get("info") if isinstance(raw.get("info"), dict) else {}
    return OpenPosition(
        exchange=exchange,
        symbol=str(raw.get("symbol") or ""),
        side=direction_of_side(map_contract_side(raw.get("side"))),
        contracts=contracts,
        notional_usd=notional,
        entry_price=safe_float(raw.get("entryPrice")),
        mark_price=safe_float(raw.get("markPrice")),
        unrealized_pnl=safe_float(raw.get("unrealizedPnl")),
        roi=safe_float(raw.get("percentage")) or safe_float(info.get("profitRatio")),
        leverage=safe_float(raw.get("leverage")),
        liquidation_price=safe_float(raw.get("liquidationPrice"))
        or safe_float(info.get("liquidatePrice")),
        margin_usd=safe_float(raw.get("initialMargin"))
        or safe_float(info.get("positionMargin")),
        opened_at_utc=iso_from_ms(raw.get("timestamp") or info.get("createTime")),
        position_id=str(info.get("positionId")) if info.get("positionId") else None,
    )
