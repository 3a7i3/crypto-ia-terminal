"""
scripts/cleanup_root.py — Analyse les fichiers à la racine et génère ROOT_CLEANUP_PROPOSAL.md.

Usage:
    python scripts/cleanup_root.py [--root PATH] [--output PATH]

Ce script ne déplace rien. Il génère uniquement un rapport de proposition.
"""

from __future__ import annotations

import argparse
import ast
import os
from datetime import datetime
from pathlib import Path

# Destination recommandée par catégorie de nom
_NAME_RULES: list[tuple[str, str, str]] = [
    # (fragment_dans_nom, destination, raison)
    ("dashboard", "dashboard/", "Dashboard/visualisation"),
    ("evolution", "quant_hedge_ai/ai_evolution/", "Moteur évolutionnaire"),
    ("monitor", "observability/", "Observabilité"),
    ("alert", "observability/", "Alertes"),
    ("circuit", "scripts/", "Utilitaire infrastructure"),
    ("config", "scripts/", "Configuration"),
    ("data_verif", "scripts/", "Validation données"),
    ("daily", "scripts/", "Analyse quotidienne"),
    ("advisor", "core/", "Orchestration principale"),
    ("bootstrap", "core/", "Démarrage système"),
    ("warm_boot", "core/", "Warm boot"),
    ("launch", "scripts/", "Script de lancement"),
    ("test_", "tests/", "Test unitaire ou d'intégration"),
]

_ALWAYS_SKIP = {"__init__.py", "setup.py", "conftest.py"}


def classify(filename: str) -> tuple[str, str]:
    name_lower = filename.lower()
    for fragment, dest, reason in _NAME_RULES:
        if fragment in name_lower:
            return dest, reason
    return "scripts/", "Non classifiable — vérification manuelle requise"


def count_imports(filepath: str) -> list[str]:
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            tree = ast.parse(f.read())
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module.split(".")[0])
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name.split(".")[0])
        return list(set(imports))
    except Exception:
        return []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Répertoire racine à analyser")
    parser.add_argument("--output", default="ROOT_CLEANUP_PROPOSAL.md")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    py_files = [
        f
        for f in root.iterdir()
        if f.is_file() and f.suffix == ".py" and f.name not in _ALWAYS_SKIP
    ]

    lines = [
        "# ROOT CLEANUP PROPOSAL",
        f"\n> Généré le {datetime.now().strftime('%Y-%m-%d %H:%M')} par scripts/cleanup_root.py",
        f"> Racine analysée : `{root}`",
        f"> Fichiers .py trouvés à la racine : **{len(py_files)}**\n",
        "---\n",
    ]

    if not py_files:
        lines += [
            "## Résultat : racine déjà propre ✅",
            "",
            "Aucun fichier `.py` orphelin détecté à la racine (hors `__init__.py`, `setup.py`, `conftest.py`).",
            "La racine est bien organisée — aucune action requise.",
        ]
    else:
        lines += [
            "## Fichiers orphelins détectés\n",
            "| Fichier | Destination proposée | Raison | Modules importés |",
            "|---------|---------------------|--------|-----------------|",
        ]
        for f in sorted(py_files):
            dest, reason = classify(f.name)
            imports = count_imports(str(f))[:5]
            imports_str = ", ".join(imports) if imports else "—"
            lines.append(f"| `{f.name}` | `{dest}` | {reason} | {imports_str} |")

        lines += [
            "",
            "## Étapes suggérées\n",
            "1. Vérifier les imports entrants avec : `grep -r 'from <nom_fichier>' --include=\"*.py\"`",
            "2. Déplacer le fichier vers la destination proposée",
            "3. Mettre à jour les imports (chercher/remplacer le module path)",
            "4. Lancer les tests : `python -m pytest tests/ -x -q`",
            "",
            "> **JAMAIS** déplacer un fichier sans vérifier ses imports entrants.",
        ]

    output_path = root / args.output
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Rapport généré : {output_path}")
    print(f"Fichiers .py orphelins trouvés : {len(py_files)}")


if __name__ == "__main__":
    main()
