#!/usr/bin/env python3
"""
debt_map.py  --  Registre de dette technique et plan d'action.

Utilisation :
  python project_os/debt_map.py                         # tableau des dettes
  python project_os/debt_map.py --json                  # -> project_os/debt_map.json
  python project_os/debt_map.py --high                  # seulement severite >= 4
  python project_os/debt_map.py --cat tests             # filtre par categorie
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DEBT_ITEMS: list[dict[str, Any]] = [
    {
        "id": "DEBT-001",
        "category": "couplage",
        "name": "Couplage analytics / execution",
        "severity": 3,
        "impact": 3,
        "module": "tracker_system / quant_hedge_ai",
        "description": "Les metriques d'analyse sont melangees avec la logique d'execution.",
        "action": "Contrats d'interface stricts entre couche metriques et execution",
        "effort": "M",
        "status": "identifie",
    },
    {
        "id": "DEBT-002",
        "category": "architecture",
        "name": "Multiplication des points d'entree",
        "severity": 3,
        "impact": 3,
        "module": "root",
        "description": "Plusieurs main.py, launch scripts, points d'entree differents.",
        "action": "Un seul entrypoint canonique par phase",
        "effort": "M",
        "status": "identifie",
    },
    {
        "id": "DEBT-003",
        "category": "documentation",
        "name": "Documentation dispersee",
        "severity": 4,
        "impact": 4,
        "module": "tous",
        "description": "Documentation repartie entre README, QUICKSTART, docstrings, fichiers .md.",
        "action": "Hub doc unique + index automatise (docs/index.md + generateur)",
        "effort": "L",
        "status": "identifie",
    },
    {
        "id": "DEBT-004",
        "category": "process",
        "name": "Absence de tracking de maturite",
        "severity": 4,
        "impact": 4,
        "module": "project_os",
        "description": "Aucune vue d'ensemble de la maturite par domaine.",
        "action": "Project OS scorecards + reporting automatise (daily/weekly)",
        "effort": "L",
        "status": "en_cours",
    },
    {
        "id": "DEBT-005",
        "category": "tests",
        "name": "Faible visibilite sur les tests manquants",
        "severity": 4,
        "impact": 5,
        "module": "tous",
        "description": "Beaucoup de fichiers sans tests correspondants. Regressions silencieuses.",
        "action": "Scan coverage par module + alerte de regressions",
        "effort": "L",
        "status": "en_cours",
    },
    {
        "id": "DEBT-006",
        "category": "securite",
        "name": "Secrets potentiellement dans le code",
        "severity": 5,
        "impact": 5,
        "module": "root",
        "description": "Presence de .env, cles API visibles dans l'historique.",
        "action": "Rotation des cles, .env.example complet, validation pre-commit",
        "effort": "S",
        "status": "identifie",
    },
    {
        "id": "DEBT-007",
        "category": "architecture",
        "name": "Code legacy non archive (_legacy/)",
        "severity": 2,
        "impact": 2,
        "module": "quant_hedge_ai._legacy",
        "description": "Modules archives mais toujours presents dans l'arborescence active.",
        "action": "Nettoyage ou isolation totale du dossier _legacy/",
        "effort": "S",
        "status": "identifie",
    },
    {
        "id": "DEBT-008",
        "category": "tests",
        "name": "Tests dormants / non maintenus",
        "severity": 3,
        "impact": 3,
        "module": "tests/",
        "description": "Tests ecrits pour des versions anterieures, potentiellement faux positifs.",
        "action": "Audit et mise a jour de tous les tests existants",
        "effort": "M",
        "status": "identifie",
    },
    {
        "id": "DEBT-009",
        "category": "couplage",
        "name": "Dependance implicite au regime de marche",
        "severity": 3,
        "impact": 3,
        "module": "quant_hedge_ai / tracker_system",
        "description": "Parametres optimises pour un regime specifique sans detection auto.",
        "action": "Systematiser la detection de regime et l'adaptation des parametres",
        "effort": "L",
        "status": "identifie",
    },
    {
        "id": "DEBT-010",
        "category": "documentation",
        "name": "Pas de runbook d'incident",
        "severity": 3,
        "impact": 4,
        "module": "ops",
        "description": "En cas de panne, pas de procedure documentee.",
        "action": "Rediger les runbooks (panne, regression, deviation de performance)",
        "effort": "M",
        "status": "identifie",
    },
]


DEBT_CATEGORIES = {
    "couplage": "Couplage inter-modules",
    "architecture": "Dette d'architecture",
    "documentation": "Dette de documentation",
    "tests": "Manque / qualite des tests",
    "securite": "Securite",
    "process": "Process / methodologie",
}

EFFORT_LABEL = {"S": "Small (<1j)", "M": "Medium (1-3j)", "L": "Large (>3j)"}


def compute_score(item: dict[str, Any]) -> int:
    return item["severity"] * item["impact"]


def main() -> None:
    output_json = False
    high_only = False
    cat_filter = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--json":
            output_json = True
        elif a == "--high":
            high_only = True
        elif a == "--cat" and i + 1 < len(args):
            cat_filter = args[i + 1]
            i += 1
        i += 1

    items = [dict(item) for item in BASE_DEBT_ITEMS]
    for item in items:
        item["priority_score"] = compute_score(item)
    items.sort(key=lambda x: -x["priority_score"])

    if high_only:
        items = [it for it in items if it["severity"] >= 4]
    if cat_filter:
        items = [it for it in items if it["category"] == cat_filter]

    if output_json:
        out: dict[str, Any] = {
            "generated_at": datetime.now().isoformat(),
            "total_items": len(items),
            "debt_items": items,
            "summary": {
                "total_score": sum(it["priority_score"] for it in items),
                "high_severity": sum(1 for it in items if it["severity"] >= 4),
                "medium_severity": sum(1 for it in items if 2 <= it["severity"] <= 3),
                "by_category": {
                    cat_id: sum(1 for it in items if it["category"] == cat_id)
                    for cat_id in DEBT_CATEGORIES
                },
            },
        }
        out_path = Path.cwd() / "project_os" / "debt_map.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"-> {out_path}")
        return

    print(f"\n{'='*100}")
    print(f"  Technical Debt Register  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*100}")
    print(
        f"  {'ID':<10} {'Dette':<38} {'Sev':>3} {'Imp':>3} {'Score':>5} {'Eff':>3} {'Statut':<12} {'Categorie'}"
    )
    print(f"  {'-'*10} {'-'*38} {'-'*3} {'-'*3} {'-'*5} {'-'*3} {'-'*12} {'-'*20}")
    for item in items:
        print(
            f"  {item['id']:<10} {item['name'][:36]:<38} {item['severity']:>3} {item['impact']:>3} "
            f"{item['priority_score']:>5} {item['effort']:>3} {item['status']:<12} {item['category']}"
        )
    print(f"{'='*100}")
    print(
        f"  {len(items)} dettes  |  Score total: {sum(it['priority_score'] for it in items)}"
    )
    print(f"  Hautes severite (>=4): {sum(1 for it in items if it['severity'] >= 4)}")
    print()


if __name__ == "__main__":
    main()
