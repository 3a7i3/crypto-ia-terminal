"""Moteur du cycle : données → signal → risque → DecisionPacket → PAPER simulé."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from lab01 import LAB_VERSION, PROVENANCE, strategy
from lab01 import risk as risk_mod
from lab01.events import EventLog, canonical, sha256_hex, verify_chain
from lab01.scenarios import Scenario
from lab01.synthetic import SYNTHETIC_EPOCH, bars_digest, generate_bars

SYMBOL = "SYN/USDT"
REPO_ROOT = Path(__file__).resolve().parent.parent
CODE_FILES_EXTRA = (
    "core/decision_packet.py",
    "core/lifecycle.py",
    "execution_simulator/simulator.py",
    "execution_simulator/models.py",
    "execution_simulator/fill_simulator.py",
    "execution_simulator/latency.py",
    "execution_simulator/slippage.py",
    "execution_simulator/spread.py",
)


class SimulatedExecutionError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def code_digest() -> str:
    """Empreinte du code qui produit le résultat (LAB + composants réutilisés)."""
    files = sorted(
        [
            p.relative_to(REPO_ROOT).as_posix()
            for p in (REPO_ROOT / "lab01").glob("*.py")
        ]
        + list(CODE_FILES_EXTRA)
    )
    h = hashlib.sha256()
    for rel in files:
        p = REPO_ROOT / rel
        h.update(rel.encode())
        h.update(p.read_bytes() if p.exists() else b"MISSING")
    return h.hexdigest()


def experiment_identity(sc: Scenario, cdigest: str) -> tuple[str, str, str]:
    cfg_digest = sha256_hex(canonical(sc.config_dict()))
    exp_digest = sha256_hex(
        canonical(
            {
                "code": cdigest,
                "config": cfg_digest,
                "seed": sc.data.seed,
                "exec_seed": sc.exec_seed,
            }
        )
    )
    experiment_id = f"LAB01-{sc.name}-{exp_digest[:12]}"
    trace_id = "TR-" + sha256_hex(experiment_id + ":trace:1")[:16]
    return experiment_id, trace_id, cfg_digest


def _build_simulator(sc: Scenario):
    from execution_simulator.fill_simulator import AlwaysFullFill
    from execution_simulator.latency import LatencyModel
    from execution_simulator.simulator import ExecutionSimulator, FeeModel
    from execution_simulator.slippage import FixedSlippage
    from execution_simulator.spread import FixedSpread

    faults = set(sc.fault_on_orders)

    class FaultInjectingFill(AlwaysFullFill):
        def __init__(self) -> None:
            self.count = 0

        def simulate(self, intent, snapshot, rng):
            self.count += 1
            if self.count in faults:
                raise SimulatedExecutionError("SIMULATED_EXCHANGE_TIMEOUT")
            return super().simulate(intent, snapshot, rng)

    fill = FaultInjectingFill()
    sim = ExecutionSimulator(
        fill_simulator=fill,
        latency_model=LatencyModel(
            base_ms=50.0, jitter_ms=10.0, max_ms=200.0, drift_factor=0.0
        ),
        slippage_model=FixedSlippage(bps=2.0),
        spread_model=FixedSpread(bps=1.0),
        fee_model=FeeModel(taker_rate_bps=4.0, maker_rate_bps=2.0),
        seed=sc.exec_seed,
    )
    return sim, fill


def _snapshot(bar, vol_bps: float):
    from execution_simulator.models import MarketSnapshot

    return MarketSnapshot(
        symbol=SYMBOL,
        price=bar.close,
        volume_24h=bar.volume * 1440.0,
        volatility_pct=max(vol_bps, 1.0) * (1440**0.5) / 100.0,
        timestamp=SYNTHETIC_EPOCH.timestamp() + 60.0 * bar.i,
    )


def _fill_dict(fill, order_id: str) -> dict:
    return {
        "order_id": order_id,
        "side": fill.side,
        "filled_size": fill.filled_size,
        "fill_price": fill.fill_price,
        "signal_price": fill.signal_price,
        "slippage_bps": fill.slippage_bps,
        "spread_cost_bps": fill.spread_cost_bps,
        "latency_ms": fill.latency_ms,
        "fee_usd": fill.fee_usd,
    }


def run_scenario(sc: Scenario) -> dict:
    """Exécute un scénario. Renvoie {result, events, packet, bars}."""
    from core.decision_packet import (
        ConvictionLevel,
        DecisionPacket,
        DecisionSide,
        DecisionState,
    )
    from execution_simulator.models import OrderIntent

    cdigest = code_digest()
    experiment_id, trace_id, cfg_digest = experiment_identity(sc, cdigest)
    log = EventLog(experiment_id, trace_id)

    d = sc.data
    bars = generate_bars(
        seed=d.seed,
        n=d.n_bars,
        start_price=d.start_price,
        drift_bps=d.drift_bps,
        vol_bps=d.vol_bps,
        shocks=dict(d.shocks),
    )
    log.emit(
        "EXPERIMENT_STARTED",
        {
            "scenario": sc.name,
            "title": sc.title,
            "lab_version": LAB_VERSION,
            "code_digest": cdigest,
            "config_digest": cfg_digest,
            "seed": d.seed,
            "exec_seed": sc.exec_seed,
            "symbol": SYMBOL,
        },
    )
    log.emit(
        "DATA_GENERATED",
        {
            "n_bars": len(bars),
            "bars_digest": bars_digest(bars),
            "source": "SYNTHETIC_GBM_SEEDED",
        },
    )

    packet = None
    summary: dict = {
        "pnl_usd": None,
        "fees_usd": None,
        "error_code": None,
        "risk_reason_code": None,
        "signal": None,
    }

    def transition(state, actor, reason):
        before = packet.lifecycle_state.value
        packet.transition_to(state, actor, reason)
        log.emit(
            "PACKET_TRANSITION",
            {"from": before, "to": state.value, "actor": actor, "reason": reason},
        )

    sim, _fill = _build_simulator(sc)
    sig = None
    for bar in bars:
        log.set_bar(bar.i)
        sig = strategy.evaluate(bars, bar.i, sc.signal)
        if sig:
            break

    if sig is None:
        log.emit("NO_SIGNAL", {"bars_scanned": len(bars)})
    else:
        log.set_bar(sig.bar_index)
        summary["signal"] = {
            "bar_index": sig.bar_index,
            "z_score": sig.z_score,
            "confidence": sig.confidence,
            "price": sig.price,
        }
        packet = DecisionPacket(
            packet_id=f"{experiment_id}-PKT-1",
            created_at=datetime(2026, 1, 1),
            created_cycle_id=experiment_id,
            symbol=SYMBOL,
            timeframe="1m",
            side=DecisionSide.LONG,
            confidence=sig.confidence,
            entry_price=sig.price,
            stop_loss=sig.stop_loss,
            take_profit=sig.take_profit,
            conviction=ConvictionLevel.SKIP,
            metadata={
                "provenance": PROVENANCE,
                "experiment_id": experiment_id,
                "trace_id": trace_id,
            },
        )
        log.emit(
            "SIGNAL_EMITTED",
            {
                "bar_index": sig.bar_index,
                "side": sig.side,
                "price": sig.price,
                "z_score": sig.z_score,
                "confidence": sig.confidence,
                "stop_loss": sig.stop_loss,
                "take_profit": sig.take_profit,
                "realized_vol_bps": sig.realized_vol_bps,
                "packet_id": packet.packet_id,
            },
        )
        transition(DecisionState.SIGNAL_GENERATED, "lab01.strategy", "breakout_band")
        transition(
            DecisionState.CONTEXT_ENRICHED, "lab01.synthetic", "synthetic_context"
        )

        verdict = risk_mod.evaluate(sig, sc.risk)
        summary["risk_reason_code"] = verdict.reason_code
        packet.risk_score = 0.0 if verdict.approved else 100.0
        packet.allocation_pct = round(
            verdict.notional_usd / sc.risk.capital_usd * 100.0, 4
        )
        log.emit("RISK_EVALUATED", verdict.as_dict())
        transition(DecisionState.RISK_EVALUATED, "lab01.risk", verdict.reason_code)

        if not verdict.approved:
            failed = next(c for c in verdict.checks if not c.passed)
            log.emit(
                "RISK_REJECTED",
                {
                    "reason_code": verdict.reason_code,
                    "justification": failed.justification,
                    "observed": failed.observed,
                    "limit": failed.limit,
                    "comparison": failed.comparison,
                },
            )
            packet.reject("lab01.risk", verdict.reason_code)
            log.emit(
                "PACKET_TRANSITION",
                {
                    "from": "RISK_EVALUATED",
                    "to": "REJECTED",
                    "actor": "lab01.risk",
                    "reason": verdict.reason_code,
                },
            )
        else:
            transition(DecisionState.APPROVED, "lab01.risk", "within_limits")
            transition(
                DecisionState.EXECUTION_PENDING, "lab01.executor", "order_queued"
            )
            entry_id = f"{trace_id}-ORD-1"
            intent = OrderIntent(
                symbol=SYMBOL,
                side="buy",
                size=verdict.size,
                order_type="market",
                signal_price=sig.price,
                timestamp=SYNTHETIC_EPOCH.timestamp() + 60.0 * sig.bar_index,
                strategy_id="lab01.breakout",
            )
            log.emit(
                "ORDER_SUBMITTED",
                {
                    "order_id": entry_id,
                    "side": "buy",
                    "size": verdict.size,
                    "type": "market",
                },
            )
            try:
                entry = sim.execute(
                    intent, _snapshot(bars[sig.bar_index], sig.realized_vol_bps)
                )
            except SimulatedExecutionError as exc:
                summary["error_code"] = exc.code
                log.emit(
                    "EXECUTION_ERROR",
                    {
                        "order_id": entry_id,
                        "error_code": exc.code,
                        "stage": "entry",
                        "simulated": True,
                    },
                )
                transition(
                    DecisionState.FAILED,
                    "lab01.executor",
                    f"EXECUTION_ERROR:{exc.code}",
                )
                entry = None
            if entry is not None:
                log.emit("ORDER_FILLED", _fill_dict(entry, entry_id))
                transition(DecisionState.EXECUTED, "lab01.executor", "filled")
                log.emit(
                    "POSITION_OPENED",
                    {"size": entry.filled_size, "entry_price": entry.fill_price},
                )
                transition(DecisionState.MONITORED, "lab01.monitor", "position_open")
                exit_ref, exit_reason, exit_bar = None, None, None
                for j in range(sig.bar_index + 1, len(bars)):
                    b = bars[j]
                    log.set_bar(j)
                    held = j - sig.bar_index
                    if b.low <= sig.stop_loss:
                        exit_ref, exit_reason, exit_bar = sig.stop_loss, "STOP_LOSS", b
                    elif b.high >= sig.take_profit:
                        exit_ref, exit_reason, exit_bar = (
                            sig.take_profit,
                            "TAKE_PROFIT",
                            b,
                        )
                    elif held >= sc.signal.max_hold_bars or j == len(bars) - 1:
                        exit_ref, exit_reason, exit_bar = b.close, "TIME_EXIT", b
                    if exit_bar:
                        break
                exit_id = f"{trace_id}-ORD-2"
                out_intent = OrderIntent(
                    symbol=SYMBOL,
                    side="sell",
                    size=entry.filled_size,
                    order_type="market",
                    signal_price=exit_ref,
                    timestamp=SYNTHETIC_EPOCH.timestamp() + 60.0 * exit_bar.i,
                    strategy_id="lab01.breakout",
                )
                log.emit(
                    "ORDER_SUBMITTED",
                    {
                        "order_id": exit_id,
                        "side": "sell",
                        "size": entry.filled_size,
                        "type": "market",
                        "reason": exit_reason,
                    },
                )
                try:
                    out = sim.execute(
                        out_intent, _snapshot(exit_bar, sig.realized_vol_bps)
                    )
                except SimulatedExecutionError as exc:
                    summary["error_code"] = exc.code
                    log.emit(
                        "EXECUTION_ERROR",
                        {
                            "order_id": exit_id,
                            "error_code": exc.code,
                            "stage": "exit",
                            "simulated": True,
                        },
                    )
                    transition(
                        DecisionState.FAILED,
                        "lab01.executor",
                        f"EXECUTION_ERROR:{exc.code}",
                    )
                    out = None
                if out is not None:
                    log.emit("ORDER_FILLED", _fill_dict(out, exit_id))
                    fees = entry.fee_usd + out.fee_usd
                    pnl = (out.fill_price - entry.fill_price) * entry.filled_size - fees
                    summary["pnl_usd"], summary["fees_usd"] = (
                        round(pnl, 6),
                        round(fees, 6),
                    )
                    log.emit(
                        "POSITION_CLOSED",
                        {
                            "exit_reason": exit_reason,
                            "exit_bar": exit_bar.i,
                            "bars_held": exit_bar.i - sig.bar_index,
                            "synthetic_pnl_usd": summary["pnl_usd"],
                            "fees_usd": summary["fees_usd"],
                            "note": "PnL synthétique du LAB ; ne remplace ni FIN ni PPL",
                        },
                    )
                    transition(DecisionState.CLOSED, "lab01.executor", exit_reason)
                    transition(
                        DecisionState.POSTMORTEM_ANALYZED,
                        "lab01.postmortem",
                        "synthetic_postmortem",
                    )

    # --- critères explicites -------------------------------------------------
    ex = sc.expect
    types = log.types()
    final_state = packet.lifecycle_state.value if packet else "NO_PACKET"
    criteria = [
        _c(
            "FINAL_STATE", f"état final = {ex.final_state}", final_state, ex.final_state
        ),
        _c(
            "RISK_VERDICT",
            f"verdict risque = {ex.risk_reason_code}",
            summary["risk_reason_code"],
            ex.risk_reason_code,
        ),
        _c(
            "PACKET_CHAIN_VALID",
            "chaîne de hachage du DecisionPacket intègre",
            bool(packet and packet.verify_chain()),
            True,
        ),
        _c(
            "EVENT_CHAIN_VALID",
            "chaîne de hachage des événements intègre et SYNTHETIC",
            verify_chain(log.events),
            True,
        ),
        _c(
            "TRACEABLE",
            "tous les événements portent experiment_id et trace_id",
            all(
                e["experiment_id"] == experiment_id and e["trace_id"] == trace_id
                for e in log.events
            ),
            True,
        ),
        _c(
            "PNL_PRESENT",
            "PnL synthétique présent"
            if ex.pnl_expected
            else "aucun PnL (aucune position clôturée)",
            summary["pnl_usd"] is not None,
            ex.pnl_expected,
        ),
    ]
    for t in ex.required_events:
        criteria.append(
            _c(f"EVENT_PRESENT:{t}", f"événement {t} présent", t in types, True)
        )
    for t in ex.forbidden_events:
        criteria.append(
            _c(f"EVENT_ABSENT:{t}", f"événement {t} absent", t in types, False)
        )
    if ex.error_code:
        criteria.append(
            _c(
                "ERROR_CODE",
                f"code d'erreur = {ex.error_code}",
                summary["error_code"],
                ex.error_code,
            )
        )
    verdict_str = "PASS" if all(c["passed"] for c in criteria) else "FAIL"
    log.emit("CRITERIA_EVALUATED", {"verdict": verdict_str, "criteria": criteria})
    log.emit(
        "EXPERIMENT_FINISHED", {"verdict": verdict_str, "final_state": final_state}
    )

    result = {
        "schema": "lab01.result/1",
        "provenance": PROVENANCE,
        "experiment_id": experiment_id,
        "trace_id": trace_id,
        "scenario": sc.name,
        "title": sc.title,
        "verdict": verdict_str,
        "final_state": final_state,
        "criteria": criteria,
        "risk_reason_code": summary["risk_reason_code"],
        "error_code": summary["error_code"],
        "synthetic_pnl_usd": summary["pnl_usd"],
        "fees_usd": summary["fees_usd"],
        "signal": summary["signal"],
        "n_events": len(log.events),
        "events_digest": log.digest,
        "bars_digest": bars_digest(bars),
        "code_digest": cdigest,
        "config_digest": cfg_digest,
        "seed": d.seed,
        "exec_seed": sc.exec_seed,
        "note": "SYNTHETIC : aucune donnée de production, aucun exchange, aucune autorité PPL/FIN.",
    }
    return {
        "result": result,
        "events": log.events,
        "packet": packet.to_dict() if packet else None,
        "bars": bars,
    }


def _c(cid: str, description: str, observed, expected) -> dict:
    return {
        "id": cid,
        "description": description,
        "observed": observed,
        "expected": expected,
        "passed": observed == expected,
    }
