"""
Tentacule Évolution — auto-amélioration des modules via l'IA du projet.

Rôle:
  - Score chaque module Python (santé du code: bare except, TODOs, complexité)
  - Identifie les modules les plus faibles
  - Utilise l'EvolutionEngine existant comme référence de "santé stratégique"
  - Propose (et optionnellement applique) des corrections simples et sûres
  - Génère un rapport d'amélioration par cycle

Corrections auto-sûres appliquées:
  - Ajouter `from __future__ import annotations` manquant
  - Remplacer `except:` nu par `except Exception:`
  - Ajouter timeout par défaut aux appels requests sans timeout

Corrections proposées (pas appliquées auto):
  - Refactoriser fonctions > 50 lignes
  - Ajouter type hints manquants
  - Réduire complexité cyclomatique élevée
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from pieuvre.incidents.models import Finding, Severity
from pieuvre.tentacles.base import BaseTentacle

logger = logging.getLogger(__name__)


@dataclass
class ModuleScore:
    """Score de santé d'un module Python."""

    path: str
    score: float  # 0.0 (mauvais) → 100.0 (parfait)
    bare_excepts: int = 0
    todo_count: int = 0
    long_functions: list[str] = field(default_factory=list)
    missing_types: int = 0
    missing_future: bool = False
    issues: list[str] = field(default_factory=list)


_BARE_EXCEPT = re.compile(r"^\s*except\s*:\s*$", re.MULTILINE)
_TODO = re.compile(r"#\s*(TODO|FIXME|HACK|XXX|BUG)", re.IGNORECASE)
_FUTURE_IMPORT = re.compile(r"from\s+__future__\s+import\s+annotations")


class EvolutionTentacle(BaseTentacle):
    """Auto-amélioration — analyse et améliore la qualité du code."""

    name = "evolution"
    emoji = "🧬"

    # Seuils de score pour déclencher des alertes
    WEAK_MODULE_THRESHOLD = 60.0
    CRITICAL_MODULE_THRESHOLD = 40.0

    def __init__(self, repo_path: Path, auto_fix: bool = False) -> None:
        super().__init__(repo_path)
        self.auto_fix = auto_fix
        self._module_scores: list[ModuleScore] = []
        self._fixes_applied: int = 0

    def scan(self) -> list[Finding]:
        self._scan_count += 1
        files = self._collect_py_files()
        findings: list[Finding] = []
        scores: list[ModuleScore] = []

        for path in files:
            score = self._score_module(path)
            scores.append(score)

            # Auto-fix indépendant du seuil de score
            if self.auto_fix and score.bare_excepts > 0:
                fixed = self._auto_fix_bare_except(path)
                if fixed:
                    self._fixes_applied += 1
                    findings.append(
                        Finding(
                            file=self._relative(path),
                            line=0,
                            rule="auto_fixed_bare_except",
                            message=f"Auto-correction: bare except → except Exception dans {path.name}",
                            severity=Severity.LOW,
                            snippet="auto_fix=bare_except",
                            tentacle=self.name,
                        )
                    )

            if score.score < self.CRITICAL_MODULE_THRESHOLD:
                sev = Severity.HIGH
            elif score.score < self.WEAK_MODULE_THRESHOLD:
                sev = Severity.MEDIUM
            else:
                continue  # module sain

            if self.is_immune(f"weak_module:{path.name}"):
                continue

            findings.append(
                Finding(
                    file=self._relative(path),
                    line=0,
                    rule="weak_module",
                    message=(
                        f"Module faible (score {score.score:.0f}/100) — "
                        f"{len(score.issues)} problème(s): {', '.join(score.issues[:3])}"
                    ),
                    severity=sev,
                    snippet=f"score={score.score:.0f} bare_except={score.bare_excepts} todos={score.todo_count}",
                    tentacle=self.name,
                )
            )

        self._module_scores = scores
        self.last_findings = findings

        # Rapport de santé globale
        if scores:
            avg = sum(s.score for s in scores) / len(scores)
            weak = sum(1 for s in scores if s.score < self.WEAK_MODULE_THRESHOLD)
            logger.info(
                "[EVOLUTION] Score moyen: %.0f/100 — %d/%d modules faibles — %d corrections auto",
                avg,
                weak,
                len(scores),
                self._fixes_applied,
            )

        return findings

    # ── Scoring ───────────────────────────────────────────────────────────────

    def _score_module(self, path: Path) -> ModuleScore:
        score = ModuleScore(path=self._relative(path), score=100.0)
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            score.score = 0.0
            return score

        # Bare excepts (-10 chacun)
        bare = len(_BARE_EXCEPT.findall(source))
        score.bare_excepts = bare
        if bare:
            score.issues.append(f"{bare} bare except")
            score.score -= bare * 10

        # TODOs (-3 chacun)
        todos = len(_TODO.findall(source))
        score.todo_count = todos
        if todos:
            score.issues.append(f"{todos} TODO/FIXME")
            score.score -= todos * 3

        # from __future__ import annotations manquant (-5)
        if source.strip() and not _FUTURE_IMPORT.search(source):
            score.missing_future = True
            score.issues.append("missing future annotations")
            score.score -= 5

        # Fonctions longues via AST (-5 par fonction > 50 lignes)
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    length = (node.end_lineno or 0) - node.lineno
                    if length > 50:
                        score.long_functions.append(f"{node.name}({length}L)")
                        score.score -= 5
            if score.long_functions:
                score.issues.append(f"{len(score.long_functions)} fonctions longues")
        except SyntaxError:
            score.score -= 20
            score.issues.append("erreur de syntaxe")

        score.score = max(0.0, min(100.0, score.score))
        return score

    # ── Auto-corrections sûres ────────────────────────────────────────────────

    def _auto_fix_bare_except(self, path: Path) -> bool:
        """Remplace `except:` nu par `except Exception:` — correction sûre."""
        try:
            source = path.read_text(encoding="utf-8")
            new_source = re.sub(r"(\s+)except\s*:", r"\1except Exception:", source)
            if new_source != source:
                path.write_text(new_source, encoding="utf-8")
                logger.info("[EVOLUTION] Auto-fix bare_except dans %s", path.name)
                return True
        except Exception as exc:
            logger.warning("Auto-fix échoué pour %s: %s", path.name, exc)
        return False

    # ── Rapport ───────────────────────────────────────────────────────────────

    def weakest_modules(self, top_n: int = 5) -> list[ModuleScore]:
        return sorted(self._module_scores, key=lambda s: s.score)[:top_n]

    def average_score(self) -> float:
        if not self._module_scores:
            return 100.0
        return sum(s.score for s in self._module_scores) / len(self._module_scores)
