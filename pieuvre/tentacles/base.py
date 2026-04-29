"""BaseTentacle — classe abstraite pour tous les tentacules de la Pieuvre."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from pieuvre.incidents.models import Finding

logger = logging.getLogger(__name__)


class BaseTentacle(ABC):
    """
    Un tentacule de la Pieuvre Géante.

    Chaque tentacule:
      - Possède un domaine de surveillance exclusif
      - Peut être mis en pause (RECOVERY) et relancé (REGROWTH)
      - Accumule ses dernières trouvailles pour affichage
      - Supporte l'injection d'immunités depuis les incidents passés
    """

    name: str = "base"
    emoji: str = "🔍"

    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path
        self.active: bool = True
        self.last_findings: list[Finding] = []
        self._immunity: set[str] = set()
        self._scan_count: int = 0

    # ── API principale ────────────────────────────────────────────────────────

    @abstractmethod
    def scan(self) -> list[Finding]:
        """Exécute le scan synchrone — appelé via asyncio.to_thread par le cerveau."""

    def pause(self) -> None:
        self.active = False
        logger.debug("Tentacule %s mis en pause", self.name)

    def resume(self) -> None:
        self.active = True
        logger.debug("Tentacule %s relancé", self.name)

    def add_immunity(self, pattern_name: str) -> None:
        """Injecte une immunité apprise d'un incident passé."""
        self._immunity.add(pattern_name)
        logger.debug("Tentacule %s: immunité '%s' acquise", self.name, pattern_name)

    def load_immunities(self, patterns: set[str]) -> None:
        self._immunity.update(patterns)

    def is_immune(self, rule: str) -> bool:
        """Vérifie si ce rule a déjà été absorbé comme immunité silencieuse."""
        return rule in self._immunity

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _collect_py_files(
        self,
        skip_dirs: frozenset[str] | None = None,
        skip_test_files: bool = True,
    ) -> list[Path]:
        """Collecte tous les .py du projet en excluant les dossiers système."""
        default_skip = frozenset(
            {
                ".git",
                "__pycache__",
                "venv",
                ".venv",
                "node_modules",
                "pieuvre",
                "archives",
                "archive_results",
                ".github",
            }
        )
        excluded = (skip_dirs or frozenset()) | default_skip
        files: list[Path] = []
        for py in self.repo_path.rglob("*.py"):
            parts = set(py.parts)
            if parts & excluded:
                continue
            if skip_test_files and (
                py.name.startswith("test_") or py.name.endswith("_test.py")
            ):
                continue
            if "tests" in py.parts:
                continue
            files.append(py)
        return files

    def _relative(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.repo_path))
        except ValueError:
            return str(path)
