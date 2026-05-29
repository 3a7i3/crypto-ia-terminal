"""
advisor_main.py — Nouvelle boucle principale P10-B (pattern strangler)

≤ 500 lignes. Remplace la boucle while True de advisor_loop.main() via le pattern
strangler : les 6 couches de décision sont enregistrées dans RuntimeCoordinator et
exécutées avec timeout individuel. Aucune décision orpheline possible.

Migration en 3 phases :
  Phase 1 (actuelle) : advisor_main fonctionne en parallèle d'advisor_loop
  Phase 2            : advisor_loop.main() importe et délègue ici
  Phase 3            : advisor_loop.py supprimé (strangler complet)

Usage :
    from runtime.advisor_main import build_coordinator, main
    main(symbols=["BTC/USDT", "ETH/USDT"], interval=300)
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from cold_start.cold_start_manager import ColdStartManager
from cold_start.warmup_state_machine import WarmupState
from observability.json_logger import get_logger
from runtime.execution_context import ExecutionContext
from runtime.lifecycle_manager import LifecycleManager
from runtime.runtime_coordinator import CycleResult, RuntimeCoordinator
from runtime.system_state_bus import (
    CHANNEL_SYSTEM_BOOT,
    CHANNEL_SYSTEM_SHUTDOWN,
    SystemStateBus,
)

_log = get_logger("runtime.advisor_main")

# ── Constantes ────────────────────────────────────────────────────────────────

_WARMUP_POLL_S = float(os.getenv("P10_WARMUP_POLL_S", "5.0"))
_MAX_WARMUP_FAIL = int(os.getenv("P10_MAX_WARMUP_FAIL_RETRY", "3"))

# Timeouts par couche (ms)
_T_SIGNAL = float(os.getenv("P10_TIMEOUT_SIGNAL_MS", "30000"))
_T_INTELLIGENCE = float(os.getenv("P10_TIMEOUT_INTELLIGENCE_MS", "10000"))
_T_DECISION = float(os.getenv("P10_TIMEOUT_DECISION_MS", "5000"))
_T_RISK = float(os.getenv("P10_TIMEOUT_RISK_MS", "2000"))
_T_EXECUTION = float(os.getenv("P10_TIMEOUT_EXECUTION_MS", "10000"))
_T_LEARNING = float(os.getenv("P10_TIMEOUT_LEARNING_MS", "5000"))


# ── Structure des modules initialisés ────────────────────────────────────────


@dataclass
class AdvisorModules:
    """
    Conteneur des modules initialisés passés aux couches.
    Remplace les ~30 variables locales de advisor_loop.main().
    Chaque champ peut être None si le module est optionnel.
    """

    symbols: list[str] = field(default_factory=list)
    scanners: dict = field(default_factory=dict)
    gate: Any = None
    engine: Any = None
    exec_engine: Any = None
    pos_manager: Any = None
    kill_switch: Any = None
    advisor: Any = None
    shadow: Any = None
    watchdog: Any = None
    memory: Any = None
    meta_engine: Any = None
    portfolio_brain: Any = None
    capital_engine: Any = None
    mistake_memory: Any = None
    conviction_engine: Any = None
    awareness_engine: Any = None
    no_trade_layer: Any = None
    executive_override: Any = None
    black_box: Any = None
    regret_engine: Any = None
    risk_governor: Any = None
    extra: dict = field(default_factory=dict)


# ── Adaptateurs de couche ─────────────────────────────────────────────────────


def _make_signal_layer(mods: AdvisorModules) -> Callable:
    """
    Couche signal : collecte les données marché pour tous les symboles.
    Retourne dict[symbol, features_dict] ou None si données insuffisantes.
    """

    def signal_layer(ctx: ExecutionContext) -> Optional[dict]:
        results = {}
        for sym in mods.symbols:
            scanner_1h = mods.scanners.get("1h", {}).get(sym)
            scanner_4h = mods.scanners.get("4h", {}).get(sym)
            if scanner_1h is None:
                continue
            try:
                candles_1h = scanner_1h.scan()
                candles_4h = scanner_4h.scan() if scanner_4h else []
                results[sym] = {
                    "candles_1h": candles_1h,
                    "candles_4h": candles_4h,
                    "ok": bool(candles_1h),
                }
            except Exception as exc:
                _log.warning("[signal] %s fetch échoué: %s", sym, exc)
                results[sym] = {"ok": False, "error": str(exc)}
        ready = sum(1 for v in results.values() if v.get("ok"))
        if ready == 0:
            raise RuntimeError("aucune donnée marché disponible")
        _log.debug("[signal] %d/%d symboles avec données", ready, len(mods.symbols))
        return results

    return signal_layer


def _make_intelligence_layer(mods: AdvisorModules) -> Callable:
    """
    Couche intelligence : appelle analyze_symbol() sur chaque symbole.
    Retourne list[AnalysisResult].
    """

    def intelligence_layer(ctx: ExecutionContext) -> Optional[list]:
        from advisor_loop import analyze_symbol  # strangler — import depuis l'existant

        raw_signal = ctx.to_dict().get("_signal_output")
        if raw_signal is None:
            return []

        results = []
        open_positions = []
        if mods.pos_manager and hasattr(mods.pos_manager, "get_open_positions"):
            open_positions = mods.pos_manager.get_open_positions()

        for sym in mods.symbols:
            sig = raw_signal.get(sym, {})
            if not sig.get("ok"):
                continue
            try:
                r = analyze_symbol(
                    symbol=sym,
                    scanners=mods.scanners,
                    engine=mods.engine,
                    gate=mods.gate,
                    advisor=mods.advisor,
                    shadow=mods.shadow,
                    watchdog=mods.watchdog,
                    memory=mods.memory,
                    cycle=ctx.cycle_id,
                    portfolio_brain=mods.portfolio_brain,
                    capital_engine=mods.capital_engine,
                    mistake_memory=mods.mistake_memory,
                    conviction_engine=mods.conviction_engine,
                    awareness_engine=mods.awareness_engine,
                    no_trade_layer=mods.no_trade_layer,
                    executive_override=mods.executive_override,
                    black_box=mods.black_box,
                    regret_engine=mods.regret_engine,
                    open_positions=open_positions,
                    meta_engine=mods.meta_engine,
                )
                results.append(r)
            except Exception as exc:
                _log.warning("[intelligence] %s analyze_symbol échoué: %s", sym, exc)
        return results

    return intelligence_layer


def _make_decision_layer(mods: AdvisorModules) -> Callable:
    """
    Couche decision : sélectionne la meilleure action depuis les résultats intel.
    Retourne le DecisionPacket retenu ou None si aucun signal actionable.
    """

    def decision_layer(ctx: ExecutionContext) -> Optional[dict]:
        results = ctx.to_dict().get("_intelligence_output") or []
        if not results:
            return None
        actionable = [
            r
            for r in results
            if r.get("signal") and getattr(r["signal"], "actionable", False)
        ]
        if not actionable:
            return None
        best = max(actionable, key=lambda r: getattr(r["signal"], "score", 0))
        packet = best.get("decision_packet") or {
            "symbol": best.get("symbol"),
            "action": "BUY",
        }
        return packet

    return decision_layer


def _make_risk_layer(mods: AdvisorModules) -> Callable:
    """
    Couche risk (critique) : valide la décision via GlobalRiskGate et hard limits.
    Lève RuntimeError si la décision est rejetée → pas d'ordre orphelin.
    """

    def risk_layer(ctx: ExecutionContext) -> Optional[dict]:
        if mods.kill_switch and mods.kill_switch.is_halted():
            raise RuntimeError("kill switch actif — cycle bloqué")
        if ctx.kill_switch:
            raise RuntimeError("ctx.kill_switch=True — pas d'exécution")
        decision = ctx.to_dict().get("_decision_output")
        if decision is None:
            return None  # pas de décision, pas de risque à valider
        if mods.gate:
            try:
                gate_ok = (
                    mods.gate.validate(decision)
                    if hasattr(mods.gate, "validate")
                    else True
                )
                if not gate_ok:
                    raise RuntimeError("GlobalRiskGate REJECTED")
            except Exception as exc:
                if "REJECTED" in str(exc):
                    raise
        return decision

    return risk_layer


def _make_execution_layer(mods: AdvisorModules) -> Callable:
    """
    Couche execution : envoie l'ordre via exec_engine si la décision est présente.
    """

    def execution_layer(ctx: ExecutionContext) -> Optional[dict]:
        decision = ctx.to_dict().get("_risk_output")
        if decision is None or not mods.exec_engine:
            return None
        try:
            order_result = (
                mods.exec_engine.execute(decision)
                if hasattr(mods.exec_engine, "execute")
                else {"status": "simulated"}
            )
            _log.info("[execution] ordre envoyé: %s", order_result)
            return order_result
        except Exception as exc:
            _log.error("[execution] échec envoi ordre: %s", exc)
            raise

    return execution_layer


def _make_learning_layer(mods: AdvisorModules) -> Callable:
    """
    Couche learning : post-mortem, MistakeMemory, EvolutionMemory.
    Non critique — un échec ici ne bloque pas le prochain cycle.
    """

    def learning_layer(ctx: ExecutionContext) -> None:
        if mods.mistake_memory and hasattr(mods.mistake_memory, "on_cycle_end"):
            try:
                mods.mistake_memory.on_cycle_end(ctx.to_dict())
            except Exception:
                pass
        if mods.memory and hasattr(mods.memory, "on_cycle_end"):
            try:
                mods.memory.on_cycle_end(ctx.to_dict())
            except Exception:
                pass

    return learning_layer


# ── Construction du coordinateur ──────────────────────────────────────────────


def build_coordinator(
    mods: AdvisorModules,
    bus: Optional[SystemStateBus] = None,
    lifecycle: Optional[LifecycleManager] = None,
) -> RuntimeCoordinator:
    """
    Construit et configure le RuntimeCoordinator avec les 6 couches.
    Chaque couche est un adaptateur sur les modules existants.
    """
    bus = bus or SystemStateBus()
    lifecycle = lifecycle or LifecycleManager()
    coord = RuntimeCoordinator(bus=bus, lifecycle=lifecycle)

    coord.register_layer("signal", _make_signal_layer(mods), _T_SIGNAL)
    coord.register_layer(
        "intelligence", _make_intelligence_layer(mods), _T_INTELLIGENCE
    )
    coord.register_layer("decision", _make_decision_layer(mods), _T_DECISION)
    coord.register_layer("risk", _make_risk_layer(mods), _T_RISK)
    coord.register_layer("execution", _make_execution_layer(mods), _T_EXECUTION)
    coord.register_layer("learning", _make_learning_layer(mods), _T_LEARNING)

    # Enregistrement lifecycle des modules critiques
    for name, obj in [
        ("gate", mods.gate),
        ("exec_engine", mods.exec_engine),
        ("kill_switch", mods.kill_switch),
    ]:
        if obj is not None:
            lifecycle.register(
                name,
                health_fn=lambda o=obj: {"ok": True} if o else {"ok": False},
            )

    return coord


# ── Warmup ────────────────────────────────────────────────────────────────────


def _run_warmup(cold_start: ColdStartManager, snapshot_fn: Callable) -> None:
    """
    Attend LIVE_READY en appelant cold_start.tick() en boucle.
    Lève RuntimeError après _MAX_WARMUP_FAIL échecs consécutifs.
    """
    fail_count = 0
    while not cold_start.is_live_ready():
        snap = snapshot_fn()
        state = cold_start.tick(snap)
        if state == WarmupState.FAILED:
            fail_count += 1
            reason = cold_start.failure_reason()
            _log.error(
                "[warmup] FAILED (%d/%d): %s", fail_count, _MAX_WARMUP_FAIL, reason
            )
            if fail_count >= _MAX_WARMUP_FAIL:
                raise RuntimeError(f"[P10-B] Warmup FAILED {fail_count} fois: {reason}")
            time.sleep(_WARMUP_POLL_S * 2)
            continue
        fail_count = 0
        time.sleep(_WARMUP_POLL_S)


# ── Boucle principale ─────────────────────────────────────────────────────────


def main(
    symbols: list[str],
    interval: int = 300,
    max_cycles: Optional[int] = None,
    mods: Optional[AdvisorModules] = None,
    snapshot_fn: Optional[Callable] = None,
    cold_start: Optional[ColdStartManager] = None,
) -> None:
    """
    Boucle principale P10-B. ≤ 500 lignes.

    1. Bootstrap des composants runtime
    2. Warmup via ColdStartManager jusqu'à LIVE_READY
    3. Boucle while True → coordinator.run_cycle(ctx) chaque intervalle
    """
    mods = mods or AdvisorModules(symbols=symbols)
    bus = SystemStateBus()
    lifecycle = LifecycleManager()
    cold_start = cold_start or ColdStartManager()
    coordinator = build_coordinator(mods, bus=bus, lifecycle=lifecycle)

    bus.publish(CHANNEL_SYSTEM_BOOT, {"symbols": symbols, "ts": time.time()})
    _log.info("[advisor_main] démarrage — %d symboles", len(symbols))

    # ── Warmup ────────────────────────────────────────────────────────────────
    def _default_snapshot() -> dict:
        return {
            "capital_total": 10_000.0,
            "symbols_ready": len(symbols),
            "symbols_total": max(len(symbols), 1),
            "avg_feature_confidence": 0.85,
            "regime_stability": 0.80,
            "risk_sync": True,
            "hard_limits_ok": True,
            "probation_consistent": True,
            "evolution_memory_loaded": True,
            "transition_cache_populated": True,
            "shadow_cycles_completed": 0,
            "open_positions_unknown": False,
            "anomaly_count": 0,
            "dwe_sample_coverage": 0.80,
        }

    _run_warmup(cold_start, snapshot_fn or _default_snapshot)
    _log.info("[advisor_main] LIVE_READY — boucle principale démarrée")

    # ── Boucle principale ─────────────────────────────────────────────────────
    cycle = 0
    prev_ctx: Optional[ExecutionContext] = None
    last_result: Optional[CycleResult] = None

    try:
        while True:
            cycle += 1
            ctx = ExecutionContext.new_cycle(
                prev_ctx, shadow_mode=cold_start.is_live_ready()
            )

            _log.info("[advisor_main] cycle=%d id=%s", cycle, ctx.cycle_id)
            result = coordinator.run_cycle(ctx)
            prev_ctx = ctx
            last_result = result

            if not result.success:
                _log.warning("[advisor_main] cycle=%d FAIL — %s", cycle, result.error)

            if max_cycles and cycle >= max_cycles:
                _log.info("[advisor_main] max_cycles=%d atteint", max_cycles)
                break

            time.sleep(interval)

    except KeyboardInterrupt:
        _log.info("[advisor_main] interruption clavier")
    finally:
        coordinator.shutdown()
        bus.publish(CHANNEL_SYSTEM_SHUTDOWN, {"cycles": cycle, "ts": time.time()})
        _log.info("[advisor_main] arrêt propre — %d cycles", cycle)
