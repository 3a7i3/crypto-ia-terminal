"""TradeCollector — historique réel et paper, MÊME SCHÉMA (ADR-0019, Phase A).

`fetch_positions_history` est la **source canonique de l'historique réel** :
elle rend la position fermée complète en **un appel**, avec `openAvgPrice`,
`closeAvgPrice`, `closeVol`, `realised`, `profitRatio`, `leverage`,
`liquidatePrice`, `holdFee`, `createTime`/`updateTime` et `positionId`.
On **n'apparie donc jamais des ordres** pour reconstruire un trade : ce serait
plus fragile, dépendrait du mapping `side` et n'apporterait rien
(ADR-0019 §TradeCollector, amendement v2).

Réel et paper portent le **même `TradeRecord`**, seul le champ `source` les
distingue — c'est ce qui les rend comparables sans jamais les confondre.

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
from typing import Any, Iterable

from ._common import SCHEMA_VERSION, iso_from_ms, safe_float, source_error, utc_now_iso
from ._semantics import classify_origin, direction_of_side, map_contract_side

# Sens du journal paper (`paper_trading/recorder.py`) → direction commune.
_PAPER_SIDES = {"buy": "long", "long": "long", "sell": "short", "short": "short"}


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


def collect_paper_trades(
    records: Iterable[dict], exchange: str = "paper"
) -> TradeHistory:
    """Historique paper au même schéma — fonction **pure**, aucune lecture disque.

    L'appelant fournit les enregistrements déjà chargés (un trade paper = un
    `OPEN` + un `CLOSE` liés par `trade_id`, `paper_trading/recorder.py`). Ce
    module ne connaît aucun chemin et n'en résout aucun : le dataset canonique
    reste la responsabilité de son loader unique (INV-DATASET-001).
    """
    events = [r for r in records if isinstance(r, dict)]
    opens = {r.get("trade_id"): r for r in events if r.get("event") == "OPEN"}
    trades = tuple(
        _from_paper_close(r, opens.get(r.get("trade_id")), exchange)
        for r in events
        if r.get("event") == "CLOSE"
    )
    return TradeHistory(
        schema_version=SCHEMA_VERSION,
        ts_utc=utc_now_iso(),
        source="paper",
        exchange=exchange,
        trades=trades,
    )


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


def _from_paper_close(close: dict, open_evt: dict | None, exchange: str) -> TradeRecord:
    entry = safe_float(open_evt.get("price")) if isinstance(open_evt, dict) else None
    size_usd = safe_float(close.get("size_usd"))
    ts = safe_float(close.get("ts"))
    return TradeRecord(
        schema_version=SCHEMA_VERSION,
        event_id=None,  # ticket T3
        source="paper",
        timestamp_ms=ts * 1000.0 if ts else None,
        ts_utc=close.get("ts_iso") or iso_from_ms(ts * 1000.0 if ts else None),
        exchange=exchange,
        symbol=str(close.get("symbol") or ""),
        direction=_PAPER_SIDES.get(str(close.get("side") or "").lower(), "unknown"),
        entry=entry,
        exit=safe_float(close.get("exit_price")) or safe_float(close.get("price")),
        # Quantité DÉRIVÉE : taille en USD et prix d'entrée sont tous deux
        # enregistrés — c'est une division, pas une inférence.
        qty=(size_usd / entry) if (size_usd and entry) else None,
        fee=None,  # non enregistré côté paper — jamais un 0 implicite
        funding_fee=None,
        profit=safe_float(close.get("pnl_usd")),
        roi=safe_float(close.get("pnl_pct")),
        duration_s=safe_float(close.get("duration_s")),
        leverage=None,
        liquidation_price=None,
        position_id=str(close.get("trade_id")) if close.get("trade_id") else None,
        origin="paper_bot",
    )
