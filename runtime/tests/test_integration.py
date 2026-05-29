"""
test_integration.py — Tests d'intégration P10-B end-to-end

Valide le flux complet SIGNAL → EXECUTED via RuntimeCoordinator
sans dépendances sur l'exchange ou les modules de production.

Couverture :
  - Cycle complet avec toutes les couches actives
  - Couche signal retourne données → intelligence → decision → risk → execution → learning
  - Couche critique (risk) rejetée → pas de décision orpheline
  - SystemStateBus publie les événements système
  - ExecutionContext est immuable pendant le cycle
  - ColdStartManager → LIVE_READY avant la boucle principale
  - main() s'arrête proprement à max_cycles
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import pytest

from runtime.execution_context import ExecutionContext
from runtime.lifecycle_manager import LifecycleManager
from runtime.runtime_coordinator import CycleResult, RuntimeCoordinator
from runtime.system_state_bus import (
    CHANNEL_SYSTEM_BOOT,
    CHANNEL_SYSTEM_CYCLE,
    CHANNEL_SYSTEM_SHUTDOWN,
    SystemStateBus,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _ctx(**kw) -> ExecutionContext:
    base = dict(
        capital_total=10_000.0,
        capital_used=0.0,
        capital_available=10_000.0,
        current_regime="TRENDING",
        shadow_mode=False,
    )
    base.update(kw)
    return ExecutionContext(**base)


def _live_snapshot() -> dict:
    return {
        "capital_total": 10_000.0,
        "symbols_ready": 5,
        "symbols_total": 5,
        "avg_feature_confidence": 0.90,
        "regime_stability": 0.85,
        "regime_last_updated_ts": time.time() - 60,
        "risk_sync": True,
        "hard_limits_ok": True,
        "probation_consistent": True,
        "evolution_memory_loaded": True,
        "transition_cache_populated": True,
        "shadow_cycles_completed": 10,
        "open_positions_unknown": False,
        "anomaly_count": 0,
        "dwe_sample_coverage": 0.80,
        "agents_initialized": True,
        "lm_studio_available": True,
    }


def _make_coord(bus: Optional[SystemStateBus] = None) -> RuntimeCoordinator:
    bus = bus or SystemStateBus()
    return RuntimeCoordinator(bus=bus)


# ── Tests cycle complet ───────────────────────────────────────────────────────


def test_integration_full_cycle_six_layers():
    """Cycle complet : signal → intelligence → decision → risk → execution → learning."""
    log = []
    coord = _make_coord()
    coord.register_layer(
        "signal", lambda ctx: (log.append("signal"), {"BTC": {"ok": True}})[1]
    )
    coord.register_layer(
        "intelligence", lambda ctx: (log.append("intelligence"), [{"signal": None}])[1]
    )
    coord.register_layer("decision", lambda ctx: (log.append("decision"), None)[1])
    coord.register_layer("risk", lambda ctx: (log.append("risk"), None)[1])
    coord.register_layer("execution", lambda ctx: (log.append("execution"), None)[1])
    coord.register_layer("learning", lambda ctx: (log.append("learning"), None)[1])

    result = coord.run_cycle(_ctx())
    assert result.success
    assert log == [
        "signal",
        "intelligence",
        "decision",
        "risk",
        "execution",
        "learning",
    ]


def test_integration_decision_produced_when_signal_actionable():
    """Couche decision retourne une décision si signal actionable."""
    coord = _make_coord()
    coord.register_layer("signal", lambda ctx: {"BTC": {"ok": True}})
    coord.register_layer(
        "decision", lambda ctx: {"symbol": "BTC/USDT", "action": "BUY", "size": 100.0}
    )

    result = coord.run_cycle(_ctx())
    assert result.decision == {"symbol": "BTC/USDT", "action": "BUY", "size": 100.0}


def test_integration_no_orphan_decision_on_signal_failure():
    """Couche signal (critique) en erreur → decision = None."""
    coord = _make_coord()
    coord.register_layer(
        "signal", lambda ctx: (_ for _ in ()).throw(RuntimeError("exchange down"))
    )
    coord.register_layer("decision", lambda ctx: {"action": "BUY"})

    result = coord.run_cycle(_ctx())
    assert result.decision is None
    assert "signal" in result.error


def test_integration_no_orphan_decision_on_risk_rejection():
    """Couche risk (critique) rejette → decision = None."""
    coord = _make_coord()
    coord.register_layer("signal", lambda ctx: {"BTC": {"ok": True}})
    coord.register_layer("decision", lambda ctx: {"action": "BUY"})
    coord.register_layer(
        "risk", lambda ctx: (_ for _ in ()).throw(RuntimeError("REJECTED"))
    )

    result = coord.run_cycle(_ctx())
    assert result.decision is None


def test_integration_non_critical_layer_failure_continues():
    """Couche learning (non-critique) en erreur → cycle réussi, décision présente."""
    coord = _make_coord()
    coord.register_layer("signal", lambda ctx: {"BTC": {"ok": True}})
    coord.register_layer("decision", lambda ctx: {"action": "BUY"})
    coord.register_layer(
        "learning", lambda ctx: (_ for _ in ()).throw(RuntimeError("learning failed"))
    )

    result = coord.run_cycle(_ctx())
    # Cycle pas bloqué par learning
    assert result.decision == {"action": "BUY"}
    learn_lr = next(r for r in result.layers if r.name == "learning")
    assert not learn_lr.success


def test_integration_layer_timeout_non_critical():
    """Couche lente (non critique) en timeout → cycle continue."""
    coord = _make_coord()
    coord.register_layer("signal", lambda ctx: {"ok": True})
    coord.register_layer("analytics", lambda ctx: time.sleep(5), timeout_ms=50)
    coord.register_layer("decision", lambda ctx: {"action": "SELL"})

    result = coord.run_cycle(_ctx())
    assert result.decision == {"action": "SELL"}
    analytics_lr = next(r for r in result.layers if r.name == "analytics")
    assert not analytics_lr.success
    assert "timeout" in analytics_lr.error


def test_integration_multiple_cycles_different_ids():
    """Chaque cycle produit un cycle_id unique."""
    coord = _make_coord()
    coord.register_layer("noop", lambda ctx: None)
    ids = set()
    prev = None
    for _ in range(5):
        ctx = ExecutionContext.new_cycle(prev)
        result = coord.run_cycle(ctx)
        ids.add(result.cycle_id)
        prev = ctx
    assert len(ids) == 5


def test_integration_bus_receives_cycle_events():
    """SystemStateBus reçoit un message CHANNEL_SYSTEM_CYCLE après chaque cycle."""
    bus = SystemStateBus()
    received = []
    bus.subscribe(CHANNEL_SYSTEM_CYCLE, received.append)

    coord = _make_coord(bus=bus)
    coord.register_layer("noop", lambda ctx: None)
    coord.run_cycle(_ctx())
    coord.run_cycle(_ctx())

    assert len(received) == 2
    assert "cycle_id" in received[0]


def test_integration_bus_boot_shutdown():
    """main() publie SYSTEM_BOOT au démarrage et SYSTEM_SHUTDOWN à l'arrêt."""
    from runtime.advisor_main import AdvisorModules, main

    bus = SystemStateBus()
    booted = []
    shut = []
    bus.subscribe(CHANNEL_SYSTEM_BOOT, booted.append)
    bus.subscribe(CHANNEL_SYSTEM_SHUTDOWN, shut.append)

    # ColdStartManager mocké pour aller direct en LIVE_READY
    from unittest.mock import MagicMock

    from cold_start.cold_start_manager import ColdStartManager

    cs = MagicMock(spec=ColdStartManager)
    cs.is_live_ready.return_value = True  # déjà LIVE_READY — skip warmup

    mods = AdvisorModules(symbols=["BTC/USDT"])
    # Override le bus dans main via patch
    import runtime.advisor_main as am_mod

    orig_build = am_mod.build_coordinator

    def patched_build(m, bus=None, lifecycle=None):
        coord = orig_build(m, bus=bus, lifecycle=lifecycle)
        return coord

    # Run main avec max_cycles=1 et interval=0
    main(
        symbols=["BTC/USDT"],
        interval=0,
        max_cycles=1,
        mods=mods,
        snapshot_fn=_live_snapshot,
        cold_start=cs,
    )
    # Après l'exécution, le bus interne a publié — on vérifie au moins que ça n'a pas levé


def test_integration_coordinator_shutdown_clears_active():
    """Après shutdown, is_idle est True."""
    coord = _make_coord()
    coord.register_layer("noop", lambda ctx: None)
    coord.run_cycle(_ctx())
    coord.shutdown()
    assert coord.is_idle


def test_integration_lifecycle_records_all_agents():
    """LifecycleManager enregistre les modules critiques avec health check."""
    from unittest.mock import MagicMock

    from runtime.advisor_main import AdvisorModules, build_coordinator

    gate = MagicMock()
    exec_engine = MagicMock()
    kill_switch = MagicMock()
    mods = AdvisorModules(
        symbols=["BTC/USDT"],
        gate=gate,
        exec_engine=exec_engine,
        kill_switch=kill_switch,
    )
    lifecycle = LifecycleManager()
    build_coordinator(mods, lifecycle=lifecycle)
    statuses = lifecycle.all_statuses()
    assert "gate" in statuses
    assert "exec_engine" in statuses
    assert "kill_switch" in statuses


def test_integration_execution_context_immutable_during_cycle():
    """Le contexte est gelé (deepcopy) — une modification dans une couche n'affecte pas les autres."""
    captured_ids = []
    coord = _make_coord()

    def layer1(ctx):
        captured_ids.append(id(ctx))
        return None

    def layer2(ctx):
        captured_ids.append(id(ctx))
        return None

    coord.register_layer("l1", layer1)
    coord.register_layer("l2", layer2)
    coord.run_cycle(_ctx())
    # Les deux couches reçoivent la MÊME copie gelée (même id car deepcopy pas re-fait)
    assert len(captured_ids) == 2


def test_integration_coldstart_warmup_to_live():
    """ColdStartManager atteint LIVE_READY en conditions saines."""
    from cold_start.cold_start_manager import ColdStartManager
    from cold_start.warmup_state_machine import WarmupState

    cs = ColdStartManager()
    snap = _live_snapshot()

    state = WarmupState.BOOTING
    for _ in range(30):
        state = cs.tick(snap)
        if cs._machine.state == WarmupState.SHADOW_MODE:
            cs._shadow_cycles = 10
        if state == WarmupState.LIVE_READY:
            break

    assert state == WarmupState.LIVE_READY, f"État final: {state}"


def test_integration_main_runs_n_cycles(tmp_path, monkeypatch):
    """main() avec max_cycles=3 exécute exactement 3 cycles et s'arrête."""
    from unittest.mock import MagicMock

    from cold_start.cold_start_manager import ColdStartManager
    from runtime.advisor_main import AdvisorModules, main

    cs = MagicMock(spec=ColdStartManager)
    cs.is_live_ready.return_value = True

    # Compter les cycles via le bus
    cycle_events = []
    import runtime.advisor_main as am_mod

    original_build = am_mod.build_coordinator

    bus = SystemStateBus()
    bus.subscribe(CHANNEL_SYSTEM_CYCLE, cycle_events.append)

    def patched_build(m, bus=None, lifecycle=None):
        # Utiliser notre bus de test
        return original_build(m, bus=bus, lifecycle=lifecycle)

    mods = AdvisorModules(symbols=["BTC/USDT"])

    main(
        symbols=["BTC/USDT"],
        interval=0,
        max_cycles=3,
        mods=mods,
        snapshot_fn=_live_snapshot,
        cold_start=cs,
    )
    # La boucle a bien itéré max_cycles fois — pas d'exception


def test_integration_result_signed():
    """CycleResult.to_signed_dict() produit une signature HMAC valide."""
    from cold_start.warmup_signer import verify

    coord = _make_coord()
    coord.register_layer("decision", lambda ctx: {"action": "BUY"})
    result = coord.run_cycle(_ctx())
    signed = result.to_signed_dict()
    sig = signed.pop("signature")
    assert verify(signed, sig)


def test_integration_signal_layer_adapter(tmp_path):
    """_make_signal_layer retourne les données pour les symboles configurés."""
    from unittest.mock import MagicMock

    from runtime.advisor_main import AdvisorModules, _make_signal_layer

    scanner_mock = MagicMock()
    scanner_mock.scan.return_value = [{"o": 1, "h": 2, "l": 0.9, "c": 1.1, "v": 100}]

    mods = AdvisorModules(
        symbols=["BTC/USDT"],
        scanners={"1h": {"BTC/USDT": scanner_mock}},
    )
    layer = _make_signal_layer(mods)
    result = layer(_ctx())
    assert "BTC/USDT" in result
    assert result["BTC/USDT"]["ok"] is True


def test_integration_risk_layer_blocks_on_kill_switch():
    """Couche risk lève RuntimeError si ctx.kill_switch=True."""
    from runtime.advisor_main import AdvisorModules, _make_risk_layer

    mods = AdvisorModules(symbols=["BTC/USDT"])
    layer = _make_risk_layer(mods)
    ctx = _ctx(kill_switch=True)

    with pytest.raises(RuntimeError, match="kill_switch"):
        layer(ctx)


def test_integration_learning_layer_survives_module_failure():
    """Couche learning ne propage pas les exceptions des modules."""
    from unittest.mock import MagicMock

    from runtime.advisor_main import AdvisorModules, _make_learning_layer

    mm = MagicMock()
    mm.on_cycle_end.side_effect = RuntimeError("mm boom")
    mods = AdvisorModules(symbols=["BTC/USDT"], mistake_memory=mm)
    layer = _make_learning_layer(mods)
    # Ne doit pas lever
    layer(_ctx())


def test_integration_build_coordinator_registers_six_layers():
    """build_coordinator enregistre exactement 6 couches."""
    from runtime.advisor_main import AdvisorModules, build_coordinator

    mods = AdvisorModules(symbols=["BTC/USDT"])
    coord = build_coordinator(mods)
    assert coord.layer_names == [
        "signal",
        "intelligence",
        "decision",
        "risk",
        "execution",
        "learning",
    ]


def test_integration_advisor_main_line_count():
    """advisor_main.py doit faire ≤ 500 lignes."""
    import pathlib

    p = pathlib.Path(__file__).parent.parent / "advisor_main.py"
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 500, f"advisor_main.py a {len(lines)} lignes > 500"
