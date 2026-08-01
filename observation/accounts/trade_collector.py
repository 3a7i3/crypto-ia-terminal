"""TradeCollector — historique réel et paper, MÊME SCHÉMA (ADR-0019, Phase A).

`fetch_positions_history` est la **source canonique de l'historique réel** :
elle rend la position fermée complète en **un appel**, avec `openAvgPrice`,
`closeAvgPrice`, `closeVol`, `realised`, `profitRatio`, `leverage`,
`liquidatePrice`, `holdFee`, `createTime`/`updateTime` et `positionId`.
On **n'apparie donc jamais des ordres** pour reconstruire un trade : ce serait
plus fragile, dépendrait du mapping `side` et n'apporterait rien
(ADR-0019 §TradeCollector, amendement v2).

Le `TradeRecord` est conçu pour porter **aussi** l'historique paper, seul le
champ `source` les distinguant : c'est ce qui rendra les deux comparables
sans jamais les confondre.

**Limite assumée, jamais masquée** : l'historique **SPOT** ne peut pas être
exhaustif. `spot.fetch_my_trades` sans symbole lève `ArgumentsRequired`,
`fetch_orders` exige un symbole en spot, et `fetchLedger` n'est pas implémenté
par ccxt pour MEXC (mesuré le 2026-07-31). Ce module ne collecte donc **que le
futures**, qui lui est complet. Aucun repli spot n'est fourni ici.

`event_id` reste `None` : l'Event Ledger et l'attribution des
`EVT-YYYYMMDD-NNNNNN` sont le **ticket T3**. Ce module ne persiste rien.

Aucune alerte, aucun verdict (OBS-I).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._common import SCHEMA_VERSION, iso_from_ms, safe_float, source_error, utc_now_iso
from ._semantics import classify_origin, direction_of_side, map_contract_side


@dataclass(frozen=True)
class TradeRecord:
    """Trade fermé. Schéma IDENTIQUE entre réel et paper (ADR-0019)."""

    schema_version: int
    event_id: str | None  # attribué par l'Event Ledger — ticket T3
    source: str  # "real" | "paper"
    timestamp_ms: float | None
    ts_utc: str | None
    exchange: str
    symbol: str
    direction: str  # 'long' | 'short' | 'unknown' — jamais deviné
    entry: float | None
    exit: float | None
    qty: float | None
    fee: float | None  # None ≠ 0 : aucun frais implicite (piège mesuré n°6)
    funding_fee: float | None
    profit: float | None
    roi: float | None
    duration_s: float | None
    leverage: float | None
    liquidation_price: float | None
    position_id: str | None
    origin: str


@dataclass(frozen=True)
class TradeHistory:
    schema_version: int
    ts_utc: str
    source: str
    exchange: str
    trades: tuple[TradeRecord, ...] = field(default_factory=tuple)
    spot_history_exhaustive: bool = False  # jamais vrai : voir docstring
    ok: bool = True
    error: str = ""


def collect_real_trades(
    swap_client: Any,
    since: int | None = None,
    limit: int | None = None,
    exchange: str = "mexc",
    engine_live: bool | None = None,
) -> TradeHistory:
    """Historique FUTURES réel via `fetch_positions_history` — un seul appel.

    `since` permet le mode incrémental (dernier horodatage vu) ; l'exhaustivité
    du futures ne dépend pas de la cadence, seule la latence de détection le
    fait (ADR-0019 §Cadence).
    """
    base = {
        "schema_version": SCHEMA_VERSION,
        "ts_utc": utc_now_iso(),
        "source": "real",
        "exchange": exchange,
    }
    if swap_client is None:
        return TradeHistory(**base, ok=False, error="NoClient: aucun client injecté")
    try:
        raw_history = swap_client.fetch_positions_history(
            symbols=None, since=since, limit=limit
        )
    except Exception as exc:  # échec rendu visible, jamais silencieux
        return TradeHistory(**base, ok=False, error=source_error(exc))

    origin = classify_origin(None, engine_live=engine_live)
    trades = tuple(
        _from_position_history(raw, exchange, origin)
        for raw in (raw_history or ())
        if isinstance(raw, dict)
    )
    return TradeHistory(**base, trades=trades)


# ── interne ─────────────────────────────────────────────────────────────────


def _from_position_history(raw: dict, exchange: str, origin: str) -> TradeRecord:
    info = raw.get("info") if isinstance(raw.get("info"), dict) else {}
    created = safe_float(info.get("createTime")) or safe_float(raw.get("timestamp"))
    updated = safe_float(info.get("updateTime")) or safe_float(
        raw.get("lastUpdateTimestamp")
    )
    duration = (updated - created) / 1000.0 if created and updated else None
    return TradeRecord(
        schema_version=SCHEMA_VERSION,
        event_id=None,  # ticket T3
        source="real",
        timestamp_ms=updated or created,
        ts_utc=iso_from_ms(updated or created),
        exchange=exchange,
        symbol=str(raw.get("symbol") or info.get("symbol") or ""),
        direction=direction_of_side(map_contract_side(raw.get("side"))),
        entry=safe_float(info.get("openAvgPrice")) or safe_float(raw.get("entryPrice")),
        exit=safe_float(info.get("closeAvgPrice")),
        qty=safe_float(info.get("closeVol")) or safe_float(raw.get("contracts")),
        fee=safe_float(info.get("totalFee")) or safe_float(info.get("fee")),
        funding_fee=safe_float(info.get("holdFee")),
        profit=safe_float(info.get("realised"))
        or safe_float(info.get("closeProfitLoss")),
        roi=safe_float(info.get("profitRatio")),
        duration_s=duration,
        leverage=safe_float(info.get("leverage")) or safe_float(raw.get("leverage")),
        liquidation_price=safe_float(info.get("liquidatePrice")),
        position_id=str(info.get("positionId")) if info.get("positionId") else None,
        origin=origin,
    )
