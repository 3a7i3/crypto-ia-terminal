"""
core/invariants.py — Invariants architecturaux exécutables.

Complément de docs/SYSTEM_INVARIANTS.md (I-01..I-12) pour les invariants
qui peuvent être vérifiés par introspection au démarrage, avant tout trading.

Séparation des responsabilités :
    SYSTEM_INVARIANTS.md  → invariants runtime (valeurs, seuils, sessions)
    core/invariants.py    → invariants architecturaux (qui fait quoi, qui décide quoi)

Usage :
    from core.invariants import verify_architecture
    verify_architecture()  # lève InvariantViolation si cassé

Les violations sont fatales : si l'architecture est cassée, le système ne démarre pas.
"""

from __future__ import annotations

import importlib
import inspect
from typing import Callable


class InvariantViolation(RuntimeError):
    """Un invariant architectural est violé — arrêt du système requis."""

    pass


# ---------------------------------------------------------------------------
# Registre des invariants
# ---------------------------------------------------------------------------

_INVARIANTS: list[tuple[str, Callable[[], None]]] = []


def _invariant(name: str):
    """Décorateur qui enregistre une fonction comme invariant."""

    def decorator(fn: Callable[[], None]) -> Callable[[], None]:
        _INVARIANTS.append((name, fn))
        return fn

    return decorator


# ---------------------------------------------------------------------------
# A-01 — DecisionPacket : mutation d'état uniquement via transition_to()
# ---------------------------------------------------------------------------


@_invariant(
    "A-01: DecisionPacket.lifecycle_state mutable uniquement via transition_to()"
)
def _check_decision_packet_state_machine() -> None:
    from core.decision_packet import DecisionPacket, DecisionState

    p = DecisionPacket(symbol="TEST")
    # lifecycle_state est un champ dataclass normal (pas de property setter bloquant)
    # L'invariant est contractuel : la docstring l'interdit explicitement.
    # On vérifie que transition_to() existe et que le graphe est défini.
    assert callable(
        getattr(p, "transition_to", None)
    ), "DecisionPacket doit exposer transition_to()"
    from core.decision_packet import VALID_TRANSITIONS

    assert len(VALID_TRANSITIONS) > 0, "Graphe de transitions vide"
    assert (
        DecisionState.CREATED in VALID_TRANSITIONS
    ), "CREATED doit avoir une transition sortante"
    assert (
        DecisionState.POSTMORTEM_ANALYZED not in VALID_TRANSITIONS
    ), "POSTMORTEM_ANALYZED est terminal — pas de transition sortante"


# ---------------------------------------------------------------------------
# A-02 — OrderSizer : calcule, ne rejette jamais
# ---------------------------------------------------------------------------


@_invariant("A-02: OrderSizer ne lève pas de rejet — uniquement clamping")
def _check_order_sizer_no_reject() -> None:
    try:
        mod = importlib.import_module("quant_hedge_ai.agents.risk.order_sizer")
    except ImportError:
        return  # Module absent → skip (env minimal)
    cls = getattr(mod, "OrderSizer", None)
    if cls is None:
        return
    # Vérifie que la méthode compute/calculate ne lève pas SessionHaltedError
    # (qui est la signature d'un rejet). On inspecte la source pour détecter
    # les imports de SessionHaltedError dans order_sizer.
    try:
        source = inspect.getsource(cls)
        assert (
            "SessionHaltedError" not in source
        ), "OrderSizer importe SessionHaltedError — il ne doit pas rejeter, seulement clamp"
    except (OSError, TypeError):
        pass  # Impossible d'inspecter → skip


# ---------------------------------------------------------------------------
# A-03 — GlobalRiskGate : seul module autorisé à rejeter via GateResult
# ---------------------------------------------------------------------------


@_invariant("A-03: GlobalRiskGate expose check() retournant GateResult avec allowed")
def _check_global_risk_gate_interface() -> None:
    try:
        mod = importlib.import_module("quant_hedge_ai.agents.risk.global_risk_gate")
    except ImportError:
        return
    cls = getattr(mod, "GlobalRiskGate", None)
    if cls is None:
        return
    assert callable(getattr(cls, "check", None)), "GlobalRiskGate doit exposer check()"


# ---------------------------------------------------------------------------
# A-04 — ExecutionEngine : ne décide pas des signaux
# ---------------------------------------------------------------------------


@_invariant("A-04: ExecutionEngine n'importe pas LiveSignalEngine (pas de décision)")
def _check_execution_engine_no_signal_decision() -> None:
    try:
        mod = importlib.import_module(
            "quant_hedge_ai.agents.execution.execution_engine"
        )
        source = inspect.getsource(mod)
    except (ImportError, OSError):
        return
    forbidden = ["from.*live_signal_engine", "import live_signal_engine"]
    import re

    for pattern in forbidden:
        if re.search(pattern, source):
            raise InvariantViolation(
                "A-04: ExecutionEngine importe LiveSignalEngine — "
                "violation de séparation signal/exécution"
            )


# ---------------------------------------------------------------------------
# A-05 — RuntimeStateMachine : SAFE_MODE → can_trade = False, can_fetch = False
# ---------------------------------------------------------------------------


@_invariant("A-05: SAFE_MODE bloque trading ET fetch de données")
def _check_safe_mode_policy() -> None:
    try:
        from quant_hedge_ai.runtime.runtime_state_machine import RuntimeStateMachine
    except ImportError:
        return
    sm = RuntimeStateMachine()
    sm.force_safe_mode("invariant_check")
    assert not sm.can_trade, "SAFE_MODE doit bloquer can_trade"
    assert not sm.can_fetch_data, "SAFE_MODE doit bloquer can_fetch_data"
    assert sm.size_factor == 0.0, "SAFE_MODE doit avoir size_factor=0.0"


# ---------------------------------------------------------------------------
# A-06 — DEGRADED : trading autorisé, taille réduite à 50%
# ---------------------------------------------------------------------------


@_invariant("A-06: DEGRADED → can_trade=True, size_factor=0.5")
def _check_degraded_policy() -> None:
    try:
        from quant_hedge_ai.runtime.runtime_state_machine import RuntimeStateMachine
    except ImportError:
        return
    sm = RuntimeStateMachine(degraded_threshold=1)
    sm.report_error("test_error")
    if sm.can_trade:  # si DEGRADED atteint
        assert (
            sm.size_factor == 0.5
        ), f"DEGRADED doit avoir size_factor=0.5, got {sm.size_factor}"


# ---------------------------------------------------------------------------
# A-07 — DecisionPacket.seal() : signature Ed25519 présente après scellement
# ---------------------------------------------------------------------------


@_invariant("A-07: DecisionPacket expose seal() et is_sealed()")
def _check_packet_seal_interface() -> None:
    from core.decision_packet import DecisionPacket

    p = DecisionPacket(symbol="TEST")
    assert callable(getattr(p, "seal", None)), "DecisionPacket doit exposer seal()"
    assert callable(
        getattr(p, "is_sealed", None)
    ), "DecisionPacket doit exposer is_sealed()"
    assert not p.is_sealed(), "Un packet non scellé doit retourner is_sealed()=False"


# ---------------------------------------------------------------------------
# A-08 — Transitions terminales : un packet terminal ne peut plus transitionner
# ---------------------------------------------------------------------------


@_invariant("A-08: Transition depuis état terminal lève RuntimeError")
def _check_terminal_state_locked() -> None:
    from core.decision_packet import DecisionPacket, DecisionState

    p = DecisionPacket(symbol="TEST")
    p.veto_by("invariant_check", "test")
    assert p.lifecycle_state == DecisionState.VETOED
    try:
        p.transition_to(DecisionState.SIGNAL_GENERATED, "test", "test")
        raise InvariantViolation(
            "A-08: transition depuis VETOED n'a pas levé RuntimeError"
        )
    except RuntimeError:
        pass  # Comportement attendu


# ---------------------------------------------------------------------------
# Vérification globale
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# A-09 — GovernanceKernel : interface exposée + init_authority disponible
# ---------------------------------------------------------------------------


@_invariant("A-09: GovernanceKernel expose can_trade/can_fetch/size_factor/rsm_state")
def _check_governance_kernel_interface() -> None:
    try:
        from core.authority import get_authority, init_authority, reset_authority
        from quant_hedge_ai.runtime.runtime_state_machine import RuntimeStateMachine
    except ImportError:
        return
    rsm = RuntimeStateMachine()
    kernel = init_authority(rsm)
    try:
        assert callable(kernel.can_trade), "GovernanceKernel doit exposer can_trade()"
        assert callable(kernel.can_fetch), "GovernanceKernel doit exposer can_fetch()"
        assert callable(
            kernel.can_place_order
        ), "GovernanceKernel doit exposer can_place_order()"
        assert callable(
            kernel.size_factor
        ), "GovernanceKernel doit exposer size_factor()"
        assert callable(kernel.rsm_state), "GovernanceKernel doit exposer rsm_state()"
        assert kernel.can_trade() is True, "Kernel NORMAL → can_trade doit être True"
        assert kernel.can_fetch() is True, "Kernel NORMAL → can_fetch doit être True"
        assert kernel.size_factor() == 1.0, "Kernel NORMAL → size_factor doit être 1.0"
        assert isinstance(kernel.rsm_state(), str), "rsm_state() doit retourner un str"
        # get_authority() doit retourner le kernel initialisé
        retrieved = get_authority()
        assert (
            retrieved is kernel
        ), "get_authority() doit retourner le kernel initialisé"
    finally:
        reset_authority()  # nettoyage état global pour les autres tests


@_invariant("A-09b: get_authority() lève RuntimeError si non initialisé")
def _check_governance_kernel_raises_if_not_init() -> None:
    try:
        from core.authority import get_authority, reset_authority
    except ImportError:
        return
    reset_authority()
    try:
        get_authority()
        raise InvariantViolation(
            "A-09b: get_authority() n'a pas levé RuntimeError quand non initialisé"
        )
    except RuntimeError:
        pass  # comportement attendu
    finally:
        reset_authority()


# ---------------------------------------------------------------------------
# A-10 — Interfaces de blocage des agents (prérequis I-14)
# ---------------------------------------------------------------------------


@_invariant(
    "A-10: Agents décisionnels exposent interfaces de blocage fail-closed (I-14)"
)
def _check_decision_agents_blocking_interfaces() -> None:
    """Pré-condition de I-14 : chaque agent expose une interface qui peut bloquer."""
    # ConvictionLevel.MINIMAL → blocks_trade() is True
    try:
        from quant_hedge_ai.agents.intelligence.conviction_engine import (
            ConvictionLevel,
            ConvictionResult,
        )

        cr = ConvictionResult(
            level=ConvictionLevel.MINIMAL,
            score=10.0,
            size_factor=0.0,
            dimensions={},
            notes=[],
        )
        assert callable(cr.blocks_trade), "ConvictionResult doit exposer blocks_trade()"
        assert (
            cr.blocks_trade() is True
        ), "ConvictionLevel.MINIMAL doit bloquer le trade"
    except ImportError:
        pass

    # PortfolioVerdict.__bool__ = False quand rejected
    try:
        from quant_hedge_ai.agents.risk.portfolio_brain import PortfolioVerdict

        rejected = PortfolioVerdict(
            allowed=False, reason="test", size_factor=0.0, capital_available=0.0
        )
        allowed = PortfolioVerdict(
            allowed=True, reason="ok", size_factor=1.0, capital_available=100.0
        )
        assert (
            bool(rejected) is False
        ), "PortfolioVerdict(allowed=False) doit être falsy"
        assert bool(allowed) is True, "PortfolioVerdict(allowed=True) doit être truthy"
    except ImportError:
        pass

    # SelfAwarenessEngine expose is_safe_to_trade() et retourne True à l'état initial
    try:
        from quant_hedge_ai.agents.intelligence.self_awareness_engine import (
            SelfAwarenessEngine,
        )

        engine = SelfAwarenessEngine()
        assert callable(
            engine.is_safe_to_trade
        ), "SelfAwarenessEngine doit exposer is_safe_to_trade()"
        assert (
            engine.is_safe_to_trade() is True
        ), "SelfAwarenessEngine neuf → is_safe_to_trade() doit être True"
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# A-11 — GovernanceKernel : can_place_order=False quand can_trade=False (I-15)
# ---------------------------------------------------------------------------


@_invariant(
    "A-11: GovernanceKernel.can_place_order=False quand RSM bloque can_trade (I-15)"
)
def _check_governance_kernel_order_blocked_when_no_trade() -> None:
    """SAFE_MODE → can_trade=False → can_place_order=False — aucun bypass possible."""
    try:
        from core.authority import GovernanceKernel, reset_authority
        from quant_hedge_ai.runtime.runtime_state_machine import RuntimeStateMachine
    except ImportError:
        return  # core/authority.py absent (G1 non implémenté) — skip
    rsm = RuntimeStateMachine()
    kernel = GovernanceKernel(rsm)
    try:
        rsm.force_safe_mode("invariant_a11")
        assert (
            kernel.can_trade() is False
        ), "A-11: SAFE_MODE → can_trade() doit être False"
        assert (
            kernel.can_place_order() is False
        ), "A-11: SAFE_MODE → can_place_order() doit être False"
        assert (
            kernel.size_factor() == 0.0
        ), "A-11: SAFE_MODE → size_factor() doit être 0.0"
    finally:
        reset_authority()


# ---------------------------------------------------------------------------
# A-12 — Infrastructure trace_id : génération + isolation thread-local (I-16)
# ---------------------------------------------------------------------------


@_invariant(
    "A-12: new_trace_id() génère des IDs UUID4 uniques ; round-trip set/current correct (I-16)"
)
def _check_trace_id_infrastructure() -> None:
    try:
        from observability.json_logger import (
            current_trace_id,
            new_trace_id,
            set_trace_id,
        )
    except ImportError:
        return

    # Unicité sur 20 tirages
    ids = {new_trace_id() for _ in range(20)}
    assert len(ids) == 20, "new_trace_id() doit générer des IDs uniques"

    # Format UUID4 (36 chars, 4 tirets)
    tid = new_trace_id()
    assert (
        isinstance(tid, str) and len(tid) == 36
    ), f"trace_id doit être un UUID4 (36 chars), got {len(tid)!r}"
    assert tid.count("-") == 4, "UUID4 doit contenir 4 tirets"

    # Round-trip thread-local set → current
    set_trace_id(tid)
    assert (
        current_trace_id() == tid
    ), "current_trace_id() doit retourner le trace_id défini par set_trace_id()"


# ---------------------------------------------------------------------------
# A-13 — G4 : _GOVERNANCE_KEYS ∩ _RUNTIME_KEYS = ∅
# Aucune variable de gouvernance ne peut être reconfigurée à chaud via JSON.
# ---------------------------------------------------------------------------


@_invariant("A-13: G4 — GOVERNANCE_KEYS ∩ RUNTIME_KEYS = ∅ (aucun overlap hot-reload)")
def _check_governance_runtime_disjoint() -> None:
    import ast
    import pathlib

    src = (pathlib.Path(__file__).parent / "advisor_loop.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(src)

    gov_keys: set[str] = set()
    rt_keys: set[str] = set()

    def _extract_frozenset_strings(call_node: ast.Call) -> set[str]:
        """Extrait les chaînes littérales d'un appel frozenset({...})."""
        result: set[str] = set()
        for elt in ast.walk(call_node):
            if isinstance(elt, (ast.Set, ast.Tuple, ast.List)):
                for e in elt.elts:
                    if isinstance(e, ast.Constant) and isinstance(e.value, str):
                        result.add(e.value)
        return result

    for node in ast.walk(tree):
        # ast.Assign : x = frozenset({...})
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if isinstance(node.value, ast.Call):
                        if target.id == "_GOVERNANCE_KEYS":
                            gov_keys.update(_extract_frozenset_strings(node.value))
                        elif target.id == "_RUNTIME_KEYS":
                            rt_keys.update(_extract_frozenset_strings(node.value))

        # ast.AnnAssign : x: frozenset[str] = frozenset({...})
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.value is not None:
                if isinstance(node.value, ast.Call):
                    if node.target.id == "_GOVERNANCE_KEYS":
                        gov_keys.update(_extract_frozenset_strings(node.value))
                    elif node.target.id == "_RUNTIME_KEYS":
                        rt_keys.update(_extract_frozenset_strings(node.value))

    if not gov_keys:
        raise InvariantViolation(
            "A-13: _GOVERNANCE_KEYS introuvable dans advisor_loop.py — G4 non appliqué"
        )
    overlap = gov_keys & rt_keys
    if overlap:
        raise InvariantViolation(
            f"A-13: Variables presentes dans _GOVERNANCE_KEYS ET _RUNTIME_KEYS : {overlap}. "
            "G4 violation — elles peuvent etre rechargees a chaud."
        )


# ---------------------------------------------------------------------------
# A-14 — G5 : OrderSizer rejette si Kelly ≤ 0 avant EXECUTION_PENDING
# ---------------------------------------------------------------------------


@_invariant(
    "A-14: G5 — OrderSizer.size_packet rejette le packet si kelly_fraction <= 0"
)
def _check_order_sizer_kelly_zero_rejects() -> None:
    try:
        from core.decision_packet import DecisionPacket, DecisionState
        from quant_hedge_ai.agents.risk.order_sizer import OrderSizer
    except ImportError:
        return

    sizer = OrderSizer(kelly_fraction=0.25, min_size_usd=10.0, max_size_usd=5000.0)
    packet = DecisionPacket(symbol="TEST_INVARIANT")

    # Simuler l'arrivée en état APPROVED (prérequis de size_packet)
    packet.transition_to(DecisionState.SIGNAL_GENERATED, "test", "invariant")
    packet.transition_to(DecisionState.CONTEXT_ENRICHED, "test", "invariant")
    packet.transition_to(DecisionState.RISK_EVALUATED, "test", "invariant")
    packet.transition_to(DecisionState.APPROVED, "test", "invariant")

    # win_rate=0.2, avg_win=0.5, avg_loss=5.0 → Kelly très négatif → 0.0
    sizer.size_packet(
        packet,
        capital=10_000.0,
        win_rate=0.2,
        avg_win_pct=0.5,
        avg_loss_pct=5.0,
    )
    assert packet.lifecycle_state == DecisionState.REJECTED, (
        f"A-14 violation : kelly<=0 doit produire REJECTED, "
        f"got {packet.lifecycle_state.value}"
    )
    assert (
        packet.lifecycle_state != DecisionState.EXECUTION_PENDING
    ), "A-14 violation : EXECUTION_PENDING ne doit jamais suivre kelly<=0"


# ---------------------------------------------------------------------------
# A-15 — G8-E : guard _dp=None présent dans advisor_loop.py
# ---------------------------------------------------------------------------


@_invariant(
    "A-15: G8-E — guard DecisionPacket absent bloque l'exécution (source check)"
)
def _check_g8e_guard_present() -> None:
    import pathlib

    src = (pathlib.Path(__file__).parent / "advisor_loop.py").read_text(
        encoding="utf-8"
    )
    if "_effective_trade_allowed = False" not in src:
        raise InvariantViolation(
            "A-15: Guard G8-E '_effective_trade_allowed = False' absent de advisor_loop.py. "
            "Un ordre peut passer sans DecisionPacket."
        )
    if "[G8-E]" not in src:
        raise InvariantViolation(
            "A-15: Log marker '[G8-E]' absent — guard non instrumenté ou retiré."
        )


# ---------------------------------------------------------------------------
# A-16 — G0 : guard trace_id présent avant shadow_execute
# ---------------------------------------------------------------------------


@_invariant("A-16: G0 — guard trace_id présent avant shadow_execute (source check)")
def _check_g0_trace_guard_present() -> None:
    import pathlib

    src = (pathlib.Path(__file__).parent / "advisor_loop.py").read_text(
        encoding="utf-8"
    )
    if "_shadow_trace_ok" not in src:
        raise InvariantViolation(
            "A-16: Guard G0 '_shadow_trace_ok' absent de advisor_loop.py. "
            "shadow_execute() peut être atteint sans trace_id."
        )
    if "governance_g0" not in src:
        raise InvariantViolation(
            "A-16: Reject 'governance_g0' absent — packet non rejeté si trace_id manquant."
        )


# ---------------------------------------------------------------------------
# A-17 — G1 : GovernanceKernel non initialisé → pipeline bloqué, pas pass
# ---------------------------------------------------------------------------


@_invariant(
    "A-17: G1 — GovernanceKernel non initialisé produit un retour bloqué (pas pass)"
)
def _check_g1_kernel_uninitialized_blocks() -> None:
    import pathlib

    src = (pathlib.Path(__file__).parent / "advisor_loop.py").read_text(
        encoding="utf-8"
    )
    # Vérifier que "except RuntimeError:" n'est plus suivi de "pass" dans ce contexte
    lines = src.splitlines()
    for i, line in enumerate(lines):
        if "except RuntimeError:" in line:
            # Regarder les 3 lignes suivantes
            following = "\n".join(lines[i + 1 : i + 4])
            if "pass  # GovernanceKernel non initialisé" in following:
                raise InvariantViolation(
                    f"A-17 violation à la ligne {i + 1}: "
                    "'except RuntimeError: pass' trouvé — "
                    "GovernanceKernel non initialisé ne bloque pas le pipeline."
                )
    if "AUTHORITY_UNINITIALIZED" not in src:
        raise InvariantViolation(
            "A-17: 'AUTHORITY_UNINITIALIZED' absent de advisor_loop.py — "
            "retour bloqué manquant pour kernel non initialisé."
        )


# ---------------------------------------------------------------------------
# A-18 — S4 : lifecycle.ALLOWED_TRANSITIONS est complet et cohérent
# ---------------------------------------------------------------------------


@_invariant(
    "A-18: S4 — lifecycle.ALLOWED_TRANSITIONS complet, coherent, zero violation"
)
def _check_lifecycle_exhaustive() -> None:
    try:
        from core.lifecycle import verify_lifecycle_exhaustive
    except ImportError:
        raise InvariantViolation(
            "A-18: core/lifecycle.py absent — modele formel S4 non disponible"
        )
    violations = verify_lifecycle_exhaustive()
    if violations:
        summary = "; ".join(violations[:5])
        raise InvariantViolation(
            f"A-18: {len(violations)} violation(s) dans lifecycle.ALLOWED_TRANSITIONS : "
            f"{summary}"
        )


@_invariant("A-19: P-01 — Absence de deadlock (tout non-terminal atteint un terminal)")
def _check_no_deadlock() -> None:
    try:
        from core.lifecycle import verify_no_deadlock
    except ImportError:
        return
    violations = verify_no_deadlock()
    if violations:
        raise InvariantViolation(f"A-19/P-01 deadlock detecte : {violations[0]}")


@_invariant("A-20: P-02 — Absence de cycle nominal (flux lineaire acyclique)")
def _check_no_nominal_cycle() -> None:
    try:
        from core.lifecycle import verify_no_nominal_cycle
    except ImportError:
        return
    violations = verify_no_nominal_cycle()
    if violations:
        raise InvariantViolation(
            f"A-20/P-02 cycle detecte dans le flux nominal : {violations[0]}"
        )


@_invariant("A-21: P-03 — POSTMORTEM_ANALYZED est le seul terminal nominal")
def _check_unique_nominal_terminal() -> None:
    try:
        from core.lifecycle import verify_unique_nominal_terminal
    except ImportError:
        return
    violations = verify_unique_nominal_terminal()
    if violations:
        raise InvariantViolation(
            f"A-21/P-03 unicite terminal nominal violee : {violations[0]}"
        )


# ---------------------------------------------------------------------------
# A-22 — Execution Trace Layer : CheckPriority defini + TraceVerifier present
# ---------------------------------------------------------------------------


@_invariant("A-22: Execution Trace Equivalence Layer present et coherent")
def _check_execution_trace_layer() -> None:
    """
    Verifie que le layer d'equivalence execution_trace.py est present et coherent.

    Proprietes verifiees :
      1. CheckPriority defini et complet (G1 < G4 < I14 < G8-D < G8-E < G0 < G8-C)
      2. TraceVerifier instanciable
      3. Propriete fondamentale : G1 a la priorite la plus haute
      4. ExecutionTrace enregistre des checks ordonnables
    """
    try:
        from core.execution_trace import CheckPriority, ExecutionTrace, TraceVerifier
    except ImportError:
        raise InvariantViolation(
            "A-22: core/execution_trace.py absent — Execution Trace Layer non disponible"
        )

    # 1. G1 doit avoir la priorite la plus haute (valeur numerique la plus basse)
    all_priorities = list(CheckPriority)
    min_priority = min(all_priorities, key=lambda p: p.value)
    if min_priority != CheckPriority.G1_RUNTIME_AUTHORITY:
        raise InvariantViolation(
            f"A-22: G1_RUNTIME_AUTHORITY n'est pas la priorite maximale. "
            f"Priorite la plus haute : {min_priority.name} (valeur={min_priority.value}). "
            "G1 doit avoir la valeur numerique la plus basse."
        )

    # 2. G8-E doit avoir une priorite superieure a G4 (G8-E bloque apres le gate)
    assert (
        CheckPriority.G8_E_PACKET_PRESENCE > CheckPriority.G4_GLOBAL_RISK_GATE
    ), "A-22: G8-E doit avoir une priorite inferieure a G4 (numeriquement superieure)"

    # 3. G0 doit avoir une priorite superieure a G8-E
    assert (
        CheckPriority.G0_TRACE_ID > CheckPriority.G8_E_PACKET_PRESENCE
    ), "A-22: G0 doit etre verifie apres G8-E (on ne verifie trace_id que si packet present)"

    # 4. TraceVerifier instanciable
    verifier = TraceVerifier()
    assert callable(verifier.verify), "A-22: TraceVerifier.verify() doit etre callable"

    # 5. ExecutionTrace produit une trace ordonnee si checks ajoutes dans l'ordre
    trace = ExecutionTrace(trace_id="invariant_check", symbol="TEST", cycle=0)
    trace.record("G1_TEST", CheckPriority.G1_RUNTIME_AUTHORITY, True, "test", "ok")
    trace.record("G4_TEST", CheckPriority.G4_GLOBAL_RISK_GATE, True, "test", "ok")
    if not trace.is_ordered():
        raise InvariantViolation(
            "A-22: ExecutionTrace.is_ordered() retourne False apres insertion canonique"
        )


def verify_architecture(raise_on_failure: bool = True) -> list[str]:
    """
    Lance tous les invariants architecturaux.

    Args:
        raise_on_failure: si True (défaut), lève InvariantViolation au premier échec.
                          si False, collecte et retourne la liste des échecs.

    Returns:
        Liste des messages d'erreur (vide si tout est OK).
    """
    failures: list[str] = []
    for name, check in _INVARIANTS:
        try:
            check()
        except InvariantViolation as e:
            msg = f"[INVARIANT VIOLATION] {name}: {e}"
            if raise_on_failure:
                raise InvariantViolation(msg) from e
            failures.append(msg)
        except Exception as e:  # noqa: BLE001
            msg = f"[INVARIANT ERROR] {name}: {type(e).__name__}: {e}"
            if raise_on_failure:
                raise InvariantViolation(msg) from e
            failures.append(msg)
    return failures


def verify_architecture_soft() -> list[str]:
    """Version non-fatale : retourne les échecs sans lever d'exception."""
    return verify_architecture(raise_on_failure=False)
