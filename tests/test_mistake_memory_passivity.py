"""
tests/test_mistake_memory_passivity.py — S-02B.1 : passivité de MistakeMemory.

ADR S-02B.1 : LEARNING != AUTHORITY. MistakeMemory peut observer, enregistrer,
classifier et proposer des règles de blocage en permanence ; elle ne peut
transformer un match de règle en veto réel sur un trade live que si
FEATURE_ADAPTIVE_DECISION_FEEDBACK est explicitement activé (défaut: False).

Structure :
    Layer 1 — MistakeMemory (classe isolée) : check_before_trade()/__bool__
    Layer 2 — advisor_loop.analyze_symbol() : intégration bout-en-bout
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))

from quant_hedge_ai.agents.intelligence.mistake_memory import (
    MistakeCheckResult,
    MistakeMemory,
)


# ── Layer 1 — MistakeMemory isolée ───────────────────────────────────────────


def _mm(tmp_path: Path) -> MistakeMemory:
    return MistakeMemory(db_path=str(tmp_path / "mistake_memory.jsonl"))


def _seed_regime_mismatch_rule(mm: MistakeMemory) -> None:
    """Fait apparaître une règle REGIME_MISMATCH active.

    `_count_similar()` est évalué avant l'ajout de l'enregistrement courant
    (voir `record_trade_result`), donc il faut REPEAT_BLOCK_THRESHOLD + 1
    occurrences (par défaut 2 + 1 = 3) pour que la règle apparaisse.
    """
    for _ in range(mm.REPEAT_BLOCK_THRESHOLD + 1):
        mm.record_trade_result(
            order_id="o",
            symbol="BTC/USDT",
            signal="BUY",
            score=60,
            regime="sideways",
            conviction_level="medium",
            pnl_pct=-0.02,
            context_features={},
        )


class TestMistakeCheckResultBoolSemantics:
    def test_blocked_result_is_falsy(self):
        res = MistakeCheckResult(blocked=True, reason="x", rule_id="r1")
        assert bool(res) is False

    def test_unblocked_result_is_truthy(self):
        res = MistakeCheckResult(blocked=False, reason="OK")
        assert bool(res) is True


class TestMistakeMemoryRuleMatching:
    def test_no_matching_rule_behavior_unchanged(self, tmp_path):
        """Aucune règle → check_before_trade() OK, indépendant du flag S-02."""
        mm = _mm(tmp_path)
        check = mm.check_before_trade(
            symbol="ETH/USDT",
            signal="BUY",
            score=90,
            regime="bull_trend",
            features={},
        )
        assert check.blocked is False
        assert bool(check) is True

    def test_repeated_regime_mismatch_generates_active_rule(self, tmp_path):
        mm = _mm(tmp_path)
        _seed_regime_mismatch_rule(mm)
        assert len(mm.active_rules_summary()) >= 1

    def test_matching_rule_reports_blocked_true_on_check(self, tmp_path):
        """La classe elle-même continue de rapporter un match — c'est
        advisor_loop (S-02B.1), pas MistakeMemory, qui décide si ce match
        devient un veto réel."""
        mm = _mm(tmp_path)
        _seed_regime_mismatch_rule(mm)
        check = mm.check_before_trade(
            symbol="BTC/USDT",
            signal="BUY",
            score=50,
            regime="sideways",
            features={},
        )
        assert check.blocked is True
        assert check.rule_id is not None

    def test_state_provenance_reflects_volume(self, tmp_path):
        mm = _mm(tmp_path)
        _seed_regime_mismatch_rule(mm)
        prov = mm.state_provenance()
        assert prov["subsystem"] == "MistakeMemory"
        assert prov["n_records"] == mm.REPEAT_BLOCK_THRESHOLD + 1
        assert prov["n_rules_active"] >= 1
        assert prov["source_path"].endswith("mistake_memory.jsonl")

    def test_record_trade_result_does_not_mutate_historical_records(self, tmp_path):
        """S-02B.1 §13 — aucune réécriture rétroactive de l'historique."""
        mm = _mm(tmp_path)
        mm.record_trade_result(
            order_id="o1",
            symbol="BTC/USDT",
            signal="BUY",
            score=70,
            regime="bull_trend",
            conviction_level="high",
            pnl_pct=0.01,
            context_features={},
        )
        first_record = dict(mm._mistakes[0])
        mm.record_trade_result(
            order_id="o2",
            symbol="ETH/USDT",
            signal="SELL",
            score=65,
            regime="bear_trend",
            conviction_level="medium",
            pnl_pct=-0.05,
            context_features={},
        )
        assert mm._mistakes[0] == first_record


# ── Layer 2 — Intégration advisor_loop.analyze_symbol() ─────────────────────


class _FakeMultiTimeframeScanner:
    @staticmethod
    def merge_base(mtf_data, symbol, candles_1h):
        return {}


class _FakeFeatureEngineer:
    def extract_features(self, candles):
        return {}


class _FakeRegimeDetector:
    def classify(self, features):
        return "unknown"


class _FakeConfidenceExplainer:
    def explain(self, signal):
        return None


class _FakeRuntime:
    MultiTimeframeScanner = _FakeMultiTimeframeScanner
    FeatureEngineer = _FakeFeatureEngineer
    AdvancedRegimeDetector = _FakeRegimeDetector
    ConfidenceExplainer = _FakeConfidenceExplainer


class _FakeScanner1h:
    last_stability: dict = {}

    def scan(self):
        return {}


class _FakeScannerMtf:
    def scan(self, cycle):
        return {}


class _FakeGate:
    def check(self, signal, portfolio_drawdown, order_size_usd):
        return SimpleNamespace(allowed=True, failed=[], reason=None)


class _FakeAdvisor:
    def explain(self, signal):
        return SimpleNamespace(risk_level="low", confidence="high", text="ok")


class _FakeShadow:
    pass


class _FakeWatchdog:
    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def measure(self, *_a, **_k):
        return self._Ctx()


class _FakeStrategyMemoryStore:
    def load_by_regime(self, regime, limit=10):
        return []

    def state_provenance(self):
        return {"subsystem": "StrategyMemoryStore", "source_path": "x"}


class _FakeMistakeMemoryBlocking:
    """check_before_trade() retourne toujours un match bloquant."""

    def __init__(self):
        self.calls = 0

    def check_before_trade(self, **kwargs):
        self.calls += 1
        return MistakeCheckResult(
            blocked=True,
            reason="[REGIME_MISMATCH] test rule",
            rule_id="REGIME_MISMATCH_sideways_BUY_1",
            similar_mistakes=2,
        )

    def state_provenance(self):
        return {"subsystem": "MistakeMemory", "n_records": 2, "n_rules_active": 1}


class _FakeMistakeMemoryClear:
    def check_before_trade(self, **kwargs):
        return MistakeCheckResult(blocked=False, reason="OK")

    def state_provenance(self):
        return {"subsystem": "MistakeMemory", "n_records": 0, "n_rules_active": 0}


def _actionable_signal() -> SimpleNamespace:
    """Signal BUY minimal — délibérément sans `.regime`/`.components` pour que
    `_to_decision_packet` échoue proprement (capturé par le try/except large
    d'analyze_symbol) et que le test reste focalisé sur la frontière S-02B.1,
    sans dépendre du sous-système DecisionPacket."""
    return SimpleNamespace(
        signal="BUY",
        score=80,
        actionable=True,
        confirmed=True,
        strength=1.0,
        timestamp=time.time(),
    )


def _run_analyze_symbol(mistake_memory, monkeypatch):
    import core.advisor_loop as advisor_loop

    # Isolation stricte : aucun état de circuit-breaker hérité d'un autre test.
    monkeypatch.setattr(advisor_loop, "_cb_mistake_memory", None)

    from quant_hedge_ai.runtime.runtime_state_machine import RuntimeStateMachine
    from core.authority import init_authority, reset_authority

    rsm = RuntimeStateMachine()
    init_authority(rsm)
    try:
        scanners = {
            "1h": {"BTC/USDT": _FakeScanner1h()},
            "mtf": {"BTC/USDT": _FakeScannerMtf()},
        }
        engine = SimpleNamespace(evaluate=lambda *a, **k: _actionable_signal())
        result = advisor_loop.analyze_symbol(
            symbol="BTC/USDT",
            scanners=scanners,
            engine=engine,
            gate=_FakeGate(),
            advisor=_FakeAdvisor(),
            shadow=_FakeShadow(),
            watchdog=_FakeWatchdog(),
            memory=_FakeStrategyMemoryStore(),
            cycle=1,
            mistake_memory=mistake_memory,
            runtime=_FakeRuntime(),
        )
    finally:
        reset_authority()
    return result


class TestAdvisorLoopMistakeMemoryPassivity:
    def test_default_feedback_false_does_not_block_trade(self, monkeypatch):
        """S-02B.1 §14 — flag par défaut (false) : un match ne bloque pas trade_allowed."""
        import core.advisor_loop as advisor_loop

        assert advisor_loop.FEATURE_ADAPTIVE_DECISION_FEEDBACK is False
        mm = _FakeMistakeMemoryBlocking()
        result = _run_analyze_symbol(mm, monkeypatch)

        assert mm.calls == 1, "MistakeMemory doit continuer d'être consultée (observation)"
        assert result["mm_check"].blocked is True, "le match reste visible (contrefactuel)"
        assert "mistake_mem" not in result["blockers"]
        assert result["trade_allowed"] is True, (
            "S-02B.1 VIOLATION : un match MistakeMemory a bloqué le trade "
            "alors que FEATURE_ADAPTIVE_DECISION_FEEDBACK=false"
        )

    def test_feedback_true_restores_legacy_block(self, monkeypatch):
        """S-02B.1 §14 — flag explicitement true : comportement legacy (veto réel)."""
        import core.advisor_loop as advisor_loop

        monkeypatch.setattr(advisor_loop, "FEATURE_ADAPTIVE_DECISION_FEEDBACK", True)
        mm = _FakeMistakeMemoryBlocking()
        result = _run_analyze_symbol(mm, monkeypatch)

        assert result["mm_check"].blocked is True
        assert "mistake_mem" in result["blockers"]
        assert result["trade_allowed"] is False

    def test_no_matching_rule_trade_allowed_unaffected_by_flag(self, monkeypatch):
        """Sans match, le flag S-02 n'a aucun effet (comportement inchangé)."""
        import core.advisor_loop as advisor_loop

        mm = _FakeMistakeMemoryClear()
        result_passive = _run_analyze_symbol(mm, monkeypatch)
        assert result_passive["trade_allowed"] is True

        monkeypatch.setattr(advisor_loop, "FEATURE_ADAPTIVE_DECISION_FEEDBACK", True)
        result_active = _run_analyze_symbol(mm, monkeypatch)
        assert result_active["trade_allowed"] is True

    def test_passive_mode_still_reports_rule_match(self, monkeypatch):
        """S-02B.1 §11 — observabilité contrefactuelle préservée en mode passif."""
        mm = _FakeMistakeMemoryBlocking()
        result = _run_analyze_symbol(mm, monkeypatch)
        assert result["mm_check"] is not None
        assert result["mm_check"].blocked is True
        assert result["mm_check"].rule_id == "REGIME_MISMATCH_sideways_BUY_1"

    def test_passive_mode_survives_missing_state_provenance(self, monkeypatch):
        """Régression : une implémentation de mistake_memory sans
        state_provenance() ne doit jamais empêcher la passivité de
        s'appliquer (trade_allowed doit rester True)."""

        class _MistakeMemoryNoProvenance:
            def check_before_trade(self, **kwargs):
                return MistakeCheckResult(
                    blocked=True, reason="x", rule_id="r1"
                )

        result = _run_analyze_symbol(_MistakeMemoryNoProvenance(), monkeypatch)
        assert result["trade_allowed"] is True
