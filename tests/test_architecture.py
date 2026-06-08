"""
tests/test_architecture.py — Garde-fous architecturaux permanents.

Ces tests ne vérifient pas le comportement fonctionnel.
Ils vérifient que les règles de dépendance entre Bounded Contexts
sont respectées. Un test qui casse ici = une frontière DDD violée.

Règles encodées (depuis ARCHITECTURE_V2_TO_BE.md §6) :
  - core/ n'importe jamais applications/, domains/, src/
  - platform/ ne dépend de personne (couche la plus basse)
  - domains/market/ n'importe jamais domains/execution/
  - domains/risk/ n'importe jamais domains/strategy/
  - src/ importe uniquement depuis src/ (pas de dépendances circulaires)
  - Aucun doublon de classe dans core/contracts/ (à terme)

Référence : docs/ARCHITECTURE_V2_TO_BE.md §6 (matrice de dépendances)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


# ── Helpers ───────────────────────────────────────────────────────────────────


def _imports_in_file(path: Path) -> list[str]:
    """Retourne la liste des modules importés dans un fichier Python."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def _imports_in_package(
    package_path: Path, skip_dunder: bool = True
) -> dict[str, list[str]]:
    """
    Retourne {fichier_relatif: [modules_importés]} pour tous les .py du package.
    """
    result = {}
    if not package_path.exists():
        return result
    for py_file in package_path.rglob("*.py"):
        if skip_dunder and py_file.name.startswith("__"):
            continue
        rel = str(py_file.relative_to(ROOT))
        result[rel] = _imports_in_file(py_file)
    return result


def _violations(
    package: str,
    forbidden_prefixes: list[str],
    skip_packages: list[str] | None = None,
) -> list[tuple[str, str]]:
    """
    Retourne [(fichier, import_interdit)] pour tous les fichiers du package
    qui importent depuis un préfixe interdit.
    """
    skip = set(skip_packages or [])
    pkg_path = ROOT / package.replace(".", "/")
    found = []
    for rel_file, imports in _imports_in_package(pkg_path).items():
        for imp in imports:
            for prefix in forbidden_prefixes:
                if imp == prefix or imp.startswith(prefix + "."):
                    if not any(rel_file.startswith(s) for s in skip):
                        found.append((rel_file, imp))
    return found


# ── Tests couche Core ─────────────────────────────────────────────────────────


class TestCoreLayerIsolation:
    """
    core/ est la couche de fondation.
    Elle ne doit JAMAIS dépendre d'une couche supérieure.
    """

    def test_core_does_not_import_applications(self):
        violations = _violations("core", ["applications"])
        assert not violations, (
            f"core/ importe des modules applications/ — violation couche.\n"
            f"Fichiers : {violations}"
        )

    def test_core_does_not_import_domains(self):
        violations = _violations("core", ["domains"])
        assert not violations, (
            f"core/ importe des modules domains/ — violation couche.\n"
            f"Fichiers : {violations}"
        )

    def test_core_does_not_import_src(self):
        # src/ est le squelette V2 — core/ ne doit pas en dépendre
        violations = _violations("core", ["src"])
        assert not violations, (
            f"core/ importe depuis src/ — dépendance circulaire potentielle.\n"
            f"Fichiers : {violations}"
        )


# ── Tests couche src/ ─────────────────────────────────────────────────────────


class TestSrcInternalConsistency:
    """
    src/ est le nouveau squelette V2.
    Les modules src/ ne doivent pas importer depuis les anciens modules racine
    (quant_hedge_ai/, risk/, governance/, etc.) — ce serait une régression.
    """

    LEGACY_ROOTS = [
        "quant_hedge_ai",
        "tracker_system",
        "crypto_quant_v16",
        "terminal_core",
        "ai_autonomous_loop",
    ]

    def test_src_does_not_import_legacy_quant_hedge_ai(self):
        violations = _violations("src", ["quant_hedge_ai"])
        assert not violations, (
            f"src/ importe depuis quant_hedge_ai/ (module legacy).\n"
            f"Migrer les dépendances vers src/ ou domains/.\n"
            f"Violations : {violations}"
        )

    def test_src_does_not_import_legacy_tracker_system(self):
        violations = _violations("src", ["tracker_system"])
        assert not violations, (
            f"src/ importe depuis tracker_system/ (module legacy).\n"
            f"Violations : {violations}"
        )

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "Cycles connus Phase 0 :\n"
            "  src.analytics ↔ src.backtest : edge_scorer.py importe BacktestEngine ;"
            " backtest/engine.py importe RegimeDetector.\n"
            "  src.analytics ↔ src.risk : edge_scorer.py importe KillSwitch ;"
            " risk/regime_gate.py importe RegimeDetector.\n"
            "Fix Phase 0C : extraire RegimeDetector vers src.domain.regime"
            " (couche inférieure aux deux)."
        ),
    )
    def test_src_no_circular_between_subdirectories(self):
        """
        Vérifie qu'aucun sous-module src/A n'importe depuis src/B qui importe src/A.
        (détection de cycles simples — pas de détection de cycles complexes)

        Cycles connus et documentés (Phase 0 — à résoudre en Phase 0C) :
          - src.analytics ↔ src.backtest
          - src.analytics ↔ src.risk
        Root cause : RegimeDetector dans analytics, requis par backtest + risk.
        Fix : déplacer dans src.domain.regime (couche inférieure aux deux).
        """
        src_path = ROOT / "src"
        if not src_path.exists():
            return

        # Construit le graphe : {module -> set(dépendances)}
        graph: dict[str, set[str]] = {}
        for subdir in src_path.iterdir():
            if not subdir.is_dir() or subdir.name.startswith("_"):
                continue
            mod = f"src.{subdir.name}"
            deps: set[str] = set()
            for py_file in subdir.rglob("*.py"):
                for imp in _imports_in_file(py_file):
                    if imp.startswith("src.") and not imp.startswith(mod):
                        parts = imp.split(".")
                        if len(parts) >= 2:
                            deps.add(f"{parts[0]}.{parts[1]}")
            graph[mod] = deps

        # Détecte les cycles A→B et B→A
        cycles = []
        mods = list(graph.keys())
        for i, a in enumerate(mods):
            for b in mods[i + 1 :]:
                if b in graph.get(a, set()) and a in graph.get(b, set()):
                    cycles.append((a, b))

        assert not cycles, "Cycles de dépendances détectés dans src/ :\n" + "\n".join(
            f"  {a} ↔ {b}" for a, b in cycles
        )


# ── Tests Bounded Context (DDD) ───────────────────────────────────────────────


class TestBoundedContextRules:
    """
    Une fois les domains/ migrés, ces tests vérifient que les frontières
    DDD sont respectées (matrice ARCHITECTURE_V2_TO_BE.md §6).

    Actuellement : skip si domains/ n'existe pas encore (Phase 0C non démarrée).
    """

    def _skip_if_no_domains(self):
        if not (ROOT / "domains").exists():
            pytest.skip("domains/ non encore créé — Phase 0C non démarrée")

    def test_market_does_not_import_execution(self):
        self._skip_if_no_domains()
        violations = _violations("domains/market", ["domains.execution"])
        assert not violations, (
            f"domains/market/ importe domains/execution/ — interdit par matrice DDD.\n"
            f"Violations : {violations}"
        )

    def test_risk_does_not_import_strategy(self):
        self._skip_if_no_domains()
        violations = _violations("domains/risk", ["domains.strategy"])
        assert not violations, (
            f"domains/risk/ importe domains/strategy/ — interdit par matrice DDD.\n"
            f"Violations : {violations}"
        )

    def test_core_does_not_import_any_domain(self):
        self._skip_if_no_domains()
        violations = _violations("core", ["domains"])
        assert not violations, (
            f"core/ importe domains/ — violation couche (core → domains interdit).\n"
            f"Violations : {violations}"
        )

    def test_market_does_not_import_portfolio(self):
        self._skip_if_no_domains()
        violations = _violations("domains/market", ["domains.portfolio"])
        assert not violations, (
            f"domains/market/ importe domains/portfolio/ — interdit.\n"
            f"Violations : {violations}"
        )


# ── Métriques de dette (non-bloquants, informatifs) ───────────────────────────


class TestArchitectureMetrics:
    """
    Tests informatifs — ne font pas échouer le build mais mesurent la dette.
    À transformer en assertions strictes au fur et à mesure des migrations.
    """

    def test_root_directory_count(self):
        """
        Compte les dossiers racine. Objectif : < 40.
        Actuellement baseline à 89.
        """
        dirs = [
            d
            for d in ROOT.iterdir()
            if d.is_dir()
            and not d.name.startswith(".")
            and d.name not in {"__pycache__", ".venv", "node_modules", "_ARCHIVE_2026"}
        ]
        count = len(dirs)
        # Avertissement si > 89 (régression) — strict si > 89
        assert count <= 89, (
            f"Régression : {count} dossiers racine (baseline = 89). "
            f"Une migration a introduit de nouveaux dossiers."
        )
        # Informatif : affiche la progression vers l'objectif
        print(f"\n[Arch Metric] Dossiers racine : {count}/89 (objectif : <40)")

    def test_no_new_runtime_modules(self):
        """
        Détecte l'apparition de nouveaux modules 'runtime' hors des 3 connus.
        Objectif : 3 → 1.
        """
        # Normalisation : forward slashes pour compatibilité Windows/Linux
        known_runtimes = {
            "runtime",
            "quant_hedge_ai/runtime",
            "src/runtime",
        }
        # Répertoires à exclure (runtime logs, artefacts, venv...)
        skip_dirs = {".venv", "__pycache__", "_ARCHIVE_2026", "logs", ".git"}

        found = set()
        for d in ROOT.rglob("runtime"):
            if not d.is_dir():
                continue
            rel = d.relative_to(ROOT).as_posix()  # forward slashes
            if any(skip in rel for skip in skip_dirs):
                continue
            found.add(rel)

        new_runtimes = found - known_runtimes
        assert not new_runtimes, (
            f"Nouveau(x) module(s) runtime détecté(s) — régression (baseline=3) :\n"
            f"  {new_runtimes}\n"
            f"Consolider dans core/kernel/ au lieu d'en créer un nouveau."
        )
        print(f"\n[Arch Metric] Runtime modules : {len(found)} (objectif : 1)")

    def test_deprecated_shim_imports(self):
        """
        Compte les imports vers des shims DEPRECATED.
        Objectif : 0 après délai de 14 jours.
        """
        deprecated_count = 0
        deprecated_files = []
        for py_file in ROOT.rglob("*.py"):
            if any(
                skip in str(py_file)
                for skip in [
                    ".venv",
                    "__pycache__",
                    "_ARCHIVE_2026",
                    "test_architecture",
                ]
            ):
                continue
            try:
                content = py_file.read_text(encoding="utf-8")
                if "DEPRECATED" in content and "warnings.warn" in content:
                    deprecated_count += 1
                    deprecated_files.append(str(py_file.relative_to(ROOT)))
            except Exception:
                pass
        print(
            f"\n[Arch Metric] Shims DEPRECATED actifs : {deprecated_count} "
            f"(objectif : 0 après migration)"
        )
        # Pas d'assertion stricte — informatif uniquement jusqu'à fin Phase 0C
