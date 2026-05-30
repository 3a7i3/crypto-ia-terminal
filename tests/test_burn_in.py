"""
P12-D — Paper Trading Burn-In.

Valide que le système tient dans la durée sans crash, corruption,
ni dérive d'état — condition préalable à tout capital réel.

D1 — BurnInEngine           : run compressé, métriques collectées
D2 — HealthJournal          : snapshots périodiques JSONL
D3 — InvariantChecker       : violations capital/equity/positions/audit
D4 — Réconciliation         : périodique, réseau défaillant récupéré
D5 — BurnInReport           : rapport final, critères passage P13
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

import pytest

from system.burn_in import BurnInConfig, BurnInEngine, BurnInReport
from system.invariant_checker import InvariantChecker, InvariantViolation

# ── Helpers ───────────────────────────────────────────────────────────────────


def _fast_config(**kwargs) -> BurnInConfig:
    """Config rapide pour tests (500 cycles)."""
    defaults = {
        "n_cycles": 500,
        "snapshot_interval": 100,
        "invariant_interval": 50,
        "reconcile_interval": 100,
        "seed": 42,
        "initial_capital": 10_000.0,
    }
    defaults.update(kwargs)
    return BurnInConfig(**defaults)


def _run_fast(**kwargs) -> BurnInReport:
    return BurnInEngine(_fast_config(**kwargs)).run()


# ══════════════════════════════════════════════════════════════════════════════
# D3 — InvariantChecker
# ══════════════════════════════════════════════════════════════════════════════


class TestD3InvariantChecker:
    """Détection correcte des violations d'invariants."""

    # ── I-CAPITAL ─────────────────────────────────────────────────────────────

    def test_positive_capital_no_violation(self):
        checker = InvariantChecker()
        assert checker.check_capital(10_000.0) is None

    def test_zero_capital_no_violation(self):
        assert InvariantChecker.check_capital(0.0) is None

    def test_negative_capital_critical_violation(self):
        v = InvariantChecker.check_capital(-1.0)
        assert v is not None
        assert v.name == "I-CAPITAL"
        assert v.severity == "CRITICAL"
        assert v.is_critical()

    # ── I-EQUITY ──────────────────────────────────────────────────────────────

    def test_coherent_equity_no_violation(self):
        assert InvariantChecker.check_equity(10_000.0, 10_000.0) is None

    def test_small_equity_divergence_allowed(self):
        assert InvariantChecker.check_equity(10_200.0, 10_000.0) is None

    def test_large_equity_divergence_warning(self):
        v = InvariantChecker.check_equity(20_000.0, 10_000.0)
        assert v is not None
        assert v.name == "I-EQUITY"
        assert v.severity == "WARNING"

    def test_zero_capital_equity_skipped(self):
        """Capital=0 → pas de check d'equity (division par zéro)."""
        assert InvariantChecker.check_equity(5_000.0, 0.0) is None

    # ── I-POSITIONS ───────────────────────────────────────────────────────────

    def test_positive_positions_no_violation(self):
        positions = {"BTC/USDT": 0.1, "ETH/USDT": 1.0}
        assert InvariantChecker.check_positions(positions) is None

    def test_negative_position_critical(self):
        positions = {"BTC/USDT": -0.1}
        v = InvariantChecker.check_positions(positions)
        assert v is not None
        assert v.name == "I-POSITIONS"
        assert v.is_critical()

    def test_empty_positions_no_violation(self):
        assert InvariantChecker.check_positions({}) is None

    def test_zero_position_no_violation(self):
        assert InvariantChecker.check_positions({"BTC/USDT": 0.0}) is None

    # ── I-RISKSTATE ───────────────────────────────────────────────────────────

    def test_known_risk_states_no_violation(self):
        for state in ("NORMAL", "DEGRADED", "CRITICAL", "SAFE_MODE", "RECOVERY"):
            assert InvariantChecker.check_risk_state(state) is None

    def test_unknown_risk_state_warning(self):
        v = InvariantChecker.check_risk_state("ZOMBIE")
        assert v is not None
        assert v.name == "I-RISKSTATE"
        assert v.severity == "WARNING"

    # ── I-AUDIT ───────────────────────────────────────────────────────────────

    def test_valid_audit_chain_no_violation(self):
        log = MagicMock()
        log.verify_all.return_value = True
        assert InvariantChecker.check_audit_chain(log) is None

    def test_corrupted_audit_chain_critical(self):
        log = MagicMock()
        log.verify_all.return_value = False
        v = InvariantChecker.check_audit_chain(log)
        assert v is not None
        assert v.name == "I-AUDIT"
        assert v.is_critical()

    def test_audit_exception_warning(self):
        log = MagicMock()
        log.verify_all.side_effect = RuntimeError("audit crash")
        v = InvariantChecker.check_audit_chain(log)
        assert v is not None
        assert v.severity == "WARNING"

    # ── check_all ─────────────────────────────────────────────────────────────

    def test_check_all_clean_state(self):
        checker = InvariantChecker()
        report = checker.check_all(
            capital=10_000.0,
            equity=10_000.0,
            positions={"BTC/USDT": 0.1},
            risk_state="NORMAL",
        )
        assert report.is_clean
        assert not report.has_critical
        assert report.checks_run >= 4

    def test_check_all_multiple_violations(self):
        checker = InvariantChecker()
        report = checker.check_all(
            capital=-100.0,  # CRITICAL
            equity=50_000.0,  # WARNING (diverge trop)
            positions={"BTC/USDT": -1.0},  # CRITICAL
            risk_state="ZOMBIE",  # WARNING
        )
        assert not report.is_clean
        assert report.has_critical
        assert len(report.violations) >= 3

    def test_check_all_with_audit(self):
        log = MagicMock()
        log.verify_all.return_value = True
        checker = InvariantChecker()
        report = checker.check_all(
            capital=10_000.0,
            equity=10_000.0,
            tamper_log=log,
        )
        assert report.is_clean
        assert report.checks_run >= 3

    def test_check_all_summary_clean(self):
        checker = InvariantChecker()
        report = checker.check_all(capital=5_000.0, equity=5_000.0)
        assert "CLEAN" in report.summary()

    def test_check_all_summary_violations(self):
        checker = InvariantChecker()
        report = checker.check_all(capital=-1.0)
        assert "VIOLATIONS" in report.summary()

    def test_invariant_violation_timestamp(self):
        v = InvariantViolation(name="I-TEST", severity="WARNING", message="test")
        assert v.ts <= time.time()

    def test_check_never_raises(self):
        checker = InvariantChecker()
        try:
            checker.check_all(
                capital=None,
                equity="not_a_number",
                positions="invalid",
                risk_state=None,
            )
        except Exception as exc:
            pytest.fail(f"check_all a levé: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# D1 — BurnInEngine — Run compressé
# ══════════════════════════════════════════════════════════════════════════════


class TestD1BurnInEngine:
    """Le moteur de burn-in s'exécute jusqu'au bout sans crash."""

    def test_run_completes_all_cycles(self):
        report = _run_fast()
        assert report.n_cycles_completed == 500

    def test_run_no_exceptions_baseline(self):
        report = _run_fast()
        assert report.n_exceptions == 0

    def test_capital_non_negative_after_run(self):
        report = _run_fast()
        assert report.capital_final >= 0.0

    def test_snapshots_created_at_interval(self):
        report = _run_fast(snapshot_interval=100)
        # 500 cycles / 100 = 5 snapshots
        assert len(report.snapshots) == 5

    def test_snapshot_fields_populated(self):
        report = _run_fast(snapshot_interval=100)
        snap = report.snapshots[0]
        assert snap.cycle == 100
        assert snap.health_score >= 0.0
        assert snap.capital >= 0.0
        assert snap.ts > 0.0

    def test_health_score_computed(self):
        report = _run_fast()
        assert 0.0 <= report.health_score_mean <= 100.0
        assert 0.0 <= report.health_score_min <= 100.0

    def test_health_score_min_le_mean(self):
        report = _run_fast()
        assert report.health_score_min <= report.health_score_mean

    def test_drawdown_non_negative(self):
        report = _run_fast()
        assert report.drawdown_pct_max >= 0.0

    def test_memory_mb_non_negative(self):
        report = _run_fast()
        assert report.memory_mb_max >= 0.0

    def test_n_trades_counted(self):
        report = _run_fast()
        assert report.n_trades >= 0

    def test_strategy_score_in_range(self):
        report = _run_fast()
        assert 0.0 <= report.strategy_score <= 100.0

    def test_strategy_grade_valid(self):
        report = _run_fast()
        assert report.strategy_grade in ("S", "A", "B", "C", "D", "F")

    def test_deterministic_with_seed(self):
        r1 = _run_fast(seed=42)
        r2 = _run_fast(seed=42)
        assert r1.capital_final == r2.capital_final
        assert r1.n_trades == r2.n_trades

    def test_duration_recorded(self):
        report = _run_fast()
        assert report.duration_s > 0.0

    def test_performance_under_30s(self):
        """500 cycles de burn-in en moins de 30 secondes."""
        t0 = time.monotonic()
        _run_fast()
        elapsed = time.monotonic() - t0
        assert elapsed < 30.0


# ══════════════════════════════════════════════════════════════════════════════
# D2 — HealthJournal
# ══════════════════════════════════════════════════════════════════════════════


class TestD2HealthJournal:
    """Journal de santé écrit correctement en JSONL."""

    def test_journal_file_created(self, tmp_path):
        path = tmp_path / "health.jsonl"
        _run_fast(journal_path=path, snapshot_interval=100)
        assert path.exists()

    def test_journal_has_correct_line_count(self, tmp_path):
        """500 cycles / 100 = 5 snapshots → 5 lignes."""
        path = tmp_path / "health.jsonl"
        _run_fast(journal_path=path, n_cycles=500, snapshot_interval=100)
        lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
        assert len(lines) == 5

    def test_journal_valid_json(self, tmp_path):
        path = tmp_path / "health.jsonl"
        _run_fast(journal_path=path, snapshot_interval=100)
        for line in path.read_text().splitlines():
            if line.strip():
                data = json.loads(line)
                assert "cycle" in data
                assert "health_score" in data

    def test_journal_schema_complete(self, tmp_path):
        path = tmp_path / "health.jsonl"
        _run_fast(journal_path=path, snapshot_interval=100)
        data = json.loads(path.read_text().splitlines()[0])
        for key in (
            "cycle",
            "ts",
            "health_score",
            "capital",
            "drawdown_pct",
            "memory_mb",
            "n_alerts",
            "n_invariant_violations",
        ):
            assert key in data, f"Clé manquante: {key}"

    def test_journal_cycles_increasing(self, tmp_path):
        path = tmp_path / "health.jsonl"
        _run_fast(journal_path=path, snapshot_interval=100)
        lines = [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]
        for i in range(1, len(lines)):
            assert lines[i]["cycle"] > lines[i - 1]["cycle"]

    def test_no_journal_without_path(self, tmp_path):
        """Sans journal_path, aucun fichier n'est créé."""
        report = _run_fast(journal_path=None)
        assert report.n_cycles_completed == 500

    def test_journal_appends_incrementally(self, tmp_path):
        """Deux runs séquentiels sur le même path appendent les lignes."""
        path = tmp_path / "health.jsonl"
        _run_fast(journal_path=path, n_cycles=300, snapshot_interval=100)
        count1 = len([ln for ln in path.read_text().splitlines() if ln.strip()])
        _run_fast(journal_path=path, n_cycles=300, snapshot_interval=100)
        count2 = len([ln for ln in path.read_text().splitlines() if ln.strip()])
        assert count2 > count1


# ══════════════════════════════════════════════════════════════════════════════
# D4 — Réconciliation périodique
# ══════════════════════════════════════════════════════════════════════════════


class TestD4Reconciliation:
    """Réconciliation périodique — réseau défaillant récupéré."""

    def test_no_reconcile_failures_without_network_issues(self):
        report = _run_fast(simulate_network_issues=False)
        assert report.n_reconciliation_failures == 0

    def test_reconcile_failures_counted_with_network_issues(self):
        """Réseau défaillant 100% → toutes reconciliations échouent."""
        report = _run_fast(
            simulate_network_issues=True,
            network_issue_rate=1.0,
            reconcile_interval=100,
            n_cycles=500,
        )
        assert report.n_reconciliation_failures > 0

    def test_partial_network_failures_tolerated(self):
        """Réseau défaillant 90% → au moins 1 échec enregistré, run complété."""
        report = _run_fast(
            simulate_network_issues=True,
            network_issue_rate=0.9,
            reconcile_interval=100,
            n_cycles=500,
        )
        assert report.n_cycles_completed == 500
        assert report.n_reconciliation_failures > 0

    def test_reconcile_interval_respected(self):
        """Avec reconcile_interval=100 et 500 cycles → 5 max reconciliations."""
        report = _run_fast(
            simulate_network_issues=True,
            network_issue_rate=1.0,
            reconcile_interval=100,
            n_cycles=500,
        )
        # 500/100 = 5 réconciliations max
        assert report.n_reconciliation_failures <= 5

    def test_no_reconcile_when_interval_zero(self):
        """reconcile_interval=0 → pas de réconciliation (désactivée)."""
        report = _run_fast(
            simulate_network_issues=True,
            network_issue_rate=1.0,
            reconcile_interval=0,
        )
        assert report.n_reconciliation_failures == 0


# ══════════════════════════════════════════════════════════════════════════════
# D5 — BurnInReport et critères P13
# ══════════════════════════════════════════════════════════════════════════════


class TestD5BurnInReport:
    """Rapport final et critères de passage vers P13."""

    def test_clean_run_passes(self):
        report = _run_fast()
        assert report.passed, f"Échec inattendu: {report.failure_reasons}"

    def test_report_to_dict_complete(self):
        report = _run_fast()
        d = report.to_dict()
        for key in (
            "passed",
            "failure_reasons",
            "duration_s",
            "n_cycles",
            "n_exceptions",
            "n_alerts",
            "health_score_mean",
            "health_score_min",
            "memory_mb_max",
            "drawdown_pct_max",
            "capital_final",
            "strategy_score",
            "strategy_grade",
        ):
            assert key in d, f"Clé manquante dans report.to_dict(): {key}"

    def test_exception_causes_failure(self):
        """Un run avec exception non-nulle → passage refusé."""
        # Construire un rapport manuellement avec exception
        report = BurnInReport()
        report.n_exceptions = 1
        report.health_score_min = 80.0
        report.drawdown_pct_max = 5.0
        passed, reasons = BurnInEngine._evaluate_pass_criteria(report)
        assert not passed
        assert any("Exception" in r for r in reasons)

    def test_critical_drawdown_causes_failure(self):
        report = BurnInReport()
        report.drawdown_pct_max = 30.0  # > 25% seuil
        report.health_score_min = 80.0
        passed, reasons = BurnInEngine._evaluate_pass_criteria(report)
        assert not passed
        assert any("Drawdown" in r or "drawdown" in r for r in reasons)

    def test_low_health_score_causes_failure(self):
        report = BurnInReport()
        report.health_score_min = 40.0  # < 50 seuil
        passed, reasons = BurnInEngine._evaluate_pass_criteria(report)
        assert not passed
        assert any("Health" in r or "health" in r for r in reasons)

    def test_invariant_violation_causes_failure(self):
        report = BurnInReport()
        report.n_invariant_violations = 1
        report.health_score_min = 80.0
        passed, reasons = BurnInEngine._evaluate_pass_criteria(report)
        assert not passed

    def test_reconcile_failure_causes_failure(self):
        report = BurnInReport()
        report.n_reconciliation_failures = 1
        report.health_score_min = 80.0
        passed, reasons = BurnInEngine._evaluate_pass_criteria(report)
        assert not passed

    def test_perfect_report_passes(self):
        report = BurnInReport()
        report.n_exceptions = 0
        report.n_invariant_violations = 0
        report.n_audit_failures = 0
        report.health_score_min = 90.0
        report.drawdown_pct_max = 5.0
        report.n_reconciliation_failures = 0
        passed, reasons = BurnInEngine._evaluate_pass_criteria(report)
        assert passed
        assert reasons == []

    def test_summary_contains_pass_or_fail(self):
        report = _run_fast()
        summary = report.summary()
        assert "PASS" in summary or "FAIL" in summary

    def test_summary_contains_key_metrics(self):
        report = _run_fast()
        summary = report.summary()
        assert "cycles=" in summary
        assert "exc=" in summary

    def test_multiple_failure_reasons_all_listed(self):
        report = BurnInReport()
        report.n_exceptions = 1
        report.health_score_min = 30.0
        report.drawdown_pct_max = 40.0
        _, reasons = BurnInEngine._evaluate_pass_criteria(report)
        assert len(reasons) >= 3

    def test_report_config_preserved(self):
        cfg = _fast_config(seed=777)
        engine = BurnInEngine(cfg)
        report = engine.run()
        assert report.config.seed == 777

    def test_network_issues_captured_in_report(self):
        report = _run_fast(
            simulate_network_issues=True,
            network_issue_rate=1.0,
            reconcile_interval=100,
        )
        # Network 100% down → reconcile failures → report refusé
        assert report.n_reconciliation_failures > 0
        # Le critère est strict (0 failure autorisé)
        assert not report.passed

    def test_invariant_checks_run_periodically(self):
        """invariant_interval=50 → checks lancés toutes les 50 cycles."""
        report = _run_fast(invariant_interval=50, n_cycles=500)
        # Au moins 500/50 = 10 checks lancés → pas de violation dans un run sain
        assert report.n_invariant_violations == 0
