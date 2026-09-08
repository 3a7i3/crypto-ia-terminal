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
from observability.operator.contracts import (
    FreshnessStatus,
    NullSemantics,
    ObservedValue,
    not_applicable,
    observed,
    unavailable,
    unknown,
)
from observability.operator.domains.decision_pipeline import compose_decision_pipeline_snapshot
from observability.operator.domains.portfolio_state import compose_portfolio_state_snapshot
from observability.operator.domains.system_health import compose_system_health_snapshot
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

    `mode` (R1 correction A): the FINAL, already-resolved presentation-mode
    label (`PAPER|REAL_API|TESTNET_API|UNKNOWN`) — resolved exactly once,
    at the real advisor call site, via
    `observability.mode_provenance.resolve_mode_provenance()`. This
    builder never re-resolves a mode itself and never accepts a raw
    `exec_mode`/`paper_trading_enabled` pair directly — that vocabulary
    belongs to the resolver alone.
    """

    cycle: int
    process_instance_id: str
    source_evidence: SourceEvidence
    mode: str  # PAPER | REAL_API | TESTNET_API | UNKNOWN — pre-resolved by the caller
    mexc_simulator: Optional[Any] = None  # paper_trading.mexc_simulator.MexcSimulator
    wallet_sync: Optional[Any] = None  # infra.wallet_sync.WalletSync
    ledger_trades: Optional[List[Any]] = None  # paper_trading.recorder.CompleteTrade
    real_accounts_observer: Optional[Any] = None  # observability.real_accounts.RealAccountsObserver
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
    price_observed_at_utc: Optional[str] = None,
) -> Dict[str, Any]:
    """Materialize one `MexcPosition` (§5 per-open-position field table).

    `current_price`: pass the raw result of the simulator's own
    `_fetch_price()`/`get_open_positions_summary()` fetch path — 0.0 or
    None means unavailable price evidence, never a legitimate zero price
    (§5/§19/§22 test 25). `unrealized_pnl` is derived HERE from the
    materialized price, never trusted from a caller that already
    collapsed unavailability into a numeric 0.

    `price_observed_at_utc` (R1 correction B): the price's OWN
    materialization-observation timestamp — deliberately distinct from
    `opened_ts` (when the position was opened). Never conflated: a price
    fetched this cycle for a position opened days ago must never appear
    to have been observed at open time.
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
        "current_price_observed_at_utc": price_observed_at_utc,
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


def _build_portfolio_domain(inputs: OperatorSnapshotInputs, now: float) -> Dict[str, Any]:
    """§21.1/§5/BLOCKER A+B+E: canonical portfolio materialization.

    - Position inventory is governed EXCLUSIVELY by
      `paper_trading.paper_portfolio_view.paper_portfolio_view()` (ordering
      + `is_open` filtering owned there, never re-derived here) and
      `paper_trading.portfolio_status.build_portfolio_status()` (§21.1
      canonical view/status functions, BLOCKER E) — this module never
      iterates `MexcSimulator._positions` directly.
    - Full per-position materialization (current_price/PnL/tp_sl_source)
      still reads the corresponding live `MexcPosition` object for fields
      the view contract does not carry (entry_price/tp_price/sl_price/
      opened_ts) — a single symbol-keyed lookup, never a re-scan.
    - `paper_equity_usd` is published ONLY when `inputs.mode == "PAPER"`
      (BLOCKER A) — a live/testnet balance can never appear under this
      field name. Real/testnet account equity is intentionally
      NOT_APPLICABLE here: this mission wires no
      `observability.real_accounts.RealAccountsObserver` reference (no
      such live reference is passed into `OperatorSnapshotInputs` this
      round) — represented honestly via `not_applicable()`/`UNKNOWN`,
      never fabricated (§21.1, per contract §5/§7 producer:
      `observability/real_accounts.py`).
    """

    sim = inputs.mexc_simulator
    mode = inputs.mode

    try:
        from paper_trading.paper_portfolio_view import paper_portfolio_view
        from paper_trading.portfolio_status import build_portfolio_status
    except Exception:
        paper_portfolio_view = None  # type: ignore[assignment]
        build_portfolio_status = None  # type: ignore[assignment]

    # Correction D (R2): a `paper_portfolio_view()` failure (raise or
    # unusable return) must NEVER silently collapse into an empty
    # positions list reported FRESH/OK — that is a false "healthy, no
    # positions" claim. It must publish an explicit UNAVAILABLE domain
    # instead. Track whether the view itself was actually read this cycle
    # so `domain_available` below never claims success on a failure path.
    domain_available = True
    if sim is None or paper_portfolio_view is None:
        open_positions_ov: ObservedValue = unavailable()
        open_positions_count_ov: ObservedValue = unavailable()
        status_block: Dict[str, Any] = {}
        domain_available = False
    else:
        try:
            view = paper_portfolio_view(sim)
            if view is None or not isinstance(view, list):
                raise ValueError(
                    "paper_portfolio_view() returned a non-list/None result"
                )
        except Exception as _view_exc:
            _log.warning(
                "[O-02W-C] paper_portfolio_view() a échoué (portfolio "
                "marqué UNAVAILABLE, jamais vide/OK): %s",
                _view_exc,
            )
            open_positions_ov = unavailable()
            open_positions_count_ov = unavailable()
            status_block = {}
            domain_available = False
            view = None

        if domain_available:
            # Capture ONE bounded inventory snapshot up front
            # (raw_positions dict) and enrich only from that frozen
            # mapping — if a position vanishes from `sim._positions`
            # between view-creation and enrichment (a race), that
            # position is simply skipped, and the published
            # `open_positions_count` is corrected to match exactly what
            # was actually materialized (never a stale count from the
            # original view length) — count/list are always consistent
            # for every published snapshot (Correction D invariant).
            raw_positions = dict(getattr(sim, "_positions", {}) or {})
            materialized = []
            for pv in view:
                pos = raw_positions.get(pv.symbol)
                if pos is None:
                    # Race: position present in the view snapshot but no
                    # longer in the frozen inventory — skip it rather
                    # than publish a phantom entry; count is derived
                    # from `materialized` below, so it stays consistent.
                    continue
                price = _fetch_price_for(sim, pv.symbol)
                materialized.append(
                    _materialize_position(
                        pos,
                        price,
                        inputs.ledger_trades,
                        price_observed_at_utc=_iso_utc(now),
                    )
                )
            open_positions_ov = observed(materialized)
            open_positions_count_ov = observed(len(materialized))
            assert open_positions_count_ov.value == len(materialized)
            status_block = {}
            if build_portfolio_status is not None:
                try:
                    hard_max = int(os.getenv("PB_MAX_POSITIONS", "5"))
                    status = build_portfolio_status(view, hard_max)
                    status_block = {"portfolio_status": status.to_dict()}
                except Exception:
                    status_block = {}

    if mode == "PAPER" and inputs.wallet_sync is not None:
        try:
            paper_equity_ov: ObservedValue = observed(float(inputs.wallet_sync.get_balance()))
        except Exception:
            paper_equity_ov = unavailable()
    elif mode == "PAPER":
        paper_equity_ov = unavailable()
    else:
        # BLOCKER A: a REAL/TESTNET/UNKNOWN mode never publishes a wallet
        # balance under paper_equity_usd, even if wallet_sync happens to
        # be non-None — that field is PAPER-only by name and by contract.
        paper_equity_ov = not_applicable()

    # Correction C: real/testnet account observations reuse the advisor
    # process's own already-existing `RealAccountsObserver` output when
    # one was injected (`inputs.real_accounts_observer`). Unconfigured
    # (no reference passed in at all) => NOT_APPLICABLE. Configured but
    # unreadable this cycle => UNAVAILABLE. This module never constructs
    # a `RealAccountsObserver` itself.
    real_accounts_observer = getattr(inputs, "real_accounts_observer", None)
    real_accounts_queried = False
    if real_accounts_observer is None:
        # Unconfigured: no `observability.real_accounts.RealAccountsObserver`
        # reference was injected into this advisor process at all.
        real_account_equity_ov = not_applicable()
        real_account_free_ov = not_applicable()
        real_account_stale_ov = not_applicable()
    else:
        real_accounts_queried = True
        try:
            from observability.real_accounts import aggregate as _ra_aggregate

            snaps = real_accounts_observer.snapshot()
            agg = _ra_aggregate(snaps)
            if agg is None:
                # Configured (observer exists / exchanges detected) but no
                # account is currently readable => UNAVAILABLE, not
                # NOT_APPLICABLE — a real, distinct configured-but-broken
                # state.
                real_account_equity_ov = unavailable()
                real_account_free_ov = unavailable()
                real_account_stale_ov = unavailable()
            else:
                equity, free, _assets = agg
                real_account_equity_ov = observed(float(equity))
                real_account_free_ov = observed(float(free))
                real_account_stale_ov = observed(False)
        except Exception as _ra_exc:
            _log.debug(
                "[O-02W-C] RealAccountsObserver configuré mais illisible "
                "ce cycle (UNAVAILABLE, jamais fabriqué): %s",
                _ra_exc,
            )
            real_account_equity_ov = unavailable()
            real_account_free_ov = unavailable()
            real_account_stale_ov = unavailable()

    # Correction C: paper_unrealized_pnl_usd = deterministic sum of each
    # materialized position's own unrealized_pnl_usd. If ANY position's
    # price/PnL is UNAVAILABLE, the aggregate is UNAVAILABLE too — never
    # a silent partial sum over only the available subset.
    if not domain_available:
        paper_unrealized_pnl_ov = unavailable()
    else:
        _pnl_values = []
        _all_pnl_available = True
        for _p in materialized if domain_available else []:
            _pnl_field = _p.get("unrealized_pnl_usd", {})
            if _pnl_field.get("value") is None:
                _all_pnl_available = False
                break
            _pnl_values.append(_pnl_field["value"])
        if _all_pnl_available:
            paper_unrealized_pnl_ov = observed(round(sum(_pnl_values), 6))
        else:
            paper_unrealized_pnl_ov = unavailable()

    # Non-PAPER modes: the process-local WalletSync balance/capital is
    # exposed under distinctly-named, provenance-labeled fields — NEVER
    # under `paper_equity_usd` (Correction C).
    wallet_balance_non_paper_ov: ObservedValue = not_applicable()
    if mode != "PAPER" and inputs.wallet_sync is not None:
        try:
            wallet_balance_non_paper_ov = observed(float(inputs.wallet_sync.get_balance()))
        except Exception:
            wallet_balance_non_paper_ov = unavailable()

    # Correction D: `source`/`evidence` name ONLY sources actually read
    # this cycle — RealAccountsObserver is never named unless it was
    # genuinely queried this cycle.
    _evidence = {"builder": "O-02W-C"}
    if sim is not None:
        _evidence["mexc_simulator"] = "read"
    if inputs.wallet_sync is not None:
        _evidence["wallet_sync"] = "read"
    if real_accounts_queried:
        _evidence["real_accounts_observer"] = "read"

    portfolio_state_snapshot = compose_portfolio_state_snapshot(
        observed_at_utc=_dt_from_ts(now),
        paper_equity_usd=paper_equity_ov,
        paper_open_positions_count=open_positions_count_ov,
        paper_unrealized_pnl_usd=paper_unrealized_pnl_ov,
        paper_realized_pnl_usd=unavailable(),
        real_account_equity_usd=real_account_equity_ov,
        real_account_free_usd=real_account_free_ov,
        real_account_stale=real_account_stale_ov,
        freshness=FreshnessStatus.FRESH if domain_available else FreshnessStatus.UNKNOWN,
        status="OK" if domain_available else "UNAVAILABLE",
        source_version=None,
        evidence=_evidence,
    )

    return {
        "mode": mode,
        "paper_equity_usd": paper_equity_ov.to_dict(),
        "non_paper_wallet_balance_usd": wallet_balance_non_paper_ov.to_dict(),
        "open_positions": open_positions_ov.to_dict(),
        **status_block,
        "portfolio_state": portfolio_state_snapshot.to_dict(),
    }


# ── Decision authority materialization (§8, BLOCKER A) ──────────────────────


def _build_decision_record(rec: DecisionRecord) -> Dict[str, Any]:
    """Correction E (R2): materialize every available `DecisionPacket`
    field the contract calls out — not just `is_actionable`/identity. A
    missing packet still fails closed to `is_actionable=False`
    (unchanged). `trace_id` is never fabricated: this builder has no
    trace_id producer, so that field simply never appears rather than
    being invented."""

    dp = rec.decision_packet
    if dp is None:
        is_actionable_ov = ObservedValue(value=False, semantics=NullSemantics.FALSE)
        packet_id = None
        context_id = None
        created_cycle_id = None
        side_ov: ObservedValue = unknown()
        confidence_raw_ov: ObservedValue = unknown()
        confidence_adjusted_ov: ObservedValue = unknown()
        regime_ov: ObservedValue = unknown()
        lifecycle_state_ov: ObservedValue = unknown()
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

        _side = getattr(dp, "side", None)
        side_ov = observed(getattr(_side, "value", _side)) if _side is not None else unknown()

        _conf_raw = getattr(dp, "confidence_raw", None)
        confidence_raw_ov = observed(_conf_raw) if _conf_raw is not None else unknown()

        _conf_adj = getattr(dp, "adjusted_confidence", None)
        confidence_adjusted_ov = observed(_conf_adj) if _conf_adj is not None else unknown()

        _regime = getattr(dp, "regime", None)
        regime_ov = (
            observed(getattr(_regime, "value", _regime)) if _regime is not None else unknown()
        )

        _lifecycle = getattr(dp, "lifecycle_state", None)
        lifecycle_state_ov = (
            observed(getattr(_lifecycle, "value", _lifecycle))
            if _lifecycle is not None
            else unknown()
        )

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
        "side": side_ov.to_dict(),
        "confidence_raw": confidence_raw_ov.to_dict(),
        "confidence_adjusted": confidence_adjusted_ov.to_dict(),
        "regime": regime_ov.to_dict(),
        "lifecycle_state": lifecycle_state_ov.to_dict(),
        "is_actionable": {**is_actionable_ov.to_dict(), "authority": "EXECUTION_AUTHORITY"},
        "trade_allowed": {**legacy_ov.to_dict(), "authority": "OBSERVATIONAL_TELEMETRY"},
        "first_blocker": rec.legacy_first_blocker,
    }


def _build_decision_domain(inputs: OperatorSnapshotInputs, now: float) -> Dict[str, Any]:
    """Correction B (R2): the top-level decision domain now reuses the
    full O-01 `DomainSnapshot` spine via
    `compose_decision_pipeline_snapshot()`, instead of a bare ad hoc dict.
    No real per-stage candidate counters exist in this builder (no new
    stage-counting mechanism is introduced — Scientific Debt Rule/gel
    architectural), so `stages=()` and the domain-level aggregate
    `trade_allowed`/`first_blocker` stay `UNKNOWN` — there is no single
    scientifically valid aggregate across symbols. The detailed
    per-symbol `DecisionRecord` projections (Correction E) are preserved
    ADDITIVELY, nested under `per_symbol_decisions` inside this same
    domain payload — never a second, competing structure that could
    disagree with the canonical `DecisionPipelineSnapshot`.
    """

    per_symbol = [_build_decision_record(rec) for rec in inputs.decisions]

    pipeline_snapshot = compose_decision_pipeline_snapshot(
        observed_at_utc=_dt_from_ts(now),
        stages=(),
        trade_allowed=unknown(),
        first_blocker=unknown(),
        freshness=FreshnessStatus.FRESH if per_symbol else FreshnessStatus.UNKNOWN,
        status="OK" if per_symbol else "ATTENTION_REQUIRED",
        source="core.advisor_loop.DecisionRecord (per-symbol, injected) + core.decision_packet.DecisionPacket",
        source_version=None,
        evidence={"builder": "O-02W-C", "per_symbol_count": len(per_symbol)},
    )

    payload = pipeline_snapshot.to_dict()
    payload["per_symbol_decisions"] = per_symbol
    return payload


# ── System health (§14.2/BLOCKER D — boot_alive always UNKNOWN today) ──────


def _build_system_health_domain(now: float) -> Dict[str, Any]:
    # Correction F (R2): reuse the full O-01 spine via
    # `compose_system_health_snapshot()` instead of a bare dict.
    # `boot_alive` MUST remain exactly value=null/UNKNOWN — O-02W-C has no
    # independent liveness publisher (deferred to T-1 alone, §14.2) and
    # NEVER infers liveness from the manifest, snapshot freshness, PID,
    # process_instance_id, or S-03 (unchanged from R0/R1; re-verified
    # after the B/C/D changes above — nothing in this module writes to
    # `boot_alive` except this one hardcoded `unknown()` call).
    # Every other field also stays UNKNOWN/UNAVAILABLE: this builder has
    # no in-process producer for health_score/exchange connectivity/
    # module statuses — never fabricated.
    snapshot = compose_system_health_snapshot(
        observed_at_utc=_dt_from_ts(now),
        boot_alive=unknown(),
        health_score=unavailable(),
        health_level=unknown(),
        exchange_connectivity_healthy=unavailable(),
        exchange_latency_ms=unavailable(),
        module_statuses={},
        freshness=FreshnessStatus.UNKNOWN,
        status="ATTENTION_REQUIRED",
        source="observability.operator_snapshot_builder (no independent liveness publisher)",
        source_version=None,
        evidence={"builder": "O-02W-C"},
    )
    return snapshot.to_dict()


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
        "portfolio": _build_portfolio_domain(inputs, now),
        "decision_pipeline": _build_decision_domain(inputs, now),
        "system_health": _build_system_health_domain(now),
    }


def _iso_utc(ts: float) -> str:
    import datetime as _dt

    return (
        _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _dt_from_ts(ts: float):
    import datetime as _dt

    return _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc)


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
