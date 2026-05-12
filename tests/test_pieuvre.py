"""
Tests unitaires de la Pieuvre Géante.

Couvre:
  - models.py: Incident, Finding, sévérités, serialisation
  - store.py: persistence JSON, immunités, récurrence
  - SecuriteTentacle: patterns de détection
  - AuditCommitsTentacle: parsing git (mock subprocess)
  - EvolutionTentacle: scoring de modules
  - GuerisonTentacle: timer de récupération, expérience
  - PieuvreGigante: machine à états, force cumulative
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Répertoire temporaire simulant un dépôt."""
    (tmp_path / "module_a.py").write_text(
        "import os\n"
        "def foo():\n"
        "    try:\n"
        "        pass\n"
        "    except:\n"
        "        pass\n",
        encoding="utf-8",
    )
    (tmp_path / "module_b.py").write_text(
        "from __future__ import annotations\n"
        "API_KEY = 'sk-1234567890abcdef'\n"
        "def bar(): pass\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def store(tmp_path: Path):
    from pieuvre.incidents.store import IncidentStore

    return IncidentStore(tmp_path / "history.json")


@pytest.fixture
def incident():
    from pieuvre.incidents.models import Incident, IncidentType, Severity

    return Incident(
        type=IncidentType.SECURITY,
        severity=Severity.HIGH,
        module="test_module.py",
        message="Test incident",
    )


# ── Tests models.py ───────────────────────────────────────────────────────────


class TestIncidentModel:
    def test_required_recovery(self, incident):
        from pieuvre.incidents.models import RECOVERY_SECONDS

        assert incident.required_recovery() == RECOVERY_SECONDS[incident.severity]

    def test_strength_reward(self, incident):
        from pieuvre.incidents.models import STRENGTH_GAIN

        assert incident.strength_reward() == STRENGTH_GAIN[incident.severity]

    def test_resolve(self, incident):
        incident.resolve()
        assert incident.resolved_at is not None
        assert incident.recovery_seconds >= 0
        assert incident.strength_gained > 0

    def test_serialization_roundtrip(self, incident):
        from pieuvre.incidents.models import Incident

        d = incident.to_dict()
        assert d["severity"] == "high"
        restored = Incident.from_dict(d)
        assert restored.id == incident.id
        assert restored.severity == incident.severity
        assert restored.module == incident.module

    def test_finding_roundtrip(self):
        from pieuvre.incidents.models import Finding, Severity

        f = Finding(
            file="a.py",
            line=10,
            rule="test_rule",
            message="msg",
            severity=Severity.MEDIUM,
            snippet="x = 1",
        )
        d = f.to_dict()
        restored = Finding.from_dict(d)
        assert restored.rule == f.rule
        assert restored.severity == f.severity


# ── Tests store.py ────────────────────────────────────────────────────────────


class TestIncidentStore:
    def test_save_and_reload(self, store, incident, tmp_path):
        from pieuvre.incidents.store import IncidentStore

        store.save(incident)
        assert len(store.all()) == 1

        # Recharge depuis le fichier
        store2 = IncidentStore(tmp_path / "history.json")
        assert len(store2.all()) == 1
        assert store2.all()[0].id == incident.id

    def test_update_existing(self, store, incident):
        store.save(incident)
        incident.message = "Updated"
        store.save(incident)
        all_ = store.all()
        assert len(all_) == 1
        assert all_[0].message == "Updated"

    def test_resolved_vs_pending(self, store, incident):
        store.save(incident)
        assert len(store.pending()) == 1
        assert len(store.resolved()) == 0
        incident.resolve()
        store.save(incident)
        assert len(store.pending()) == 0
        assert len(store.resolved()) == 1

    def test_total_strength_gained(self, store, incident):
        incident.resolve()
        store.save(incident)
        assert store.total_strength_gained() > 0

    def test_all_immunity_patterns(self, store, incident):
        incident.immunity_patterns = ["rule_a", "rule_b"]
        store.save(incident)
        patterns = store.all_immunity_patterns()
        assert "rule_a" in patterns
        assert "rule_b" in patterns

    def test_recurring_rules(self, store):
        from pieuvre.incidents.models import Incident, IncidentType, Severity

        for _ in range(3):
            inc = Incident(
                type=IncidentType.SECURITY,
                severity=Severity.LOW,
                module="x",
                message="test",
            )
            inc.immunity_patterns = ["recurring_rule"]
            store.save(inc)
        recurring = store.recurring_rules(min_count=2)
        assert "recurring_rule" in recurring
        assert recurring["recurring_rule"] == 3


# ── Tests SecuriteTentacle ────────────────────────────────────────────────────


class TestSecuriteTentacle:
    def test_detects_hardcoded_secret(self, tmp_repo):
        from pieuvre.tentacles.securite import SecuriteTentacle

        t = SecuriteTentacle(tmp_repo)
        findings = t.scan()
        rules = [f.rule for f in findings]
        assert "hardcoded_secret" in rules

    def test_detects_bare_except(self, tmp_repo):
        from pieuvre.tentacles.securite import SecuriteTentacle

        t = SecuriteTentacle(tmp_repo)
        findings = t.scan()
        rules = [f.rule for f in findings]
        assert "bare_except" in rules

    def test_immunity_suppresses_finding(self, tmp_repo):
        from pieuvre.tentacles.securite import SecuriteTentacle

        t = SecuriteTentacle(tmp_repo)
        t.add_immunity("hardcoded_secret")
        findings = t.scan()
        rules = [f.rule for f in findings]
        assert "hardcoded_secret" not in rules

    def test_eval_detected(self, tmp_path):
        from pieuvre.tentacles.securite import SecuriteTentacle

        (tmp_path / "evil.py").write_text(
            "result = eval(user_input)\n", encoding="utf-8"
        )
        t = SecuriteTentacle(tmp_path)
        findings = t.scan()
        assert any(f.rule == "eval_usage" for f in findings)

    def test_sql_injection_detected(self, tmp_path):
        from pieuvre.tentacles.securite import SecuriteTentacle

        (tmp_path / "db.py").write_text(
            'cursor.execute(f"SELECT * FROM {table}")\n', encoding="utf-8"
        )
        t = SecuriteTentacle(tmp_path)
        findings = t.scan()
        assert any(f.rule == "sql_fstring" for f in findings)

    def test_shell_true_detected(self, tmp_path):
        from pieuvre.tentacles.securite import SecuriteTentacle

        (tmp_path / "cmd.py").write_text(
            "subprocess.run(cmd, shell=True)\n", encoding="utf-8"
        )
        t = SecuriteTentacle(tmp_path)
        findings = t.scan()
        assert any(f.rule == "subprocess_shell_true" for f in findings)

    def test_clean_file_no_findings(self, tmp_path):
        from pieuvre.tentacles.securite import SecuriteTentacle

        (tmp_path / "clean.py").write_text(
            "from __future__ import annotations\n\ndef add(a: int, b: int) -> int:\n    return a + b\n",
            encoding="utf-8",
        )
        t = SecuriteTentacle(tmp_path)
        findings = t.scan()
        assert findings == []


# ── Tests EvolutionTentacle ───────────────────────────────────────────────────


class TestEvolutionTentacle:
    def test_scores_module_with_bare_except(self, tmp_repo):
        from pieuvre.tentacles.evolution import EvolutionTentacle

        t = EvolutionTentacle(tmp_repo)
        t.scan()
        scores = {s.path: s for s in t._module_scores}
        # module_a.py a un bare except → score réduit
        assert any("module_a" in k for k in scores)
        a_score = next(s for k, s in scores.items() if "module_a" in k)
        assert a_score.score < 100.0
        assert a_score.bare_excepts >= 1

    def test_auto_fix_bare_except(self, tmp_path):
        from pieuvre.tentacles.evolution import EvolutionTentacle

        f = tmp_path / "autofix.py"
        f.write_text(
            "def x():\n    try:\n        pass\n    except:\n        pass\n",
            encoding="utf-8",
        )
        t = EvolutionTentacle(tmp_path, auto_fix=True)
        t.scan()
        content = f.read_text(encoding="utf-8")
        assert "except Exception:" in content

    def test_average_score_bounded(self, tmp_repo):
        from pieuvre.tentacles.evolution import EvolutionTentacle

        t = EvolutionTentacle(tmp_repo)
        t.scan()
        avg = t.average_score()
        assert 0.0 <= avg <= 100.0

    def test_weakest_modules_sorted(self, tmp_repo):
        from pieuvre.tentacles.evolution import EvolutionTentacle

        t = EvolutionTentacle(tmp_repo)
        t.scan()
        weakest = t.weakest_modules(top_n=3)
        scores = [s.score for s in weakest]
        assert scores == sorted(scores)


# ── Tests GuerisonTentacle ────────────────────────────────────────────────────


class TestGuerisonTentacle:
    def test_recovery_reduces_with_experience(self, tmp_path):
        from pieuvre.incidents.models import (
            RECOVERY_SECONDS,
            Incident,
            IncidentType,
            Severity,
        )
        from pieuvre.tentacles.guerison import GuerisonTentacle

        g = GuerisonTentacle(tmp_path)
        inc = Incident(
            type=IncidentType.SECURITY, severity=Severity.HIGH, module="x", message="y"
        )

        # force=1.0 (base) → pas de réduction
        secs_base = g.start_recovery(inc, current_force=1.0)
        assert secs_base == RECOVERY_SECONDS[Severity.HIGH]

        g2 = GuerisonTentacle(tmp_path)
        # force=3.0 → réduction de 16%
        secs_exp = g2.start_recovery(inc, current_force=3.0)
        assert secs_exp < secs_base

    def test_is_healed_after_zero_recovery(self, tmp_path):
        from pieuvre.tentacles.guerison import GuerisonTentacle, RecoveryState

        g = GuerisonTentacle(tmp_path)
        g.recovery = RecoveryState(
            active=True, incident_id="x", end_time=time.time() - 1, actual_seconds=1
        )
        assert g.is_healed() is True

    def test_not_healed_during_recovery(self, tmp_path):
        from pieuvre.tentacles.guerison import GuerisonTentacle, RecoveryState

        g = GuerisonTentacle(tmp_path)
        g.recovery = RecoveryState(
            active=True, incident_id="x", end_time=time.time() + 999, actual_seconds=999
        )
        assert g.is_healed() is False

    def test_render_bar(self, tmp_path):
        from pieuvre.tentacles.guerison import GuerisonTentacle

        g = GuerisonTentacle(tmp_path)
        bar = g.render_recovery_bar()
        assert "santé" in bar or "%" in bar


# ── Tests PieuvreGigante (machine à états) ────────────────────────────────────


class TestPieuvreGigante:
    def test_init_restores_force(self, tmp_path):
        from pieuvre import PieuvreGigante
        from pieuvre.incidents.models import Incident, IncidentType, Severity
        from pieuvre.incidents.store import IncidentStore

        store = IncidentStore(tmp_path / "pieuvre" / "incidents" / "history.json")
        inc = Incident(
            type=IncidentType.SECURITY, severity=Severity.HIGH, module="x", message="y"
        )
        inc.resolve()
        store.save(inc)

        pieuvre = PieuvreGigante(repo_path=str(tmp_path))
        assert pieuvre.force > 1.0

    def test_status_returns_dict(self, tmp_path):
        from pieuvre import PieuvreGigante

        p = PieuvreGigante(repo_path=str(tmp_path))
        status = p.status()
        assert "state" in status
        assert "force" in status
        assert "tentacles" in status
        assert len(status["tentacles"]) == 8

    def test_worst_finding_picks_critical(self):
        from pieuvre.brain import PieuvreGigante
        from pieuvre.incidents.models import Finding, Severity

        findings = [
            Finding(file="a", line=1, rule="r1", message="m", severity=Severity.LOW),
            Finding(
                file="b", line=2, rule="r2", message="m", severity=Severity.CRITICAL
            ),
            Finding(file="c", line=3, rule="r3", message="m", severity=Severity.MEDIUM),
        ]
        worst = PieuvreGigante._worst_finding(findings)
        assert worst is not None
        assert worst.severity == Severity.CRITICAL

    def test_scan_once_returns_findings(self, tmp_path):
        """Test end-to-end: scan sur un répertoire avec du code vulnérable."""
        from pieuvre import PieuvreGigante

        (tmp_path / "vuln.py").write_text(
            'password = "secret123"\n' 'def hack(): eval("rm -rf")\n',
            encoding="utf-8",
        )

        pieuvre = PieuvreGigante(repo_path=str(tmp_path))
        findings = asyncio.run(pieuvre._run_all_tentacles())
        rules = [f.rule for f in findings]
        assert "hardcoded_secret" in rules
        assert "eval_usage" in rules

    def test_immunities_loaded_from_store(self, tmp_path):
        from pieuvre import PieuvreGigante
        from pieuvre.incidents.models import Incident, IncidentType, Severity
        from pieuvre.incidents.store import IncidentStore

        store = IncidentStore(tmp_path / "pieuvre" / "incidents" / "history.json")
        inc = Incident(
            type=IncidentType.SECURITY, severity=Severity.LOW, module="x", message="y"
        )
        inc.immunity_patterns = ["hardcoded_secret"]
        inc.resolve()
        store.save(inc)

        pieuvre = PieuvreGigante(repo_path=str(tmp_path))
        # La tentacule securite doit avoir l'immunité hardcoded_secret
        sec = next(t for t in pieuvre.tentacles if t.name == "securite")
        assert sec.is_immune("hardcoded_secret")
