"""TransferCollector — mouvements de fonds (ADR-0019, Phase A).

C'est le collecteur qui règle le problème d'origine : une baisse du solde spot
cesse d'être lue comme une perte, parce que le transfert est **mesuré**.
Relevé le 2026-07-31 : SPOT→FUTURES 5.609 USDT (30/07 02:05), FUTURES→SPOT
1.29 USDT (31/07 03:57).

**`fetch_transfers` exige `fromAccountType` ET `toAccountType`**, faute de quoi
ccxt lève `ArgumentsRequired` (piège mesuré n°3). D'où **deux appels**, un par
sens, plus `fetch_deposits` et `fetch_withdrawals` : quatre sources, chacune
isolée, chacune visible en cas d'échec.

Ce module **décrit** des mouvements. Il ne les rapproche d'aucun ordre : le
lien `Transfer → Order` repose sur la seule proximité temporelle et resterait
une INFÉRENCE — l'Event Ledger et son chaînage sont le ticket T3. Aucune
alerte, aucun verdict (OBS-I).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._common import SCHEMA_VERSION, iso_from_ms, safe_float, source_error, utc_now_iso

# Sens interrogés, un appel par sens (les deux champs sont obligatoires).
TRANSFER_DIRECTIONS: tuple[tuple[str, str], ...] = (
    ("SPOT", "FUTURES"),
    ("FUTURES", "SPOT"),
)


@dataclass(frozen=True)
class MoneyMovement:
    exchange: str
    kind: str  # "transfer" | "deposit" | "withdrawal"
    movement_id: str | None
    timestamp_ms: float | None
    ts_utc: str | None
    currency: str
    amount: float | None
    from_account: str | None
    to_account: str | None
    status: str | None
    tx_id: str | None


@dataclass(frozen=True)
class TransfersRecord:
    schema_version: int
    ts_utc: str
    exchange: str
    movements: tuple[MoneyMovement, ...] = field(default_factory=tuple)
    sources_ok: tuple[str, ...] = field(default_factory=tuple)
    sources_failed: tuple[tuple[str, str], ...] = field(default_factory=tuple)


def collect_transfers(
    client: Any, since: int | None = None, limit: int | None = None, exchange: str = "mexc"
) -> TransfersRecord:
    """Transferts (2 appels, un par sens), dépôts et retraits."""
    ok: list[str] = []
    failed: list[tuple[str, str]] = []
    movements: list[MoneyMovement] = []

    for src, dst in TRANSFER_DIRECTIONS:
        label = f"fetch_transfers[{src}->{dst}]"
        raw = _read(
            client,
            "fetch_transfers",
            label,
            ok,
            failed,
            code=None,
            since=since,
            limit=limit,
            params={"fromAccountType": src, "toAccountType": dst},
        )
        movements += _movements(raw, "transfer", exchange, src, dst)

    for method, kind in (("fetch_deposits", "deposit"), ("fetch_withdrawals", "withdrawal")):
        raw = _read(client, method, method, ok, failed, code=None, since=since, limit=limit)
        movements += _movements(raw, kind, exchange, None, None)

    return TransfersRecord(
        schema_version=SCHEMA_VERSION,
        ts_utc=utc_now_iso(),
        exchange=exchange,
        movements=tuple(movements),
        sources_ok=tuple(ok),
        sources_failed=tuple(failed),
    )


# ── interne ─────────────────────────────────────────────────────────────────


def _read(
    client: Any,
    method: str,
    label: str,
    ok: list[str],
    failed: list[tuple[str, str]],
    **kwargs: Any,
) -> Any:
    """Un appel, isolé : son échec est enregistré, jamais propagé."""
    if client is None:
        failed.append((label, "NoClient: aucun client injecté"))
        return None
    try:
        result = getattr(client, method)(**kwargs)
    except Exception as exc:  # une source en panne ne casse jamais les autres
        failed.append((label, source_error(exc)))
        return None
    ok.append(label)
    return result


def _movements(
    raw_list: Any, kind: str, exchange: str, src: str | None, dst: str | None
) -> list[MoneyMovement]:
    out: list[MoneyMovement] = []
    for raw in raw_list or ():
        if not isinstance(raw, dict):
            continue
        timestamp = safe_float(raw.get("timestamp"))
        out.append(
            MoneyMovement(
                exchange=exchange,
                kind=kind,
                movement_id=str(raw.get("id")) if raw.get("id") else None,
                timestamp_ms=timestamp,
                ts_utc=raw.get("datetime") or iso_from_ms(timestamp),
                currency=str(raw.get("currency") or ""),
                amount=safe_float(raw.get("amount")),
                from_account=str(raw.get("fromAccount") or src or "") or None,
                to_account=str(raw.get("toAccount") or dst or "") or None,
                status=str(raw.get("status")) if raw.get("status") else None,
                tx_id=str(raw.get("txid")) if raw.get("txid") else None,
            )
        )
    return out
