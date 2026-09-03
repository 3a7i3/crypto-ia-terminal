"""
tests/test_feature_flag_startup_order.py — S-02B.1 : ordre de résolution du
flag FEATURE_ADAPTIVE_DECISION_FEEDBACK vis-à-vis de load_dotenv().

Défaut identifié en revue indépendante : `core/advisor_loop.py` importait
`FEATURE_ADAPTIVE_DECISION_FEEDBACK` depuis `config.feature_flags` (une
constante de module résolue une seule fois, à l'import, via os.getenv())
AVANT son propre appel à `load_dotenv(override=True)`. Si le process n'a pas
déjà la variable dans son environnement au moment de cet import (cas normal
d'un déploiement piloté par un fichier `.env`), la constante se fige à False
même si le `.env` définit ensuite `FEATURE_ADAPTIVE_DECISION_FEEDBACK=true` —
`config.feature_flags` est déjà dans `sys.modules`, donc un ré-import ne
ré-exécute pas son corps et ne change rien.

Remédiation : `config.feature_flags.adaptive_decision_feedback_enabled()`
est un résolveur public qui relit `os.environ` à CHAQUE appel (jamais mis en
cache par l'import). `core/advisor_loop.py` l'appelle une fois, juste après
son `load_dotenv(override=True)`, et réassigne son propre
`FEATURE_ADAPTIVE_DECISION_FEEDBACK` module-level à partir de cette valeur —
tous les points de consommation existants (lookups de nom de module au moment
de l'appel, pas de capture à la définition) voient donc la valeur corrigée
sans qu'il soit nécessaire de les modifier individuellement.

Contrat requis :
    absent          → False
    "false"         → False
    "true"          → True
    valeur malformée → False
    échec d'import/résolution → False
"""
from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))

import config.feature_flags as flags


# ── Résolveur public — config/feature_flags.py ───────────────────────────────


class TestAdaptiveDecisionFeedbackResolver:
    def test_absent_resolves_false(self, monkeypatch):
        """Test requis #1."""
        monkeypatch.delenv("FEATURE_ADAPTIVE_DECISION_FEEDBACK", raising=False)
        assert flags.adaptive_decision_feedback_enabled() is False

    def test_explicit_false_resolves_false(self, monkeypatch):
        """Test requis #2."""
        monkeypatch.setenv("FEATURE_ADAPTIVE_DECISION_FEEDBACK", "false")
        assert flags.adaptive_decision_feedback_enabled() is False

    def test_explicit_true_resolves_true(self, monkeypatch):
        """Test requis #3."""
        monkeypatch.setenv("FEATURE_ADAPTIVE_DECISION_FEEDBACK", "true")
        assert flags.adaptive_decision_feedback_enabled() is True

    def test_malformed_value_resolves_false(self, monkeypatch):
        """Test requis #4."""
        for malformed in ("yeah", "TRUEISH", "1.0", "enabled", "  ", "vrai"):
            monkeypatch.setenv("FEATURE_ADAPTIVE_DECISION_FEEDBACK", malformed)
            assert flags.adaptive_decision_feedback_enabled() is False, (
                f"valeur malformée {malformed!r} n'a pas résolu à False"
            )

    def test_case_insensitive_true_variants(self, monkeypatch):
        for truthy in ("true", "TRUE", "True", "1", "yes", "YES"):
            monkeypatch.setenv("FEATURE_ADAPTIVE_DECISION_FEEDBACK", truthy)
            assert flags.adaptive_decision_feedback_enabled() is True, (
                f"valeur {truthy!r} aurait dû résoudre à True"
            )


# ── Test requis #5 — régression critique d'ordre d'import ───────────────────


class TestCriticalOrderingRegression:
    """Preuve que la résolution effective ne dépend pas d'une constante de
    module figée avant load_dotenv() — reproduit le scénario réel de
    démarrage en rechargeant core.advisor_loop (qui exécute son propre
    load_dotenv() + la ré-résolution S-02B.1 à chaque import de module)."""

    def test_effective_value_reflects_env_set_after_first_import(self, monkeypatch):
        import core.advisor_loop as advisor_loop

        # Étape 1 : config.feature_flags (et donc advisor_loop) déjà importé
        # alors que la variable est absente — reproduit "importé avant que
        # .env ne soit chargé".
        monkeypatch.delenv("FEATURE_ADAPTIVE_DECISION_FEEDBACK", raising=False)
        importlib.reload(advisor_loop)
        assert advisor_loop.FEATURE_ADAPTIVE_DECISION_FEEDBACK is False

        try:
            # Étape 2 : l'environnement/.env définit ensuite la variable à
            # true (simule load_dotenv() chargeant une valeur qui n'existait
            # pas au premier import).
            monkeypatch.setenv("FEATURE_ADAPTIVE_DECISION_FEEDBACK", "true")

            # Étape 3 : un nouveau démarrage du module (= un nouveau process
            # en production) doit refléter la valeur actuelle de
            # l'environnement, PAS une constante figée au premier import de
            # config.feature_flags (qui resterait dans sys.modules, non
            # ré-exécuté).
            importlib.reload(advisor_loop)
            assert advisor_loop.FEATURE_ADAPTIVE_DECISION_FEEDBACK is True, (
                "S-02B.1 VIOLATION : FEATURE_ADAPTIVE_DECISION_FEEDBACK reste "
                "figé sur une constante de module obsolète résolue avant "
                "load_dotenv() — le résolveur public n'est pas utilisé, ou "
                "n'est pas appelé après load_dotenv()."
            )

            # Preuve indépendante, au niveau du résolveur public seul (sans
            # dépendre de sys.modules / d'un éventuel rechargement) : il
            # relit l'environnement à cet appel précis, quel que soit l'état
            # de la constante de module de config.feature_flags.
            assert flags.adaptive_decision_feedback_enabled() is True
        finally:
            # Restaure l'état par défaut pour ne pas polluer les tests
            # suivants qui importent core.advisor_loop dans ce process pytest.
            monkeypatch.delenv("FEATURE_ADAPTIVE_DECISION_FEEDBACK", raising=False)
            importlib.reload(advisor_loop)
            assert advisor_loop.FEATURE_ADAPTIVE_DECISION_FEEDBACK is False

    def test_stale_module_constant_would_have_missed_late_env_change(
        self, monkeypatch
    ):
        """Documente précisément le défaut corrigé : la constante de module
        `config.feature_flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK` (résolue
        une fois, à l'import) NE reflète PAS un changement d'environnement
        tardif — c'est exactement pour cette raison que
        `core/advisor_loop.py` ne doit plus s'y fier après son
        `load_dotenv()`, et utilise le résolveur public à la place."""
        monkeypatch.delenv("FEATURE_ADAPTIVE_DECISION_FEEDBACK", raising=False)
        importlib.reload(flags)
        assert flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK is False

        monkeypatch.setenv("FEATURE_ADAPTIVE_DECISION_FEEDBACK", "true")
        # Pas de reload ici : simule sys.modules déjà peuplé (cas réel).
        assert flags.FEATURE_ADAPTIVE_DECISION_FEEDBACK is False, (
            "la constante de module est censée être figée — si elle a "
            "changé sans reload, ce test lui-même est devenu invalide"
        )
        # ... alors que le résolveur public, lui, voit la valeur à jour.
        assert flags.adaptive_decision_feedback_enabled() is True

        # Nettoyage : laisser flags dans un état par défaut pour les autres tests.
        monkeypatch.delenv("FEATURE_ADAPTIVE_DECISION_FEEDBACK", raising=False)
        importlib.reload(flags)


# ── Tests requis #6/#7 — intégration advisor, flag EFFECTIF (résolu) ────────


def _actionable_signal() -> SimpleNamespace:
    return SimpleNamespace(
        signal="BUY", score=80, actionable=True, confirmed=True,
        strength=1.0, timestamp=time.time(),
    )


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


class _CountingMistakeMemory:
    """MistakeMemory factice qui matche toujours et capture
    count_as_applied_block."""

    def __init__(self):
        self.count_as_applied_block_calls: list[bool] = []
        self.applied_trigger_count = 0

    def check_before_trade(self, count_as_applied_block=True, **kwargs):
        self.count_as_applied_block_calls.append(count_as_applied_block)
        if count_as_applied_block:
            self.applied_trigger_count += 1
        from quant_hedge_ai.agents.intelligence.mistake_memory import (
            MistakeCheckResult,
        )

        return MistakeCheckResult(
            blocked=True, reason="[TEST] match", rule_id="TEST_RULE"
        )

    def state_provenance(self):
        return {"subsystem": "MistakeMemory"}


class _CountingStrategyMemoryStore:
    def __init__(self):
        self.record_usage_calls: list[bool] = []

    def load_by_regime(self, regime, limit=10, record_usage=True):
        self.record_usage_calls.append(record_usage)
        return [{"strategy": {"name": "momentum_v1"}, "sharpe": 1.8}]

    def state_provenance(self):
        return {"subsystem": "StrategyMemoryStore"}


def _run_analyze_symbol_with_effective_flag(
    effective_flag: bool, mistake_memory, memory, monkeypatch
):
    import core.advisor_loop as advisor_loop

    # Le flag EFFECTIF (résolu par la fonction publique à partir de
    # l'environnement, pas un booléen arbitraire choisi par le test) pilote
    # le comportement — preuve que c'est bien cette valeur qui est branchée.
    monkeypatch.setattr(
        advisor_loop, "FEATURE_ADAPTIVE_DECISION_FEEDBACK", effective_flag
    )
    monkeypatch.setattr(advisor_loop, "_cb_mistake_memory", None)

    from quant_hedge_ai.runtime.runtime_state_machine import RuntimeStateMachine
    from core.authority import init_authority, reset_authority

    rsm = RuntimeStateMachine()
    init_authority(rsm)
    captured: dict = {}
    try:

        def _fake_evaluate(symbol, mtf_candles, features=None, memory_sharpe=None):
            captured["memory_sharpe"] = memory_sharpe
            return _actionable_signal()

        scanners = {
            "1h": {"BTC/USDT": _FakeScanner1h()},
            "mtf": {"BTC/USDT": _FakeScannerMtf()},
        }
        engine = SimpleNamespace(evaluate=_fake_evaluate)
        result = advisor_loop.analyze_symbol(
            symbol="BTC/USDT",
            scanners=scanners,
            engine=engine,
            gate=_FakeGate(),
            advisor=_FakeAdvisor(),
            shadow=_FakeShadow(),
            watchdog=_FakeWatchdog(),
            memory=memory,
            cycle=1,
            mistake_memory=mistake_memory,
            runtime=_FakeRuntime(),
        )
    finally:
        reset_authority()
    return result, captured


class TestAdvisorIntegrationUsesResolvedFlag:
    def test_effective_false_all_three_subsystems_passive(self, monkeypatch):
        """Test requis #6 — flag effectif False (dérivé de l'environnement
        via le résolveur public) : MistakeMemory non appliqué + trigger_count
        non incrémenté, StrategyMemory record_usage=False, MetaLearner non
        appliqué."""
        import core.advisor_loop as advisor_loop

        monkeypatch.delenv("FEATURE_ADAPTIVE_DECISION_FEEDBACK", raising=False)
        effective = flags.adaptive_decision_feedback_enabled()
        assert effective is False

        mm = _CountingMistakeMemory()
        memory = _CountingStrategyMemoryStore()
        result, captured = _run_analyze_symbol_with_effective_flag(
            effective, mm, memory, monkeypatch
        )

        # MistakeMemory : match visible (contrefactuel) mais non appliqué.
        assert result["trade_allowed"] is True
        assert "mistake_mem" not in result["blockers"]
        assert mm.count_as_applied_block_calls == [False]
        assert mm.applied_trigger_count == 0, (
            "trigger_count (compteur APPLIQUÉ) ne doit pas s'incrémenter "
            "quand le flag effectif est False"
        )

        # StrategyMemoryStore : lecture toujours possible, usage non enregistré.
        assert memory.record_usage_calls == [False]
        assert captured["memory_sharpe"] is None

        # MetaLearner : la recommandation n'est jamais appliquée aux
        # paramètres réels quand le flag effectif est False.
        ml_decision = {"exit_type": "hybrid", "tp": 0.05, "sl": 0.02, "trail_pct": 0.01}
        personality = SimpleNamespace(tp_pct=0.04, sl_pct=0.02, trailing_pct=0.0)
        tp, sl, trailing, applied = advisor_loop.resolve_meta_learner_exit_params(
            ml_decision, personality, effective
        )
        assert applied is False
        assert (tp, sl, trailing) == (0.04, 0.02, 0.0)

    def test_effective_true_legacy_application_restored(self, monkeypatch):
        """Test requis #7 — flag effectif True (dérivé de l'environnement) :
        comportement legacy restauré pour les trois subsystèmes."""
        import core.advisor_loop as advisor_loop

        monkeypatch.setenv("FEATURE_ADAPTIVE_DECISION_FEEDBACK", "true")
        effective = flags.adaptive_decision_feedback_enabled()
        assert effective is True

        mm = _CountingMistakeMemory()
        memory = _CountingStrategyMemoryStore()
        result, captured = _run_analyze_symbol_with_effective_flag(
            effective, mm, memory, monkeypatch
        )

        assert result["trade_allowed"] is False
        assert "mistake_mem" in result["blockers"]
        assert mm.count_as_applied_block_calls == [True]
        assert mm.applied_trigger_count == 1

        assert memory.record_usage_calls == [True]
        assert captured["memory_sharpe"] == 1.8

        ml_decision = {"exit_type": "hybrid", "tp": 0.05, "sl": 0.02, "trail_pct": 0.01}
        personality = SimpleNamespace(tp_pct=0.04, sl_pct=0.02, trailing_pct=0.0)
        tp, sl, trailing, applied = advisor_loop.resolve_meta_learner_exit_params(
            ml_decision, personality, effective
        )
        assert applied is True
        assert (tp, sl, trailing) == (0.05, 0.02, 0.01)
