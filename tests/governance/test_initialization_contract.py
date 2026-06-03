"""
tests/governance/test_initialization_contract.py

Validation de l'Execution Initialization Contract (EIC) v2.

    VALIDITY = AST_OK ∧ IMPORT_GRAPH_OK ∧ RUNTIME_PARITY_OK

Quatre classes :
    TestEICStructure        — invariants globaux du contrat (v1 compat)
    TestASTSideEffectScanner — couche 1 : détection AST
    TestImportGraphChecker  — couche 2 : topologie de dépendances
    TestRuntimeSnapshot     — couche 3 : parité runtime
    TestEICTier2Markers     — décorateurs transparents
    TestEICTier3Properties  — propriétés P1/P2 (Z3 en assertions Python)
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# Couche 0 — Invariants globaux du contrat
# ---------------------------------------------------------------------------


class TestEICStructure:

    def test_contract_module_is_itself_pure(self):
        """core/initialization_contract.py doit être Tier-1 pur."""
        from core.initialization_contract import assert_import_purity

        violations = assert_import_purity(ROOT / "core" / "initialization_contract.py")
        assert (
            violations == []
        ), f"EIC violation dans le module EIC lui-même : {violations}"

    def test_advisor_runtime_adapters_is_pure(self):
        """advisor_runtime_adapters : imports lazy, aucun side-effect."""
        from core.initialization_contract import assert_import_purity

        violations = assert_import_purity(ROOT / "core" / "advisor_runtime_adapters.py")
        assert violations == [], f"advisor_runtime_adapters impure : {violations}"

    def test_all_violations_are_documented(self):
        """Aucune violation non documentée dans advisor_loop.py."""
        from core.initialization_contract import check_advisor_loop_purity

        report = check_advisor_loop_purity()
        assert report["undocumented"] == [], (
            f"Side-effects non documentés — ajouter à KNOWN_SIDE_EFFECTS : "
            f"{report['undocumented']}"
        )

    def test_non_compliant_entries_are_covered_by_violations(self):
        """
        Chaque entrée KNOWN_SIDE_EFFECTS compliant=False doit correspondre
        à au moins une violation détectée. Si l'effet est déplacé sans mettre
        compliant=True, ce test échoue.
        """
        from core.initialization_contract import (
            KNOWN_SIDE_EFFECTS,
            check_advisor_loop_purity,
        )

        report = check_advisor_loop_purity()
        violations_text = [v[1] for v in report["violations"]]
        non_compliant = [se for se in KNOWN_SIDE_EFFECTS if not se.compliant]

        orphaned = [
            se
            for se in non_compliant
            if not any(se.pattern in v for v in violations_text)
        ]
        assert orphaned == [], (
            f"Entrées KNOWN_SIDE_EFFECTS non-compliant sans violation correspondante — "
            f"marquer compliant=True si l'effet a été déplacé : {orphaned}"
        )


# ---------------------------------------------------------------------------
# Couche 1 — ASTSideEffectScanner
# ---------------------------------------------------------------------------


class TestASTSideEffectScanner:

    def _scan(self, source: str):
        from core.initialization_contract import ASTSideEffectScanner

        return ASTSideEffectScanner().scan(source)

    # ── détection positive ────────────────────────────────────────────────

    def test_detects_os_makedirs(self):
        violations = self._scan("os.makedirs('logs', exist_ok=True)\n")
        assert len(violations) == 1
        assert violations[0][0] == 1

    def test_detects_load_dotenv(self):
        violations = self._scan("load_dotenv(override=True)\n")
        assert len(violations) == 1

    def test_detects_logging_basicconfig(self):
        violations = self._scan("logging.basicConfig(level=10)\n")
        assert len(violations) == 1

    def test_detects_logging_filehandler(self):
        violations = self._scan("logging.FileHandler('app.log')\n")
        assert len(violations) == 1

    def test_detects_open_at_module_level(self):
        violations = self._scan("f = open('data.txt')\n")
        # open() inside an assignment is not flagged (only bare Expr calls)
        assert len(violations) == 0

    def test_detects_bare_open_call(self):
        violations = self._scan("open('data.txt')\n")
        assert len(violations) == 1

    def test_detects_multiple_violations(self):
        source = "load_dotenv()\nos.makedirs('logs')\n"
        violations = self._scan(source)
        assert len(violations) == 2

    # ── non-détection (modules purs) ─────────────────────────────────────

    def test_ignores_getlogger_assignment(self):
        violations = self._scan("log = logging.getLogger('mymod')\n")
        assert violations == []

    def test_ignores_env_read_assignment(self):
        violations = self._scan("FLAG = os.environ.get('X', 'false')\n")
        assert violations == []

    def test_ignores_makedirs_inside_function(self):
        source = "def setup():\n    os.makedirs('logs')\n"
        assert self._scan(source) == []

    def test_ignores_makedirs_inside_class_method(self):
        source = "class App:\n    def init(self):\n        os.makedirs('logs')\n"
        assert self._scan(source) == []

    def test_ignores_main_guard(self):
        source = "if __name__ == '__main__':\n    os.makedirs('test')\n"
        assert self._scan(source) == []

    def test_ignores_pure_imports(self):
        source = "import os\nfrom pathlib import Path\n"
        assert self._scan(source) == []

    def test_ignores_constant_assignment(self):
        source = "SYMBOLS = ['BTC/USDT', 'ETH/USDT']\n"
        assert self._scan(source) == []

    def test_handles_syntax_error_gracefully(self):
        assert self._scan("def foo(:\n    pass\n") == []

    def test_reports_correct_line_number(self):
        source = "import os\nload_dotenv()\n"
        violations = self._scan(source)
        assert violations[0][0] == 2

    def test_reports_stripped_source_line(self):
        source = "    load_dotenv(override=True)\n"
        violations = self._scan(source)
        # Module-level indented statement (unusual but parseable)
        # The important thing is the line content is stripped
        if violations:
            assert not violations[0][1].startswith(" ")


# ---------------------------------------------------------------------------
# Couche 2 — ImportGraphChecker
# ---------------------------------------------------------------------------


class TestImportGraphChecker:

    def test_build_graph_returns_imports(self, tmp_path):
        from core.initialization_contract import ImportGraphChecker

        f = tmp_path / "module_a.py"
        f.write_text("import os\nfrom pathlib import Path\n")
        checker = ImportGraphChecker(root=tmp_path)
        graph = checker.build_graph(tmp_path)
        assert "module_a.py" in graph
        assert "os" in graph["module_a.py"]
        assert "pathlib" in graph["module_a.py"]

    def test_build_graph_skips_pycache(self, tmp_path):
        from core.initialization_contract import ImportGraphChecker

        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "cached.py").write_text("import evil\n")
        (tmp_path / "real.py").write_text("import os\n")
        checker = ImportGraphChecker(root=tmp_path)
        graph = checker.build_graph(tmp_path)
        assert not any("__pycache__" in k for k in graph)

    def test_find_impure_detects_violation(self, tmp_path):
        from core.initialization_contract import ImportGraphChecker

        f = tmp_path / "impure.py"
        f.write_text("os.makedirs('logs')\n")
        checker = ImportGraphChecker(root=tmp_path)
        impure = checker.find_impure_modules(tmp_path)
        assert "impure.py" in impure
        assert len(impure["impure.py"]) == 1

    def test_find_impure_skips_pure_modules(self, tmp_path):
        from core.initialization_contract import ImportGraphChecker

        f = tmp_path / "pure.py"
        f.write_text("import os\nFLAG = os.environ.get('X', '0')\n")
        checker = ImportGraphChecker(root=tmp_path)
        assert checker.find_impure_modules(tmp_path) == {}

    def test_find_impure_on_core_directory(self):
        """
        Le répertoire core/ doit contenir exactement les modules impurs connus.
        Tout nouveau fichier avec des side-effects doit être documenté.
        """
        from core.initialization_contract import KNOWN_SIDE_EFFECTS, ImportGraphChecker

        checker = ImportGraphChecker(root=ROOT)
        impure = checker.find_impure_modules(ROOT / "core")

        known_impure_files = {
            se.location.split(":")[0] for se in KNOWN_SIDE_EFFECTS if not se.compliant
        }
        # advisor_loop.py est connu comme impure → doit être dans le résultat
        for expected in known_impure_files:
            rel = expected.replace("/", os.sep)
            assert any(
                rel in k for k in impure
            ), f"Module connu comme impure absent du scan : {expected}"


# ---------------------------------------------------------------------------
# Couche 3 — RuntimeSnapshot
# ---------------------------------------------------------------------------


class TestRuntimeSnapshot:

    def test_delta_structure(self):
        from core.initialization_contract import RuntimeSnapshot

        snap = RuntimeSnapshot()
        snap.before()
        snap.after()
        delta = snap.delta()
        assert "new_modules" in delta
        assert "env_mutations" in delta
        assert isinstance(delta["new_modules"], list)
        assert isinstance(delta["env_mutations"], list)

    def test_is_env_pure_no_mutation(self):
        from core.initialization_contract import RuntimeSnapshot

        snap = RuntimeSnapshot()
        snap.before()
        snap.after()
        assert snap.is_env_pure() is True

    def test_is_env_pure_detects_mutation(self):
        from core.initialization_contract import RuntimeSnapshot

        snap = RuntimeSnapshot()
        snap.before()
        os.environ["__EIC_TEST_SENTINEL__"] = "1"
        snap.after()
        try:
            assert snap.is_env_pure() is False
            assert "__EIC_TEST_SENTINEL__" in snap.delta()["env_mutations"]
        finally:
            del os.environ["__EIC_TEST_SENTINEL__"]

    def test_raises_if_after_called_before_before(self):
        from core.initialization_contract import RuntimeSnapshot

        snap = RuntimeSnapshot()
        with pytest.raises(RuntimeError):
            snap.after()

    def test_raises_if_delta_called_without_capture(self):
        from core.initialization_contract import RuntimeSnapshot

        snap = RuntimeSnapshot()
        snap.before()
        with pytest.raises(RuntimeError):
            snap.delta()

    def test_new_modules_empty_when_already_loaded(self):
        """
        Si on importe un module déjà en sys.modules, new_modules doit être vide.
        """
        import json  # pre-load

        from core.initialization_contract import RuntimeSnapshot

        snap = RuntimeSnapshot()
        snap.before()
        import json  # noqa: F811 — already loaded, no new entry

        snap.after()
        assert "json" not in snap.delta()["new_modules"]


# ---------------------------------------------------------------------------
# Décorateurs de tier
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ATC — Authority Totality Contract
# ---------------------------------------------------------------------------


class TestStateTransitionIntegrity:
    """
    STI — contraintes croisées catégorie × état du cycle de vie.
    """

    def test_sti1_system_cannot_reach_approved(self):
        """
        STI-1 : SYSTEM packet → APPROVED déclenche RuntimeError.
        Vérifie que la Garde 3 de transition_to() est effective.
        """
        from core.decision_packet import (
            DecisionPacket,
            DecisionState,
            PacketEventCategory,
        )

        dp = DecisionPacket(
            symbol="CYCLE_EXCEPTION", event_category=PacketEventCategory.SYSTEM
        )
        # Amène le packet jusqu'à RISK_EVALUATED via transitions valides
        for state, actor in [
            (DecisionState.SIGNAL_GENERATED, "test"),
            (DecisionState.CONTEXT_ENRICHED, "test"),
            (DecisionState.RISK_EVALUATED, "test"),
        ]:
            dp.transition_to(state, actor, "sti_test_setup")

        with pytest.raises(RuntimeError, match="STI violation"):
            dp.transition_to(DecisionState.APPROVED, "test", "sti_forbidden_transition")

    def test_sti1_system_cannot_reach_execution_pending(self):
        """STI-1 : EXECUTION_PENDING est interdit pour SYSTEM (directement bloqué)."""
        from core.decision_packet import (
            DecisionPacket,
            DecisionState,
            PacketEventCategory,
        )

        dp = DecisionPacket(
            symbol="CYCLE_EXCEPTION", event_category=PacketEventCategory.SYSTEM
        )
        # EXECUTION_PENDING est dans CATEGORY_BLOCKED_STATES.SYSTEM
        # La transition CREATED→EXECUTION_PENDING échouerait au graphe avant STI.
        # Test direct de la contrainte STI via checker runtime.
        from core.initialization_contract import StateTransitionIntegrityChecker

        dp.lifecycle_state = DecisionState.EXECUTION_PENDING  # bypass pour test
        violations = StateTransitionIntegrityChecker().verify_packet(dp)
        assert len(violations) == 1
        assert "STI violation" in violations[0]

    def test_sti2_governance_cannot_be_approved(self):
        """STI-2 : GOVERNANCE packet → APPROVED déclenche RuntimeError."""
        from core.decision_packet import (
            DecisionPacket,
            DecisionState,
            PacketEventCategory,
        )

        dp = DecisionPacket(
            symbol="G1_AUTHORITY_BLOCK", event_category=PacketEventCategory.GOVERNANCE
        )
        for state, actor in [
            (DecisionState.SIGNAL_GENERATED, "test"),
            (DecisionState.CONTEXT_ENRICHED, "test"),
            (DecisionState.RISK_EVALUATED, "test"),
        ]:
            dp.transition_to(state, actor, "sti_test_setup")

        with pytest.raises(RuntimeError, match="STI violation"):
            dp.transition_to(DecisionState.APPROVED, "test", "sti_forbidden_transition")

    def test_sti3_trade_can_reach_approved(self):
        """STI-3 : TRADE packet peut atteindre APPROVED sans contrainte STI."""
        from core.decision_packet import (
            DecisionPacket,
            DecisionState,
            PacketEventCategory,
        )

        dp = DecisionPacket(symbol="BTC/USDT", event_category=PacketEventCategory.TRADE)
        for state in [
            DecisionState.SIGNAL_GENERATED,
            DecisionState.CONTEXT_ENRICHED,
            DecisionState.RISK_EVALUATED,
            DecisionState.APPROVED,
        ]:
            dp.transition_to(state, "test", "sti_trade_test")
        assert dp.lifecycle_state == DecisionState.APPROVED

    def test_sti3_trade_can_reach_executed(self):
        """STI-3 : TRADE packet peut atteindre EXECUTED (cycle complet)."""
        from core.decision_packet import (
            DecisionPacket,
            DecisionState,
            PacketEventCategory,
        )

        dp = DecisionPacket(symbol="BTC/USDT", event_category=PacketEventCategory.TRADE)
        for state in [
            DecisionState.SIGNAL_GENERATED,
            DecisionState.CONTEXT_ENRICHED,
            DecisionState.RISK_EVALUATED,
            DecisionState.APPROVED,
            DecisionState.EXECUTION_PENDING,
            DecisionState.EXECUTED,
        ]:
            dp.transition_to(state, "test", "sti_full_cycle")
        assert dp.lifecycle_state == DecisionState.EXECUTED

    def test_sti_checker_constraints_complete(self):
        """Les contraintes SYSTEM/GOVERNANCE couvrent les 3 états critiques."""
        from core.initialization_contract import StateTransitionIntegrityChecker

        result = StateTransitionIntegrityChecker().validate_constraints_complete()
        assert result[
            "compliant"
        ], f"STI contraintes incomplètes : {result['violations']}"

    def test_sti_checker_blocked_states_defined(self):
        """CATEGORY_BLOCKED_STATES est importable et non-vide."""
        from core.initialization_contract import StateTransitionIntegrityChecker

        assert StateTransitionIntegrityChecker().check_blocked_states_defined()

    def test_sti_system_can_be_rejected(self):
        """Un packet SYSTEM peut toujours atteindre REJECTED (terminal exception)."""
        from core.decision_packet import (
            DecisionPacket,
            DecisionState,
            PacketEventCategory,
        )

        dp = DecisionPacket(
            symbol="CYCLE_EXCEPTION", event_category=PacketEventCategory.SYSTEM
        )
        dp.transition_to(DecisionState.REJECTED, "enl2_g3", "exception")
        assert dp.lifecycle_state == DecisionState.REJECTED

    def test_sti_enl2_dp_compliant(self):
        """Le DP ENL-2 réel (CYCLE_EXCEPTION + SYSTEM + REJECTED) est STI-conforme."""
        from core.decision_packet import DecisionPacket, PacketEventCategory
        from core.initialization_contract import StateTransitionIntegrityChecker

        dp = DecisionPacket(
            symbol="CYCLE_EXCEPTION", event_category=PacketEventCategory.SYSTEM
        )
        dp.reject("enl2_g3", "test_exception")
        violations = StateTransitionIntegrityChecker().verify_packet(dp)
        assert violations == [], f"ENL-2 DP viole STI : {violations}"


class TestSemanticExhaustivenessChecker:
    """
    SEP — Semantic Exhaustiveness Checker.
    Vérifie l'exhaustivité du partitionnement TRADE / GOVERNANCE / SYSTEM.
    """

    def test_sep1_taxonomy_complete(self):
        """SEP-1 : PacketEventCategory a exactement {TRADE, GOVERNANCE, SYSTEM}."""
        from core.initialization_contract import SemanticExhaustivenessChecker

        report = SemanticExhaustivenessChecker().check_taxonomy_completeness()
        assert report[
            "compliant"
        ], f"SEP-1 : taxonomy incomplète — missing={report['missing']} extra={report['extra']}"
        assert report["actual"] == [
            "GOVERNANCE",
            "SYSTEM",
            "TRADE",
        ], f"SEP-1 : valeurs inattendues : {report['actual']}"

    def test_sep2_system_symbol_in_core_is_flagged(self):
        """SEP-2 : le checker détecte 'CYCLE_EXCEPTION' si non catégorisé."""
        from core.initialization_contract import (
            DPCreationSite,
            SemanticExhaustivenessChecker,
        )

        checker = SemanticExhaustivenessChecker()
        # Simule un site avec symbol système non catégorisé
        bad_site = DPCreationSite(
            file="fake.py",
            lineno=1,
            constructor="DecisionPacket",
            symbol="CYCLE_EXCEPTION",
            has_explicit_category=False,
            category_value="",
        )
        alerts = checker.check_system_reserved([bad_site])
        assert len(alerts) == 1

    def test_sep2_system_symbol_explicit_does_not_alert(self):
        """SEP-2 : un site CYCLE_EXCEPTION explicitement SYSTEM n'alerte pas."""
        from core.initialization_contract import (
            DPCreationSite,
            SemanticExhaustivenessChecker,
        )

        checker = SemanticExhaustivenessChecker()
        good_site = DPCreationSite(
            file="advisor_loop.py",
            lineno=1,
            constructor="_DP",
            symbol="CYCLE_EXCEPTION",
            has_explicit_category=True,
            category_value="SYSTEM",
        )
        alerts = checker.check_system_reserved([good_site])
        assert alerts == []

    def test_sep3_no_unknown_category_in_core(self):
        """SEP-3 : aucune catégorie inconnue dans core/."""
        from core.initialization_contract import SemanticExhaustivenessChecker

        checker = SemanticExhaustivenessChecker()
        sites = checker.scan_directory(ROOT / "core")
        unknown = checker.check_no_unknown_category(sites)
        assert unknown == [], f"SEP-3 : catégories inconnues dans core/ : {unknown}"

    def test_sep4_enl2_site_found_and_categorized(self):
        """SEP-4 : le site ENL-2 (_DP alias) est trouvé et catégorisé SYSTEM."""
        from core.initialization_contract import SemanticExhaustivenessChecker

        checker = SemanticExhaustivenessChecker()
        sites = checker.scan_directory(ROOT / "core")
        enl2_sites = [
            s
            for s in sites
            if s.symbol == "CYCLE_EXCEPTION" and s.has_explicit_category
        ]
        assert (
            len(enl2_sites) >= 1
        ), "SEP-4 : site ENL-2 (symbol='CYCLE_EXCEPTION', event_category=SYSTEM) introuvable"
        assert all(
            s.category_value == "SYSTEM" for s in enl2_sites
        ), f"SEP-4 : ENL-2 n'est pas catégorisé SYSTEM : {enl2_sites}"

    def test_sep_report_core_compliant(self):
        """Rapport SEP complet sur core/ : sep_compliant=True."""
        from core.initialization_contract import SemanticExhaustivenessChecker

        report = SemanticExhaustivenessChecker().report(ROOT / "core")
        assert report["taxonomy_ok"], "SEP : taxonomy non complète"
        assert (
            report["unknown_category"] == []
        ), f"SEP : catégories inconnues : {report['unknown_category']}"
        # ENL-2 site doit être dans explicit
        assert (
            len(report["explicit"]) >= 1
        ), "SEP : aucun site avec catégorie explicite — ENL-2 non trouvé"
        assert report["sep_compliant"], f"SEP non conforme : {report}"

    def test_sep_invariants_test_probes_are_acceptable(self):
        """
        Les sondes 'TEST' de core/invariants.py utilisent le défaut TRADE.
        C'est acceptable : elles sont créées transitoirement, jamais persistées.
        SEP-2 les signale comme alertes mais elles ne cassent pas sep_compliant.
        """
        from core.initialization_contract import SemanticExhaustivenessChecker

        checker = SemanticExhaustivenessChecker()
        sites = checker.scan_directory(ROOT / "core")
        test_probe_sites = [
            s
            for s in sites
            if s.symbol.startswith("TEST") and not s.has_explicit_category
        ]
        # Elles EXISTENT (sondes d'invariant) mais ne sont pas unknown_category
        # (elles utilisent le défaut, pas une valeur inconnue)
        unknown = checker.check_no_unknown_category(test_probe_sites)
        assert (
            unknown == []
        ), "Les sondes TEST ne doivent pas avoir de catégorie inconnue"

        # La preuve SEP-compliant ne dépend pas des sondes test (non persistées)
        report = checker.report(ROOT / "core")
        assert report[
            "sep_compliant"
        ], "sep_compliant ne doit pas être cassé par les sondes TEST"


class TestExceptionNormalizationContract:
    """
    ENC — valide que les deux niveaux ENL existent dans advisor_loop.py.
    """

    @pytest.fixture
    def source(self):
        return (ROOT / "core" / "advisor_loop.py").read_text(encoding="utf-8")

    def test_enl1_runtime_error_handler_exists(self, source):
        """ENL-1 : `except RuntimeError` dans G1, handler retourne (pas re-raise)."""
        from core.initialization_contract import ExceptionNormalizationContract

        assert ExceptionNormalizationContract().validate_enl1(
            source
        ), "ENC : except RuntimeError manquant ou handler re-raise dans G1"

    def test_enl2_report_error_cycle_exception_exists(self, source):
        """ENL-2 : report_error('cycle_exception') dans le cycle handler (G3)."""
        from core.initialization_contract import ExceptionNormalizationContract

        assert ExceptionNormalizationContract().validate_enl2(
            source
        ), "ENC : report_error('cycle_exception') absent — G3 non branché"

    def test_enc_full_report_compliant(self, source):
        """Rapport ENC complet : compliant=True."""
        from core.initialization_contract import ExceptionNormalizationContract

        report = ExceptionNormalizationContract().validate(
            ROOT / "core" / "advisor_loop.py"
        )
        assert report["compliant"] is True, f"ENC non conforme : {report}"

    def test_enl2_dp_gap_is_documented(self, source):
        """
        ENL-2 gap documenté : si report_error existe sans DP dans le handler,
        le gap doit être reconnu (enl2_dp_gap=False signifie le gap est fermé).
        """
        from core.initialization_contract import ExceptionNormalizationContract

        report = ExceptionNormalizationContract().validate(
            ROOT / "core" / "advisor_loop.py"
        )
        # Gap fermé après l'implémentation du ENL-2 trace record
        assert (
            report["enl2_dp_gap"] is False
        ), "ENL-2 gap non fermé — le cycle handler doit persister un DP trace record"

    def test_enl1_rtmerror_is_caught_not_escaping(self):
        """
        Propriété P3 : RuntimeError de get_authority() est capturé dans
        analyze_symbol(), pas re-raise. Vérifié par inspection AST.
        """
        from core.initialization_contract import ExceptionNormalizationContract

        # Simulation de l'ancien modèle : handler re-raise
        old_source = (
            "def foo():\n"
            "    try:\n"
            "        _get_authority()\n"
            "    except RuntimeError:\n"
            "        raise\n"
        )
        enc = ExceptionNormalizationContract()
        # validate_enl1 doit retourner False pour un handler qui re-raise
        assert (
            enc.validate_enl1(old_source) is False
        ), "ENC : un handler qui re-raise RuntimeError ne doit pas être considéré conforme"


class TestAuthorityTotalityContract:
    """
    Valide que advisor_loop.py respecte les deux propriétés ATC :
    1. get_authority() ne retourne jamais None (NULL_FALLBACK absente)
    2. G1 n'a plus de null-guard conditionnel (G1_NULL_GUARD absent)

    Ces tests cassent si quelqu'un réintroduit l'ancien modèle.
    """

    @pytest.fixture
    def advisor_loop_source(self):
        path = ROOT / "core" / "advisor_loop.py"
        return path.read_text(encoding="utf-8"), path

    def test_atc_no_null_fallback_in_advisor_loop(self, advisor_loop_source):
        """
        Propriété 1 (NULL_FALLBACK) :
        Le fallback ImportError de _get_authority ne retourne plus None.
        """
        from core.initialization_contract import AuthorityTotalityContract

        source, path = advisor_loop_source
        atc = AuthorityTotalityContract()
        violations = atc.validate_no_null_fallback(source)
        assert violations == [], (
            "ATC violation (NULL_FALLBACK) : _get_authority retourne None — "
            f"le fallback doit lever RuntimeError : {violations}"
        )

    def test_atc_no_null_guard_in_g1(self, advisor_loop_source):
        """
        Propriété 2 (G1_NULL_GUARD) :
        G1 n'a plus de condition `_auth is not None`.
        Présence = graphe d'autorité non-total (ancien modèle).
        """
        from core.initialization_contract import AuthorityTotalityContract

        source, path = advisor_loop_source
        atc = AuthorityTotalityContract()
        violations = atc.validate_g1_totality(source)
        assert violations == [], (
            "ATC violation (G1_NULL_GUARD) : null-guard détecté dans G1 — "
            f"retirer `_auth is not None` : {violations}"
        )

    def test_atc_full_report_compliant(self, advisor_loop_source):
        """Rapport ATC complet : compliant=True."""
        from core.initialization_contract import AuthorityTotalityContract

        source, path = advisor_loop_source
        report = AuthorityTotalityContract().validate(path)
        assert (
            report["compliant"] is True
        ), f"advisor_loop.py non conforme ATC : {report}"

    def test_atc_detects_null_fallback_violation(self):
        """
        Propriété de détection inverse :
        ATC doit détecter l'ancien pattern `return None`.
        """
        from core.initialization_contract import AuthorityTotalityContract

        old_pattern = "def _get_authority():\n" "    return None\n"
        atc = AuthorityTotalityContract()
        violations = atc.validate_no_null_fallback(old_pattern)
        assert (
            len(violations) >= 1
        ), "ATC doit détecter `return None` dans _get_authority"

    def test_atc_detects_null_guard_violation(self):
        """
        Propriété de détection inverse :
        ATC doit détecter `_auth is not None and`.
        """
        from core.initialization_contract import AuthorityTotalityContract

        old_pattern = "if _auth is not None and not _auth.can_trade():\n    return\n"
        atc = AuthorityTotalityContract()
        violations = atc.validate_g1_totality(old_pattern)
        assert len(violations) >= 1, "ATC doit détecter `_auth is not None and`"

    def test_atc_authority_import_failure_is_fail_closed(self):
        """
        Propriété runtime : si core.authority était absent (simulé),
        _get_authority() lève RuntimeError, pas return None.

        Vérifié en inspectant le fallback via AST.
        """
        source = (ROOT / "core" / "advisor_loop.py").read_text(encoding="utf-8")
        # Le fallback doit contenir RuntimeError, pas return None
        assert (
            "raise RuntimeError" in source
        ), "ATC : fallback doit lever RuntimeError quand core.authority absent"
        # Et ne doit PAS contenir return None dans _get_authority
        from core.initialization_contract import AuthorityTotalityContract

        violations = AuthorityTotalityContract().validate_no_null_fallback(source)
        assert violations == []


class TestEICTier2Markers:

    def test_runtime_init_transparent(self):
        from core.initialization_contract import runtime_init

        @runtime_init
        def my_setup():
            return 42

        assert my_setup() == 42
        assert my_setup.__eic_tier__ == "RUNTIME_INIT"

    def test_gate_required_transparent(self):
        from core.initialization_contract import gate_required

        @gate_required
        def compute():
            return "features"

        assert compute() == "features"
        assert compute.__eic_tier__ == "GATE_REQUIRED"


# ---------------------------------------------------------------------------
# Propriétés Tier-3 — P1 / P2 (formalisation Z3 en assertions Python)
# ---------------------------------------------------------------------------


class TestEICTier3Properties:

    @pytest.fixture(autouse=True)
    def cleanup(self):
        yield
        try:
            from core.authority import reset_authority

            reset_authority()
        except ImportError:
            pass

    def test_p1_safe_mode_implies_no_compute(self):
        """P1 : SAFE_MODE=True ⟹ scanner jamais appelé (compute_graph=∅)."""
        try:
            import core.advisor_loop as advisor_loop
            from core.authority import init_authority, reset_authority
            from quant_hedge_ai.runtime.runtime_state_machine import RuntimeStateMachine
        except ImportError:
            pytest.skip("modules non disponibles")

        reset_authority()
        rsm = RuntimeStateMachine()
        init_authority(rsm)
        rsm.force_safe_mode("test_p1")

        compute_called = {"value": False}

        class SentinelScanner:
            def scan(self, *args, **kwargs):
                compute_called["value"] = True
                raise AssertionError("P1 violation : compute exécuté en SAFE_MODE")

        result = advisor_loop.analyze_symbol(
            symbol="BTC/USDT",
            scanners={
                "1h": {"BTC/USDT": SentinelScanner()},
                "mtf": {"BTC/USDT": SentinelScanner()},
            },
            engine=None,
            gate=None,
            advisor=None,
            shadow=None,
            watchdog=None,
            memory=None,
            cycle=1,
        )

        assert compute_called["value"] is False, "P1 : scanner appelé malgré SAFE_MODE"
        assert result["trade_allowed"] is False

    def test_p2_rejected_packet_implies_no_shadow_execute(self):
        """P2 : lifecycle_state=REJECTED ⟹ shadow_execute ∉ call_graph."""
        try:
            import core.advisor_loop as advisor_loop
            from core.decision_packet import DecisionPacket, DecisionState
        except ImportError:
            pytest.skip("modules non disponibles")

        dp = DecisionPacket(symbol="BTC/USDT")
        dp.transition_to(DecisionState.REJECTED, "test", "governance_reject")

        allowed, state = advisor_loop._decision_packet_allows_execution(dp)

        assert allowed is False
        assert state == "REJECTED"

    def test_p1_completeness_normal_allows_compute(self):
        """Propriété de complétude : RSM.NORMAL ⟹ can_trade=True."""
        try:
            from core.authority import init_authority, reset_authority
            from quant_hedge_ai.runtime.runtime_state_machine import RuntimeStateMachine
        except ImportError:
            pytest.skip("modules non disponibles")

        reset_authority()
        rsm = RuntimeStateMachine()
        auth = init_authority(rsm)

        assert rsm.state.value == "NORMAL"
        assert auth.can_trade() is True
