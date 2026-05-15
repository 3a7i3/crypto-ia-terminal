#!/usr/bin/env python3
"""
project_os/doc_indexer.py  --  Scanne tous les .md du projet et regenere docs/index.md.

Enrichit l'index existant avec :
  - Liste categorisee de tous les .md trouves (hors archives/build)
  - Etat Project OS (depuis les JSON si disponibles)
  - Date de generation

Usage :
  python project_os/doc_indexer.py           # regenere docs/index.md
  python project_os/doc_indexer.py --dry-run # affiche sans ecrire
  python project_os/doc_indexer.py --scan    # liste les .md seulement
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
PROJECT_OS = ROOT / "project_os"
INDEX_OUT = ROOT / "docs" / "index.md"

SKIP_DIRS = {
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    "node_modules",
    "_build",
    "build",
    "dist",
    "frontend",
    ".github",
    ".cursor",
    "tickets",
}

# Classification des .md par patterns dans le nom de fichier
CATEGORIES: list[dict[str, Any]] = [
    {
        "id": "quickstart",
        "label": "Quick Start & Setup",
        "patterns": [
            "quickstart",
            "quick_start",
            "demarrage",
            "install",
            "setup",
            "onboard",
        ],
        "dirs": ["docs/onboarding"],
    },
    {
        "id": "architecture",
        "label": "Architecture & Design",
        "patterns": [
            "architecture",
            "arborescence",
            "stack",
            "system",
            "lifecycle",
            "schema",
        ],
        "dirs": [],
    },
    {
        "id": "roadmap",
        "label": "Roadmap & Planification",
        "patterns": [
            "roadmap",
            "plan",
            "phase",
            "sprint",
            "implementation",
            "priorities",
        ],
        "dirs": [],
    },
    {
        "id": "operations",
        "label": "Operations & Deploiement",
        "patterns": [
            "deploy",
            "docker",
            "k8s",
            "scheduler",
            "optimization",
            "guide",
            "runbook",
        ],
        "dirs": ["deploy", "k8s", "docs/runbooks"],
    },
    {
        "id": "components",
        "label": "Composants & Modules",
        "patterns": [
            "tracker",
            "dashboard",
            "evolution",
            "pieuvre",
            "supervision",
            "trading",
            "bot",
        ],
        "dirs": ["tracker_system", "quant_hedge_ai"],
    },
    {
        "id": "testing",
        "label": "Tests & Validation",
        "patterns": ["test", "validation", "checklist", "audit", "coverage", "smoke"],
        "dirs": ["docs/checklists", "docs/audit", "tests"],
    },
    {
        "id": "reports",
        "label": "Rapports historiques",
        "patterns": [
            "report",
            "rapport",
            "summary",
            "complete",
            "inventaire",
            "dedup",
            "mismatch",
            "cleanup",
        ],
        "dirs": ["docs/v91"],
    },
]


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def _should_skip(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def discover_md_files(root: Path) -> list[Path]:
    results = []
    for f in sorted(root.rglob("*.md")):
        if _should_skip(f.relative_to(root)):
            continue
        results.append(f)
    return results


def _extract_title(f: Path) -> str:
    try:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip()
    except OSError:
        pass
    return f.stem.replace("_", " ").replace("-", " ").title()


def classify_file(f: Path, root: Path) -> str:
    """Return category id for a .md file."""
    rel = str(f.relative_to(root)).replace("\\", "/").lower()
    name = f.stem.lower()

    for cat in CATEGORIES:
        # Dir match
        for d in cat["dirs"]:
            if rel.startswith(d.lower() + "/") or rel == d.lower():
                return cat["id"]
        # Pattern match on filename
        for pat in cat["patterns"]:
            if pat in name:
                return cat["id"]

    return "misc"


# ---------------------------------------------------------------------------
# Project OS state loader
# ---------------------------------------------------------------------------


def _load(name: str) -> Optional[Any]:
    path = PROJECT_OS / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _project_os_status() -> list[str]:
    lines = ["## Project OS — Etat courant", ""]

    state = _load("roadmap_state.json")
    coverage = _load("test_coverage.json")
    maturity = _load("maturity.json")
    dep_graph = _load("dep_graph.json")

    # Phase
    if state:
        phase = state.get("current_phase", "?")
        phases = state.get("phases", [])
        active = next((p for p in phases if p["status"] == "active"), None)
        lines.append(
            f"**Phase active :** {phase}" + (f" — {active['name']}" if active else "")
        )
        blockers = [b for b in state.get("blockers", []) if not b.get("resolved")]
        if blockers:
            lines.append(f"**Bloqueurs :** {len(blockers)} actif(s)")
        lines.append("")

    # Coverage
    if coverage:
        s = coverage.get("summary", {})
        pct = s.get("coverage_pct", 0)
        lines.append(
            f"**Coverage tests :** {pct}%"
            f" ({s.get('covered', 0)} OK / {s.get('partial', 0)} partiel"
            f" / {s.get('uncovered', 0)} manquant)"
        )

    # Maturity
    if maturity:
        overall = maturity.get("summary", {}).get("overall", "?")
        lines.append(f"**Maturite globale :** {overall}/5")

    # Cycles
    if dep_graph:
        cycles = dep_graph.get("cycles", [])
        lazy = dep_graph.get("lazy_cycle_candidates", [])
        if cycles:
            lines.append(f"**Cycles :** {len(cycles)} detecte(s)")
        else:
            lines.append("**Cycles :** aucun (propre)")
        if lazy:
            lines.append(f"**Lazy pseudo-cycles :** {len(lazy)} (non bloquants)")

    lines += [
        "",
        "| Commande | Role |",
        "|----------|------|",
        "| `python project_os/reporter.py --check` | CI check (exit 0/1) |",
        "| `python project_os/reporter.py --file` | Rapport daily |",
        "| `python project_os/doc_indexer.py` | Regenerer cet index |",
        "",
    ]
    return lines


# ---------------------------------------------------------------------------
# Index generation
# ---------------------------------------------------------------------------


def build_index(md_files: list[Path], root: Path) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Classify
    by_cat: dict[str, list[Path]] = {c["id"]: [] for c in CATEGORIES}
    by_cat["misc"] = []
    for f in md_files:
        # Skip the index itself
        if f == INDEX_OUT:
            continue
        cid = classify_file(f, root)
        by_cat.setdefault(cid, []).append(f)

    sections: list[str] = [
        "# Documentation Hub -- crypto_ai_terminal",
        "",
        f"> Source of truth unique. Genere automatiquement le {ts}.",
        "> Pour regenerer : `python project_os/doc_indexer.py`",
        "",
        "---",
        "",
        "## Navigation rapide",
        "",
        "| Besoin | Section |",
        "|--------|---------|",
        "| Demarrer le systeme | [Quick Start](#quick-start--setup) |",
        "| Comprendre l'architecture | [Architecture](#architecture--design) |",
        "| Etat du projet (live) | [Project OS](#project-os--etat-courant) |",
        "| Roadmap et phases | [Roadmap](#roadmap--planification) |",
        "| Un composant specifique | [Composants](#composants--modules) |",
        "| Rapports historiques | [Rapports](#rapports-historiques) |",
        "",
        "---",
        "",
    ]

    # Project OS status block (live)
    sections.extend(_project_os_status())
    sections.append("---")
    sections.append("")

    # Doc categories
    cat_order = [c["id"] for c in CATEGORIES] + ["misc"]
    for cid in cat_order:
        files = by_cat.get(cid, [])
        if not files:
            continue
        label = next((c["label"] for c in CATEGORIES if c["id"] == cid), "Divers")
        sections.append(f"## {label}")
        sections.append("")
        sections.append("| Fichier | Titre |")
        sections.append("|---------|-------|")
        for f in sorted(files, key=lambda x: x.name):
            rel = f.relative_to(root).as_posix()
            # Make relative path from docs/
            try:
                rel_from_docs = "../" + rel
            except Exception:
                rel_from_docs = rel
            title = _extract_title(f)
            sections.append(f"| [{f.name}]({rel_from_docs}) | {title[:70]} |")
        sections.append("")

    # Footer
    sections += [
        "---",
        "",
        f"*Genere par `project_os/doc_indexer.py` le {ts}.*",
        f"*{len(md_files)} fichiers .md indexes.*",
        "",
    ]

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    scan_only = "--scan" in sys.argv

    files = discover_md_files(ROOT)

    if scan_only:
        print(f"{len(files)} fichiers .md trouves :\n")
        for f in files:
            cid = classify_file(f, ROOT)
            print(f"  [{cid:<12}]  {f.relative_to(ROOT)}")
        return

    content = build_index(files, ROOT)

    if dry_run:
        print(content)
        print(
            f"\n--- dry-run: {len(content)} caracteres, {len(files)} fichiers indexes ---"
        )
        return

    INDEX_OUT.parent.mkdir(parents=True, exist_ok=True)
    INDEX_OUT.write_text(content, encoding="utf-8")
    print(f"-> {INDEX_OUT.relative_to(ROOT)}  ({len(files)} fichiers indexes)")


if __name__ == "__main__":
    main()
