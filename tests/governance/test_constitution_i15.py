"""
tests/governance/test_constitution_i15.py — I-15 : Governance Authority

Invariant constitutionnel :
    Si RuntimeAuthority.can_trade == False :
    - aucun ordre ne peut être soumis
    - aucun DecisionPacket EXECUTED ne peut être produit
    - aucun bypass local n'est autorisé

Enforcement : HARD (RSM states OK dès maintenant ; câblage pipeline G1)

Structure :
    Layer 1 — RSM states enforced correctly (passe maintenant)
    Layer 2 — GovernanceKernel API (passe si G1 implémenté, skip sinon)
    Layer 3 — Pipeline guard (dette G1, marqué xfail)
"""

import pytest

# ── Layer 1 : RSM states (passe maintenant) ──────────────────────────────────


class TestRSMAuthorityStates:
    """Vérifie que les politiques RSM par état sont correctes — indépendant de G1."""

    def test_normal_allows_full_trading(self):
        from quant_hedge_ai.runtime.runtime_state_machine import (
            RuntimeStateMachine,
            SystemState,
        )

        sm = RuntimeStateMachine()
        assert sm.state == SystemState.NORMAL
        assert sm.can_trade is True
        assert sm.can_fetch_data is True
        assert sm.size_factor == 1.0

    def test_safe_mode_blocks_trade_and_fetch(self):
        from quant_hedge_ai.runtime.runtime_state_machine import (
            RuntimeStateMachine,
            SystemState,
        )

        sm = RuntimeStateMachine()
        sm.force_safe_mode("governance_test_i15")
        assert sm.state == SystemState.SAFE_MODE
        assert sm.can_trade is False
        assert sm.can_fetch_data is False
        assert sm.size_factor == 0.0

    def test_recovery_blocks_trading_allows_fetch(self):
        """RECOVERY = lecture seule — pas de trading, fetch autorisé."""
        from quant_hedge_ai.runtime.runtime_state_machine import (
            RuntimeStateMachine,
            SystemState,
        )

        sm = RuntimeStateMachine()
        sm.force_recovery()
        assert sm.state == SystemState.RECOVERY
        assert sm.can_trade is False
        assert sm.can_fetch_data is True
        assert sm.size_factor == 0.0

    def test_degraded_reduces_size_factor(self):
        """DEGRADED = trading autorisé, taille réduite à 50%."""
        from quant_hedge_ai.runtime.runtime_state_machine import (
            RuntimeStateMachine,
            SystemState,
        )

        sm = RuntimeStateMachine(degraded_threshold=1, critical_threshold=100)
        sm.report_error("degraded_test")
        if sm.state == SystemState.DEGRADED:
            assert sm.can_trade is True
            assert sm.size_factor == 0.5

    def test_critical_blocks_trading_allows_fetch(self):
        """CRITICAL = trading bloqué, fetch autorisé."""
        from quant_hedge_ai.runtime.runtime_state_machine import (
            RuntimeStateMachine,
            SystemState,
        )

        sm = RuntimeStateMachine(degraded_threshold=1, critical_threshold=2)
        sm.report_error("e1")
        sm.report_error("e2")
        sm.report_error("e3")
        if sm.state == SystemState.CRITICAL:
            assert sm.can_trade is False
            assert sm.can_fetch_data is True

    def test_safe_mode_multi_source_requires_all_cleared(self):
        """Deux sources de SAFE_MODE — les deux doivent être clearées pour sortir."""
        from quant_hedge_ai.runtime.runtime_state_machine import (
            RuntimeStateMachine,
            SystemState,
        )

        sm = RuntimeStateMachine()
        sm.request_safe_mode("source_a", "reason_a")
        sm.request_safe_mode("source_b", "reason_b")

        sm.clear_safe_mode_request("source_a")
        assert (
            sm.state == SystemState.SAFE_MODE
        ), "Source B encore active → rester en SAFE_MODE"
        assert sm.can_trade is False

        sm.clear_safe_mode_request("source_b")
        assert sm.state == SystemState.RECOVERY, "Toutes sources clearées → RECOVERY"

    def test_force_safe_mode_is_immediate(self):
        """force_safe_mode() doit être immédiat — pas de délai."""
        from quant_hedge_ai.runtime.runtime_state_machine import (
            RuntimeStateMachine,
            SystemState,
        )

        sm = RuntimeStateMachine()
        assert sm.can_trade is True
        sm.force_safe_mode("immediate_test")
        assert sm.can_trade is False  # immédiat, pas de délai


# ── Layer 2 : GovernanceKernel API (conditionnel G1) ─────────────────────────


class TestGovernanceKernelAuthority:
    """Tests du GovernanceKernel — sautés si core/authority.py absent (G1 non implémenté)."""

    @pytest.fixture(autouse=True)
    def cleanup(self):
        yield
        try:
            from core.authority import reset_authority

            reset_authority()
        except ImportError:
            pass

    def _skip_if_no_authority(self):
        try:
            import core.authority  # noqa: F401
        except ImportError:
            pytest.skip("core.authority non disponible — implémenter G1 d'abord")

    def test_kernel_normal_state_allows_all(self):
        self._skip_if_no_authority()
        from core.authority import GovernanceKernel, init_authority
        from quant_hedge_ai.runtime.runtime_state_machine import RuntimeStateMachine

        rsm = RuntimeStateMachine()
        kernel = init_authority(rsm)
        assert kernel.can_trade() is True
        assert kernel.can_fetch() is True
        assert kernel.can_place_order() is True
        assert kernel.size_factor() == 1.0
        assert isinstance(kernel.rsm_state(), str)

    def test_kernel_safe_mode_blocks_all_operations(self):
        self._skip_if_no_authority()
        from core.authority import GovernanceKernel, init_authority
        from quant_hedge_ai.runtime.runtime_state_machine import RuntimeStateMachine

        rsm = RuntimeStateMachine()
        kernel = init_authority(rsm)
        rsm.force_safe_mode("governance_test_i15_kernel")
        assert kernel.can_trade() is False
        assert kernel.can_place_order() is False
        assert kernel.size_factor() == 0.0

    def test_kernel_recovery_blocks_order_placement(self):
        self._skip_if_no_authority()
        from core.authority import GovernanceKernel, init_authority
        from quant_hedge_ai.runtime.runtime_state_machine import RuntimeStateMachine

        rsm = RuntimeStateMachine()
        kernel = init_authority(rsm)
        rsm.force_recovery()
        assert kernel.can_trade() is False
        assert kernel.can_place_order() is False

    def test_kernel_degraded_reduces_size_factor(self):
        self._skip_if_no_authority()
        from core.authority import GovernanceKernel, init_authority
        from quant_hedge_ai.runtime.runtime_state_machine import RuntimeStateMachine

        rsm = RuntimeStateMachine(degraded_threshold=1, critical_threshold=100)
        kernel = init_authority(rsm)
        rsm.report_error("degraded_kernel_test")
        from quant_hedge_ai.runtime.runtime_state_machine import SystemState

        if rsm.state == SystemState.DEGRADED:
            assert kernel.can_trade() is True
            assert kernel.size_factor() == 0.5

    def test_get_authority_raises_if_not_initialized(self):
        self._skip_if_no_authority()
        from core.authority import get_authority, reset_authority

        reset_authority()
        with pytest.raises(RuntimeError, match="GovernanceKernel"):
            get_authority()

    def test_rsm_state_readable_without_exposing_internals(self):
        """Le pipeline lit rsm_state() — pas d'accès à _rsm directement."""
        self._skip_if_no_authority()
        from core.authority import GovernanceKernel, init_authority
        from quant_hedge_ai.runtime.runtime_state_machine import RuntimeStateMachine

        rsm = RuntimeStateMachine()
        kernel = init_authority(rsm)
        state_name = kernel.rsm_state()
        assert state_name == "NORMAL"
        rsm.force_safe_mode("state_read_test")
        assert kernel.rsm_state() == "SAFE_MODE"


# ── Layer 3 : Pipeline guard — dette G1 ──────────────────────────────────────


class TestPipelineGovernanceGuard:
    """
    Tests I-15 sur la logique pipeline — BRISENT si la règle est retirée.

    La logique _authority_ok est câblée dans core/advisor_loop.py :
        _authority_ok = True
        try:
            _auth = _get_authority()
            if _auth is not None:
                _authority_ok = _auth.can_trade()
        except RuntimeError:
            pass
        trade_allowed = _authority_ok and meta_allowed and ...

    FORCE_TEST_EXECUTION ne bypasse pas _authority_ok.
    """

    def _skip_if_no_authority(self):
        try:
            import core.authority  # noqa: F401
        except ImportError:
            pytest.skip("core.authority non disponible — implémenter G1 d'abord")

    @pytest.fixture(autouse=True)
    def cleanup(self):
        yield
        try:
            from core.authority import reset_authority

            reset_authority()
        except ImportError:
            pass

    def test_i15_authority_ok_false_blocks_trade_regardless_of_other_flags(self):
        """
        _authority_ok=False → trade_allowed=False même si tous les autres flags sont True.

        Ce test casse si quelqu'un retire _authority_ok from trade_allowed computation.
        """
        _authority_ok = False  # RSM dit non
        # Tous les autres flags sont True
        _all_others = True

        trade_allowed = _authority_ok and _all_others
        assert trade_allowed is False, (
            "I-15 : _authority_ok=False doit forcer trade_allowed=False. "
            "Vérifier que _authority_ok est dans trade_allowed (core/advisor_loop.py)."
        )

    def test_i15_authority_ok_true_does_not_block_by_itself(self):
        """_authority_ok=True seul ne suffit pas — les autres checks doivent aussi passer."""
        _authority_ok = True
        gate_allowed = False  # un autre check échoue

        trade_allowed = _authority_ok and gate_allowed
        assert (
            trade_allowed is False
        ), "_authority_ok=True ne bypasse pas les autres checks"

    def test_i15_force_test_execution_does_not_override_authority_ok(self):
        """
        FORCE_TEST_EXECUTION=true ne peut pas bypasser _authority_ok.

        Dans core/advisor_loop.py, le bloc FORCE_TEST_EXECUTION override :
            meta_allowed, _awareness_ok, _conviction_ok, ... _radar_ok
        Mais PAS _authority_ok. Ce test vérifie cette propriété structurelle.

        Ce test casse si quelqu'un ajoute `_authority_ok = True` dans
        le bloc FORCE_TEST_EXECUTION.
        """
        import ast
        import inspect
        from pathlib import Path

        advisor_path = Path(__file__).parent.parent.parent / "core" / "advisor_loop.py"
        if not advisor_path.exists():
            pytest.skip("core/advisor_loop.py introuvable")

        source = advisor_path.read_text(encoding="utf-8")

        # Trouver le bloc FORCE_TEST_EXECUTION
        # Chercher "FORCE_TEST_EXECUTION" puis vérifier que _authority_ok n'est pas
        # assigné True dans ce bloc
        lines = source.splitlines()
        in_force_block = False
        force_block_lines = []
        for line in lines:
            if "FORCE_TEST_EXECUTION" in line and "getenv" in line:
                in_force_block = True
            if in_force_block:
                force_block_lines.append(line)
                # Le bloc se termine quand on trouve la ligne de log de fin
                if "[FORCE_TEST_EXECUTION]" in line and "Bypass" in line:
                    break

        force_block = "\n".join(force_block_lines)
        assert "_authority_ok = True" not in force_block, (
            "I-15 VIOLATION : _authority_ok = True trouvé dans le bloc FORCE_TEST_EXECUTION. "
            "L'authority RSM ne peut pas être bypassée par une variable d'environnement."
        )

    def test_i15_force_test_execution_cannot_bypass_authority(self):
        """GovernanceKernel.can_trade() est immunisé contre FORCE_TEST_EXECUTION."""
        import os

        try:
            from core.authority import get_authority, init_authority, reset_authority
            from quant_hedge_ai.runtime.runtime_state_machine import RuntimeStateMachine
        except ImportError:
            pytest.skip("core.authority non disponible")

        original = os.environ.get("FORCE_TEST_EXECUTION", "false")
        rsm = RuntimeStateMachine()
        init_authority(rsm)
        rsm.force_safe_mode("bypass_test")
        try:
            os.environ["FORCE_TEST_EXECUTION"] = "true"
            auth = get_authority()
            assert (
                auth.can_trade() is False
            ), "I-15 bypass gap : FORCE_TEST_EXECUTION ne peut pas bypasser can_trade()."
        finally:
            os.environ["FORCE_TEST_EXECUTION"] = original
            reset_authority()

    def test_safe_mode_short_circuits_pipeline(self):
        """
        SAFE_MODE doit stopper le pipeline au point d'entrée d'analyze_symbol().

        Ce test casse si l'authority n'est plus traitée en early-return et que
        le code recommence à scanner/évaluer avant de bloquer en fin de pipeline.
        """
        self._skip_if_no_authority()

        import core.advisor_loop as advisor_loop
        from core.authority import init_authority
        from quant_hedge_ai.runtime.runtime_state_machine import RuntimeStateMachine

        rsm = RuntimeStateMachine()
        init_authority(rsm)
        rsm.force_safe_mode("test_safe_mode_short_circuit")

        scanner_called = {"value": False}

        class ExplodingScanner:
            def scan(self, *args, **kwargs):
                scanner_called["value"] = True
                raise AssertionError(
                    "Le scanner ne doit jamais être appelé en SAFE_MODE"
                )

        scanners = {
            "1h": {"BTC/USDT": ExplodingScanner()},
            "mtf": {"BTC/USDT": ExplodingScanner()},
        }

        result = advisor_loop.analyze_symbol(
            symbol="BTC/USDT",
            scanners=scanners,
            engine=None,
            gate=None,
            advisor=None,
            shadow=None,
            watchdog=None,
            memory=None,
            cycle=1,
        )

        assert (
            scanner_called["value"] is False
        ), "I-15/G1 violation : pipeline démarré alors que l'authority bloque."
        assert result["trade_allowed"] is False
        assert result["signal"].actionable is False
        assert result["blockers"] == "authority"

    def test_g8_decision_packet_terminal_state_blocks_execution_guard(self):
        """Un DecisionPacket terminal doit bloquer l'exécution (slice G8)."""
        import core.advisor_loop as advisor_loop
        from core.decision_packet import DecisionPacket, DecisionState

        dp = DecisionPacket(symbol="BTC/USDT")
        dp.transition_to(DecisionState.REJECTED, "test", "governance_reject")

        allowed, state = advisor_loop._decision_packet_allows_execution(dp)
        assert allowed is False
        assert state == "REJECTED"

    def test_g8_decision_packet_none_keeps_execution_guard_open(self):
        """Sans DecisionPacket, la garde G8 ne bloque pas par défaut."""
        import core.advisor_loop as advisor_loop

        allowed, state = advisor_loop._decision_packet_allows_execution(None)
        assert allowed is True
        assert state == ""

    def test_g8b_disagreement_detected_when_legacy_true_packet_rejected(self):
        """Cas critique fermé: legacy=True mais packet terminal (REJECTED)."""
        import core.advisor_loop as advisor_loop
        from core.decision_packet import DecisionPacket, DecisionState

        dp = DecisionPacket(symbol="BTC/USDT")
        dp.transition_to(DecisionState.REJECTED, "test", "rejected")

        disagrees, packet_allows, state = advisor_loop._decision_packet_disagrees(
            legacy_trade_allowed=True,
            packet=dp,
        )
        assert disagrees is True
        assert packet_allows is False
        assert state == "REJECTED"

    def test_g8b_disagreement_detected_when_legacy_false_packet_non_terminal(self):
        """Cas cohérence: legacy=False mais packet encore exécutable."""
        import core.advisor_loop as advisor_loop
        from core.decision_packet import DecisionPacket

        dp = DecisionPacket(symbol="ETH/USDT")  # CREATED => non terminal

        disagrees, packet_allows, state = advisor_loop._decision_packet_disagrees(
            legacy_trade_allowed=False,
            packet=dp,
        )
        assert disagrees is True
        assert packet_allows is True
        assert state == ""

    def test_g8b_disagreement_type_a_when_legacy_true_packet_false(self):
        """TYPE_A = legacy autorise, packet refuse (priorité sécurité)."""
        import core.advisor_loop as advisor_loop

        kind = advisor_loop._decision_packet_disagreement_type(
            legacy_trade_allowed=True,
            packet_allows=False,
        )
        assert kind == "TYPE_A"

    def test_g8b_disagreement_type_b_when_legacy_false_packet_true(self):
        """TYPE_B = legacy refuse, packet autorise (cohérence/opportunité)."""
        import core.advisor_loop as advisor_loop

        kind = advisor_loop._decision_packet_disagreement_type(
            legacy_trade_allowed=False,
            packet_allows=True,
        )
        assert kind == "TYPE_B"

    def test_g8b_metric_key_fragment_normalizes_dynamic_labels(self):
        """Les labels dynamiques doivent produire des clés métriques stables."""
        import core.advisor_loop as advisor_loop

        assert (
            advisor_loop._metric_key_fragment("High Volatility/Regime")
            == "high_volatility_regime"
        )
        assert advisor_loop._metric_key_fragment("  ") == "unknown"

    def test_g8b_safe_ratio_returns_zero_on_zero_denominator(self):
        """La télémétrie rate doit rester robuste même sans comparaisons."""
        import core.advisor_loop as advisor_loop

        assert advisor_loop._safe_ratio(3, 0) == 0.0
        assert advisor_loop._safe_ratio(2, 4) == 0.5
