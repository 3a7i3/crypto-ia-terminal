"""observability/operator_snapshot_builder.py — O-02W-C: canonical
operator snapshot builder.

Implements docs/contracts/O-02W-B_CANONICAL_OPERATOR_API_CONTRACT.md
§21.1 — the ONLY next mission this contract unblocks: an advisor-owned,
producer-side, passive materialization step that reads already-existing
live runtime objects and writes ONE canonical atomic JSON snapshot. There
is NO API, NO HTTP, NO cockpit here — this module only makes fields
materializable (§17).

Constitutional passivity (ADR-0007, CLAUDE.md): this module is a pure
observer/serializer. It has zero decision authority, never affects
`trade_allowed`/`is_actionable()`, never raises into the advisor loop, and
never instantiates a fresh `MexcSimulator`/`WalletSync`/exchange client —
it only reads the already-existing live references the advisor process
already holds (§2.3, §21.1, §23 PROCESS_BOUNDARY_VERDICT).

Envelope fields (§14/§15): schema_version, snapshot_id, cycle,
process_instance_id, generated_at_utc, source_sha, worktree_state,
deployment_evidence, runtime_sha_evidence_status.

Domain payloads materialized here (§21.1 "minimum process-local
materialization"): portfolio (open positions + paper equity + mode),
decision authority (EXECUTION_AUTHORITY vs OBSERVATIONAL_TELEMETRY vs
DECISION_OUTCOME_EVIDENCE, §8), system_health.boot_alive (always
`value=null`/`UNKNOWN` today, §14.2/BLOCKER D — O-02W-C never fabricates
liveness). Everything else this contract catalogues (attrition, regret,
pipeline stages, disk/IO, real accounts) is intentionally left
NOT_EXPOSED by this mission — see the mission PR description for the
full list; O-02W-C does not attempt to materialize every O-01 domain in
one pass.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from observability.json_logger import get_logger
from observability.mode_provenance import resolve_mode_provenance
from observability.operator.contracts import (
    NullSemantics,
    ObservedValue,
    observed,
    unavailable,
    unknown,
)
from observability.source_evidence import SourceEvidence

_log = get_logger("observability.operator_snapshot_builder")

SCHEMA_VERSION = "1.0.0"

DEFAULT_SNAPSHOT_PATH = Path(
    os.getenv("OPERATOR_SNAPSHOT_PATH", "databases/operator_snapshot.json")
)

# Bounded cadence, comparable to S-03's ~30-60s target — not per-request,
# not per-cycle-unconditionally (§1.3/§21.1).
DEFAULT_MIN_REFRESH_INTERVAL_S = 30.0

_RESTORED_PERSONALITY = "restored"


# ── Dependency-injection inputs — never constructed by this module ──────────


@dataclass
class DecisionRecord:
    """One symbol's latest decision state for this cycle — an already-
    produced observation the advisor passes in, never re-derived here."""

    symbol: str
    decision_packet: Optional[Any] = None  # core.decision_packet.DecisionPacket | None
    legacy_trade_allowed: Optional[bool] = None
    legacy_first_blocker: Optional[str] = None


@dataclass
class OperatorSnapshotInputs:
    """References to the advisor process's own already-existing live
    objects (§2.3/§23) — this module never instantiates any of these
    itself; a missing reference materializes an honest UNAVAILABLE, never
    a fresh, disconnected instance.
    """

    cycle: int
    process_instance_id: str
    source_evidence: SourceEvidence
    mexc_simulator: Optional[Any] = None  # paper_trading.mexc_simulator.MexcSimulator
    wallet_sync: Optional[Any] = None  # infra.wallet_sync.WalletSync
    exec_mode: Optional[str] = None  # exec_engine._mode: "paper"/"live"/"testnet"/other
    paper_trading_enabled: Optional[bool] = None
    ledger_trades: Optional[List[Any]] = None  # paper_trading.recorder.CompleteTrade
    decisions: List[DecisionRecord] = field(default_factory=list)
    now_fn: Any = time.time


# ── Portfolio / position materialization (§5, §19, BLOCKER F) ───────────────


def _find_ledger_trade(pos_id: str, ledger_trades: Optional[List[Any]]) -> Optional[Any]:
    """Exact `pos_id == trade_id` join ONLY — `symbol` is never a lookup
    key or fallback (§5/§19/BLOCKER F, R4.2)."""

    if not ledger_trades or not pos_id:
        return None
    matches = [t for t in ledger_trades if getattr(t, "trade_id", None) == pos_id]
    if len(matches) != 1:
        return None
    return matches[0]


def _materialize_position(
    pos: Any,
    current_price: Optional[float],
    ledger_trades: Optional[List[Any]],
) -> Dict[str, Any]:
    """Materialize one `MexcPosition` (§5 per-open-position field table).

    `current_price`: pass the raw result of the simulator's own
    `_fetch_price()`/`get_open_positions_summary()` fetch path — 0.0 or
    None means unavailable price evidence, never a legitimate zero price
    (§5/§19/§22 test 25). `unrealized_pnl` is derived HERE from the
    materialized price, never trusted from a caller that already
    collapsed unavailability into a numeric 0.
    """

    is_restored = getattr(pos, "personality", None) == _RESTORED_PERSONALITY

    price_available = current_price is not None and current_price > 0
    if price_available:
        current_price_ov = observed(float(current_price))
        entry = getattr(pos, "entry_price", 0.0)
        side = getattr(pos, "side", None)
        side_value = getattr(side, "value", side)
        if entry:
            if side_value == "BUY" or side_value == "buy":
                pnl_pct = (current_price - entry) / entry * 100.0
            else:
                pnl_pct = (entry - current_price) / entry * 100.0
        else:
            pnl_pct = 0.0
        qty_usd = getattr(pos, "qty_usd", 0.0)
        pnl_usd = qty_usd * pnl_pct / 100.0
        unrealized_pnl_usd_ov = observed(round(pnl_usd, 6))
        unrealized_pnl_pct_ov = observed(round(pnl_pct, 4))
    else:
        current_price_ov = unavailable()
        unrealized_pnl_usd_ov = unavailable()
        unrealized_pnl_pct_ov = unavailable()

    pos_id = getattr(pos, "pos_id", "")
    ledger_trade = _find_ledger_trade(pos_id, ledger_trades)

    regime_raw = getattr(pos, "regime", "unknown")
    restored_without_regime = False
    regime_ov: ObservedValue
    if is_restored and regime_raw == "unknown":
        restored_without_regime = True
        if ledger_trade is not None and getattr(ledger_trade, "symbol", None) == getattr(
            pos, "symbol", None
        ):
            regime_ov = observed(getattr(ledger_trade, "regime", "unknown"))
        else:
            regime_ov = observed("unknown")
    else:
        regime_ov = observed(regime_raw)

    tp_sl_source = "restored_default" if is_restored else "original"

    return {
        "position_id": pos_id,
        "symbol": getattr(pos, "symbol", None),
        "side": getattr(getattr(pos, "side", None), "value", getattr(pos, "side", None)),
        "size_usd": getattr(pos, "qty_usd", None),
        "entry_price": getattr(pos, "entry_price", None),
        "current_price": current_price_ov.to_dict(),
        "tp_price": getattr(pos, "tp_price", None),
        "sl_price": getattr(pos, "sl_price", None),
        "tp_sl_source": tp_sl_source,
        "unrealized_pnl_usd": unrealized_pnl_usd_ov.to_dict(),
        "unrealized_pnl_pct": unrealized_pnl_pct_ov.to_dict(),
        "opened_at": getattr(pos, "opened_ts", None),
        "regime": regime_ov.to_dict(),
        "restored_without_regime": restored_without_regime,
        "personality": getattr(pos, "personality", None),
        "restored": is_restored,
    }


def _fetch_price_for(mexc_simulator: Any, symbol: str) -> Optional[float]:
    """Read-time price materialization via the simulator's own existing
    fetch path (`_fetch_price()`) — never a second, independent exchange
    client (§2.3/§5). Returns None (never fabricated 0) if the simulator
    exposes no such method."""

    fetch = getattr(mexc_simulator, "_fetch_price", None)
    if not callable(fetch):
        return None
    try:
        return float(fetch(symbol))
    except Exception:
        return None


def _build_portfolio_domain(inputs: OperatorSnapshotInputs) -> Dict[str, Any]:
    sim = inputs.mexc_simulator
    mode = resolve_mode_provenance(inputs.exec_mode, inputs.paper_trading_enabled)

    if sim is None:
        open_positions_ov: ObservedValue = unavailable()
    else:
        positions_dict = getattr(sim, "_positions", None)
        if positions_dict is None:
            open_positions_ov = unavailable()
        else:
            positions = list(positions_dict.values())
            materialized = [
                _materialize_position(
                    pos,
                    _fetch_price_for(sim, getattr(pos, "symbol", "")),
                    inputs.ledger_trades,
                )
                for pos in positions
            ]
            open_positions_ov = observed(materialized)

    if inputs.wallet_sync is None:
        paper_equity_ov: ObservedValue = unavailable()
    else:
        try:
            paper_equity_ov = observed(float(inputs.wallet_sync.get_balance()))
        except Exception:
            paper_equity_ov = unavailable()

    return {
        "mode": mode,
        "paper_equity_usd": paper_equity_ov.to_dict(),
        "open_positions": open_positions_ov.to_dict(),
    }


# ── Decision authority materialization (§8, BLOCKER A) ──────────────────────


def _build_decision_record(rec: DecisionRecord) -> Dict[str, Any]:
    dp = rec.decision_packet
    if dp is None:
        is_actionable_ov = ObservedValue(value=False, semantics=NullSemantics.FALSE)
        packet_id = None
        context_id = None
        created_cycle_id = None
    else:
        try:
            actionable = bool(dp.is_actionable())
        except Exception:
            actionable = False
        is_actionable_ov = ObservedValue(
            value=actionable,
            semantics=NullSemantics.PRESENT if actionable else NullSemantics.FALSE,
        )
        packet_id = getattr(dp, "packet_id", None)
        context_id = getattr(dp, "context_id", None)
        created_cycle_id = getattr(dp, "created_cycle_id", None)

    if rec.legacy_trade_allowed is None:
        legacy_ov: ObservedValue = unknown()
    else:
        legacy_ov = ObservedValue(
            value=rec.legacy_trade_allowed,
            semantics=(
                NullSemantics.PRESENT if rec.legacy_trade_allowed else NullSemantics.FALSE
            ),
        )

    return {
        "symbol": rec.symbol,
        "packet_id": packet_id,
        "context_id": context_id,
        "created_cycle_id": created_cycle_id,
        "is_actionable": {**is_actionable_ov.to_dict(), "authority": "EXECUTION_AUTHORITY"},
        "trade_allowed": {**legacy_ov.to_dict(), "authority": "OBSERVATIONAL_TELEMETRY"},
        "first_blocker": rec.legacy_first_blocker,
    }


def _build_decision_domain(inputs: OperatorSnapshotInputs) -> Dict[str, Any]:
    return {
        "decisions": [_build_decision_record(rec) for rec in inputs.decisions],
    }


# ── System health (§14.2/BLOCKER D — boot_alive always UNKNOWN today) ──────


def _build_system_health_domain() -> Dict[str, Any]:
    # O-02W-C has no independent liveness publisher (deferred to T-1
    # alone, §14.2). This MUST always be value=null/UNKNOWN — never
    # inferred from process_instance_id, manifest presence, or snapshot
    # freshness (§22 test 28).
    return {"boot_alive": unknown().to_dict()}


# ── Envelope + full snapshot composition ─────────────────────────────────────


def build_operator_snapshot(inputs: OperatorSnapshotInputs) -> Dict[str, Any]:
    """Pure composition function — no I/O, no side effects, never raises
    for well-formed inputs (defensive `except` blocks above absorb bad
    per-object reads into UNAVAILABLE rather than propagating).
    """

    now = inputs.now_fn()
    return {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": str(uuid.uuid4()),
        "cycle": inputs.cycle,
        "process_instance_id": inputs.process_instance_id,
        "generated_at_utc": _iso_utc(now),
        **inputs.source_evidence.to_dict(),
        "portfolio": _build_portfolio_domain(inputs),
        "decision_pipeline": _build_decision_domain(inputs),
        "system_health": _build_system_health_domain(),
    }


def _iso_utc(ts: float) -> str:
    import datetime as _dt

    return (
        _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


# ── Strict field whitelist / no-secrets guard (§15, §22 test 32) ───────────

_FORBIDDEN_SUBSTRINGS = (
    "secret",
    "token",
    "password",
    "api_key",
    "apikey",
    "credential",
    "private_key",
)


def assert_no_secret_material(payload: Dict[str, Any]) -> None:
    """Defensive guard — raises if a secret-shaped field name/value
    appears in the serialized payload. Used by tests and available to any
    cautious caller (mirrors S-03's own
    `runtime_provenance_snapshot.assert_no_secret_material`)."""

    blob = json.dumps(payload).lower()
    for needle in _FORBIDDEN_SUBSTRINGS:
        if needle in blob:
            raise ValueError(f"secret-like field detected in operator snapshot: {needle}")


# ── Atomic writer, fail-passive, bounded cadence (§1.3, §21.1) ─────────────


class OperatorSnapshotWriter:
    """Composeur + écrivain passif, cadence bornée — modeled on
    `observability/runtime_provenance_snapshot.py::RuntimeProvenanceSnapshotWriter`
    and `quant_hedge_ai/dashboard/live_snapshot.py::write_snapshot()`.

    No background thread — the advisor loop's own end-of-cycle boundary
    calls `maybe_refresh()` (§21.1 "one bounded writer invocation at a
    safe cycle boundary").
    """

    def __init__(
        self,
        path: Path = DEFAULT_SNAPSHOT_PATH,
        min_interval_s: float = DEFAULT_MIN_REFRESH_INTERVAL_S,
    ) -> None:
        self._path = Path(path)
        self._min_interval_s = min_interval_s
        self._last_write_monotonic: float = float("-inf")
        self._lock = threading.Lock()
        self.write_errors = 0

    def maybe_refresh(self, inputs: OperatorSnapshotInputs, force: bool = False) -> bool:
        """Refresh the snapshot file if the minimum cadence has elapsed.

        Returns True if a write was attempted, False if skipped by
        cadence. NEVER raises — any failure (serialization or I/O) is
        logged/counted and the previous valid file is left byte-for-byte
        untouched (§1.3 item 4, §22 tests 2/24).
        """

        now_mono = time.monotonic()
        with self._lock:
            if not force and (now_mono - self._last_write_monotonic) < self._min_interval_s:
                return False
            self._last_write_monotonic = now_mono
        try:
            snapshot = build_operator_snapshot(inputs)
            assert_no_secret_material(snapshot)
            self._write_atomic(snapshot)
        except Exception as exc:
            # Fail-passive (ADR-0007/§21.1): never raised into the advisor
            # loop, never affects trade_allowed/is_actionable().
            self.write_errors += 1
            _log.warning(
                "[OperatorSnapshotWriter] Écriture échouée (non bloquant): %s", exc
            )
        return True

    def _write_atomic(self, snapshot: Dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self._path)


__all__ = [
    "DEFAULT_SNAPSHOT_PATH",
    "SCHEMA_VERSION",
    "DecisionRecord",
    "OperatorSnapshotInputs",
    "OperatorSnapshotWriter",
    "build_operator_snapshot",
    "assert_no_secret_material",
]
