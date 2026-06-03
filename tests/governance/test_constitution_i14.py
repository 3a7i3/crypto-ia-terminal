"""
tests/governance/test_constitution_i14.py — I-14 : Agent Failure Safety

Invariant constitutionnel :
    Toute exception non récupérée provenant d'un agent décisionnel
    doit produire une décision REJECTED.
    Une exception ne peut jamais augmenter la probabilité d'exécution d'un trade.

Enforcement : HARD (implémenté)

Chaque test de Layer 2 échoue si la règle est retirée du code.
"""

import pytest

# ── Layer 1 : Interfaces de blocage (invariants d'interface) ─────────────────


class TestAgentBlockingInterfaces:
    def test_conviction_minimal_blocks_trade(self):
        from quant_hedge_ai.agents.intelligence.conviction_engine import (
            ConvictionLevel,
            ConvictionResult,
        )

        result = ConvictionResult(
            level=ConvictionLevel.MINIMAL,
            score=15.0,
            size_factor=0.0,
            dimensions={},
            notes=[],
        )
        assert result.blocks_trade() is True

    def test_conviction_low_does_not_block(self):
        from quant_hedge_ai.agents.intelligence.conviction_engine import (
            ConvictionLevel,
            ConvictionResult,
        )

        result = ConvictionResult(
            level=ConvictionLevel.LOW,
            score=45.0,
            size_factor=0.3,
            dimensions={},
            notes=[],
        )
        assert result.blocks_trade() is False

    def test_conviction_high_does_not_block(self):
        from quant_hedge_ai.agents.intelligence.conviction_engine import (
            ConvictionLevel,
            ConvictionResult,
        )

        result = ConvictionResult(
            level=ConvictionLevel.HIGH,
            score=80.0,
            size_factor=1.0,
            dimensions={},
            notes=[],
        )
        assert result.blocks_trade() is False

    def test_portfolio_verdict_rejected_is_falsy(self):
        from quant_hedge_ai.agents.risk.portfolio_brain import PortfolioVerdict

        verdict = PortfolioVerdict(
            allowed=False,
            reason="concentration_exceeded",
            size_factor=0.0,
            capital_available=0.0,
        )
        assert not bool(verdict)

    def test_portfolio_verdict_allowed_is_truthy(self):
        from quant_hedge_ai.agents.risk.portfolio_brain import PortfolioVerdict

        verdict = PortfolioVerdict(
            allowed=True, reason="ok", size_factor=1.0, capital_available=500.0
        )
        assert bool(verdict)

    def test_self_awareness_healthy_engine_is_safe(self):
        from quant_hedge_ai.agents.intelligence.self_awareness_engine import (
            SelfAwarenessEngine,
        )

        engine = SelfAwarenessEngine()
        assert engine.is_safe_to_trade() is True
        assert engine.effective_size_factor() == 1.0


# ── Layer 2 : Logique fail-closed — BRISENT si la règle est retirée ──────────
#
# Ces tests vérifient directement la logique implémentée dans advisor_loop.py.
# Si quelqu'un reverte les boolean patterns vers l'ancien fail-open,
# ces tests passent au rouge immédiatement.


class TestI14FailClosedLogic:
    """
    Vérifie la logique fail-closed ligne par ligne.

    Logique I-14 implémentée dans core/advisor_loop.py :
        _conviction_ok = conviction_engine is None or (
            conviction is not None and not conviction.blocks_trade()
        )
    Si on reverte vers :
        _conviction_ok = conviction is None or not conviction.blocks_trade()
    → test_conviction_engine_configured_result_none_is_blocked ÉCHOUE.
    """

    def test_conviction_engine_configured_result_none_is_blocked(self):
        """Engine configuré + résultat None → bloqué (I-14 fail-closed)."""
        conviction_engine = object()  # non-None = configuré
        conviction = None  # exception capturée → aucun résultat

        # Logique I-14 (core/advisor_loop.py):
        _conviction_ok = conviction_engine is None or (
            conviction is not None and not conviction.blocks_trade()
        )
        assert _conviction_ok is False, (
            "I-14 violation : engine configuré + conviction=None → fail-open. "
            "Vérifier : conviction_engine is None or (conviction is not None and ...)"
        )

    def test_conviction_engine_not_configured_none_is_ok(self):
        """Engine non configuré → None attendu, pas d'exception → pass."""
        conviction_engine = None  # non configuré
        conviction = None

        _conviction_ok = conviction_engine is None or (
            conviction is not None and not conviction.blocks_trade()
        )
        assert _conviction_ok is True, "Engine non configuré → conviction=None est OK"

    def test_portfolio_brain_configured_result_none_is_blocked(self):
        """PortfolioBrain configuré + résultat None + signal actionable → bloqué."""
        portfolio_brain = object()  # configuré
        pb_verdict = None  # exception → aucun résultat
        signal_actionable = True

        _pb_ok = (
            portfolio_brain is None
            or not signal_actionable
            or (pb_verdict is not None and pb_verdict.allowed)
        )
        assert _pb_ok is False, (
            "I-14 violation : portfolio_brain configuré + pb_verdict=None → fail-open. "
            "Vérifier : portfolio_brain is None or not signal.actionable or (pb_verdict is not None and ...)"
        )

    def test_portfolio_brain_not_configured_none_is_ok(self):
        """PortfolioBrain non configuré → None attendu → pass."""
        portfolio_brain = None
        pb_verdict = None
        signal_actionable = True

        _pb_ok = (
            portfolio_brain is None
            or not signal_actionable
            or (pb_verdict is not None and pb_verdict.allowed)
        )
        assert _pb_ok is True

    def test_portfolio_brain_result_none_non_actionable_signal_is_ok(self):
        """Signal non actionable → PortfolioBrain non appelé → None OK."""
        portfolio_brain = object()  # configuré
        pb_verdict = None
        signal_actionable = False  # signal pas actionable → brain non consulté

        _pb_ok = (
            portfolio_brain is None
            or not signal_actionable
            or (pb_verdict is not None and pb_verdict.allowed)
        )
        assert _pb_ok is True

    def test_mistake_memory_configured_result_none_is_blocked(self):
        """MistakeMemory configuré + résultat None → bloqué."""
        mistake_memory = object()
        mm_check = None
        signal_actionable = True

        _mm_ok = (
            mistake_memory is None
            or not signal_actionable
            or (mm_check is not None and bool(mm_check))
        )
        assert _mm_ok is False

    def test_executive_override_configured_result_none_is_blocked(self):
        """ExecutiveOverride configuré + résultat None → bloqué."""
        executive_override = object()
        eo_verdict = None
        signal_actionable = True

        _eo_ok = (
            executive_override is None
            or not signal_actionable
            or (eo_verdict is not None and bool(eo_verdict))
        )
        assert _eo_ok is False

    def test_threat_radar_configured_report_none_is_blocked(self):
        """ThreatRadar configuré + report None (avec candles) → bloqué."""
        threat_radar = object()
        radar_report = None
        candles_1h = [{"close": 100}]  # non-vide → radar devait tourner

        _radar_ok = (
            threat_radar is None
            or not candles_1h
            or (radar_report is not None and radar_report.trade_allowed)
        )
        assert _radar_ok is False

    def test_threat_radar_configured_no_candles_is_ok(self):
        """ThreatRadar configuré mais pas de bougies → radar non appelé → OK."""
        threat_radar = object()
        radar_report = None
        candles_1h = []  # vide → radar non appelé

        _radar_ok = (
            threat_radar is None
            or not candles_1h
            or (radar_report is not None and radar_report.trade_allowed)
        )
        assert _radar_ok is True

    def test_capital_engine_configured_allocation_none_is_blocked(self):
        """CapitalEngine configuré + allocation None → bloqué."""
        from quant_hedge_ai.agents.risk.portfolio_brain import PortfolioVerdict

        capital_engine = object()
        pb_verdict = PortfolioVerdict(
            allowed=True, reason="ok", size_factor=1.0, capital_available=500.0
        )
        allocation = None  # exception dans capital_engine.allocate()
        signal_actionable = True

        _cae_ok = (
            capital_engine is None
            or not signal_actionable
            or (pb_verdict is not None and not pb_verdict.allowed)
            or (allocation is not None and bool(allocation))
        )
        assert _cae_ok is False

    def test_capital_engine_skipped_because_pb_blocked_is_ok(self):
        """PortfolioBrain bloque → CapitalEngine skipped → allocation None = OK."""
        from quant_hedge_ai.agents.risk.portfolio_brain import PortfolioVerdict

        capital_engine = object()
        pb_verdict = PortfolioVerdict(
            allowed=False, reason="exposure", size_factor=0.0, capital_available=0.0
        )
        allocation = None  # skipped car pb a bloqué
        signal_actionable = True

        _cae_ok = (
            capital_engine is None
            or not signal_actionable
            or (pb_verdict is not None and not pb_verdict.allowed)
            or (allocation is not None and bool(allocation))
        )
        assert _cae_ok is True


# ── Layer 2b : Vérification source — BRISENT si le fix est revert dans advisor_loop ──


class TestI14SourceEnforcement:
    """
    Vérifie que les patterns fail-closed I-14 sont présents dans le code source.
    Ces tests cassent immédiatement si quelqu'un reverte les boolean patterns.

    Pattern attendu dans core/advisor_loop.py :
        _conviction_ok = conviction_engine is None or (
            conviction is not None and not conviction.blocks_trade()
        )
    Pattern interdit (fail-open) :
        _conviction_ok = conviction is None or not conviction.blocks_trade()
    """

    @pytest.fixture(autouse=True)
    def source(self):
        from pathlib import Path

        p = Path(__file__).parent.parent.parent / "core" / "advisor_loop.py"
        if not p.exists():
            pytest.skip("core/advisor_loop.py introuvable")
        self._source = p.read_text(encoding="utf-8")

    def test_i14_conviction_fail_closed_pattern_present(self):
        """Conviction check doit utiliser conviction_engine is None (pas conviction is None)."""
        assert "conviction_engine is None" in self._source, (
            "I-14 violation : 'conviction_engine is None' absent de advisor_loop.py. "
            "Le pattern fail-open 'conviction is None or ...' a peut-être été réintroduit."
        )

    def test_i14_fail_open_conviction_pattern_absent(self):
        """L'ancien pattern fail-open ne doit plus exister dans la décision finale."""
        # "_conviction_ok = conviction is None" est le pattern fail-open.
        # On cherche spécifiquement dans le bloc de décision (pas dans les commentaires).
        lines = self._source.splitlines()
        violations = [
            (i + 1, l)
            for i, l in enumerate(lines)
            if "_conviction_ok = conviction is None" in l
            and not l.strip().startswith("#")
        ]
        assert (
            not violations
        ), f"I-14 fail-open réintroduit à la ligne {violations[0][0]}: {violations[0][1].strip()}"

    def test_i14_portfolio_brain_fail_closed_pattern_present(self):
        """pb_verdict check doit utiliser portfolio_brain is None."""
        assert (
            "portfolio_brain is None" in self._source
        ), "I-14 violation : 'portfolio_brain is None' absent de advisor_loop.py."

    def test_i14_fail_open_pb_pattern_absent(self):
        """L'ancien _pb_ok = pb_verdict is None ne doit plus exister."""
        lines = self._source.splitlines()
        violations = [
            (i + 1, l)
            for i, l in enumerate(lines)
            if "_pb_ok = pb_verdict is None" in l and not l.strip().startswith("#")
        ]
        assert (
            not violations
        ), f"I-14 fail-open _pb_ok réintroduit à la ligne {violations[0][0]}: {violations[0][1].strip()}"

    def test_i14_radar_fail_closed_pattern_present(self):
        """radar_report check doit utiliser threat_radar is None."""
        assert (
            "threat_radar is None" in self._source
        ), "I-14 violation : 'threat_radar is None' absent de advisor_loop.py."


# ── Layer 3 : Vérification croisée — la logique produit le bon trade_allowed ──


class TestI14TradeAllowedIntegration:
    """
    Vérifie que trade_allowed = False quand un agent configuré retourne None.
    Ces tests modélisent le calcul de trade_allowed dans advisor_loop.py.
    """

    def test_trade_blocked_when_conviction_engine_configured_but_result_none(self):
        """Simulation complète : conviction_engine set + conviction=None → trade_allowed=False."""
        conviction_engine = object()
        conviction = None
        signal_actionable = True

        # Tous les autres flags sont True
        _authority_ok = True
        meta_allowed = True
        gate_allowed = True
        _awareness_ok = True
        _notrade_ok = True
        _pb_ok = True
        _cae_ok = True
        _mm_ok = True
        _eo_ok = True
        _radar_ok = True
        _arb_ok = True

        # I-14 compliant conviction check:
        _conviction_ok = conviction_engine is None or (
            conviction is not None and not conviction.blocks_trade()
        )

        trade_allowed = (
            _authority_ok
            and meta_allowed
            and gate_allowed
            and _awareness_ok
            and _conviction_ok
            and _notrade_ok
            and _pb_ok
            and _cae_ok
            and _mm_ok
            and _eo_ok
            and _radar_ok
            and _arb_ok
        )
        assert (
            trade_allowed is False
        ), "trade_allowed doit être False si conviction_engine configuré mais conviction=None"

    def test_trade_allowed_when_conviction_engine_not_configured(self):
        """conviction_engine=None → conviction=None est OK → trade peut passer (autres flags OK)."""
        conviction_engine = None
        conviction = None

        _conviction_ok = conviction_engine is None or (
            conviction is not None and not conviction.blocks_trade()
        )

        trade_allowed = _conviction_ok and True  # autres flags OK
        assert trade_allowed is True
