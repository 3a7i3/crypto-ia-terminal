#!/usr/bin/env python3
"""
maturity.py  --  Scorecards de maturite par domaine (niveau 1-5).

Domaines evalues :
  - Modular architecture
  - Market replay (no-lookahead)
  - Statistical reliability
  - Execution realism
  - Exchange realism constraints
  - Walk-forward / OOS validation
  - Observability
  - Live readiness

Utilisation :
  python project_os/maturity.py                          # tableau complet
  python project_os/maturity.py --json                   # -> project_os/maturity.json
  python project_os/maturity.py --domain "execution"     # un seul domaine
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

DOMAINS: list[dict[str, Any]] = [
    {
        "id": "modular_architecture",
        "name": "Modular architecture",
        "description": "Decouplage global du projet en packages/domaines coherents",
        "levels": {
            1: "Tout dans un seul module, pas de separation claire",
            2: "Quelques packages isoles, couplages residus forts",
            3: "Decouplage fonctionnel visible, dependances gerees",
            4: "Architecture propre, interfaces stables, peu de couplage transverse",
            5: "Plugins / modules remplacables, isolation totale par domaine",
        },
        "auto_check_hints": ["__init__.py", "abc.ABC", "Protocol", "tests/"],
    },
    {
        "id": "market_replay",
        "name": "Market replay (no-lookahead)",
        "description": "Rejeu de marche sans fuite de donnees futures",
        "levels": {
            1: "Pas de systeme de replay",
            2: "Replay base sur des fichiers, lookahead possible",
            3: "Replay cadence, clock controlee, lookahead detecte",
            4: "Replay deterministe, verification lookahead systematique",
            5: "Replay multiconditions (regimes, stress), backtest/replay ecart <1%",
        },
        "auto_check_hints": [
            "replay",
            "replay_engine",
            "clock",
            "lookahead",
            "no_lookahead",
        ],
    },
    {
        "id": "statistical_reliability",
        "name": "Statistical reliability",
        "description": "Validite statistique des metriques et backtests",
        "levels": {
            1: "Metriques brutes sans validation",
            2: "Sharpe / Sortino / drawdown calcules mais sans rigueur",
            3: "Metriques avec intervalle de confiance, variance estimee",
            4: "Tests de robustesse systematiques, regime analysis",
            5: "Backtest distribue, Monte Carlo, deflation rate corrige",
        },
        "auto_check_hints": [
            "sharpe",
            "sortino",
            "drawdown",
            "confidence",
            "monte_carlo",
        ],
    },
    {
        "id": "execution_realism",
        "name": "Execution realism",
        "description": "Simulation d'execution realiste (slippage, latence, spread, fills)",
        "levels": {
            1: "Execution supposee parfaite (prix de cloture)",
            2: "Slippage fixe applique, pas de variation",
            3: "Slippage dynamique, spread bid/ask estime",
            4: "Simulation d'ordres, file d'attente, fills partiels",
            5: "Modele d'impact de marche, latence reseau, rebate/fees exacts",
        },
        "auto_check_hints": [
            "execution_simulator",
            "slippage",
            "latency",
            "fill",
            "spread",
        ],
    },
    {
        "id": "exchange_constraints",
        "name": "Exchange realism constraints",
        "description": "Contraintes reelles des exchanges (lots, tick, rate limits)",
        "levels": {
            1: "Aucune contrainte d'echange prise en compte",
            2: "Quelques regles (lot size) verifiees",
            3: "Tick size, min notional, rate limits valides",
            4: "Validation pre-order systematique, rejet documente",
            5: "Modele complet par exchange, simulation de rejet",
        },
        "auto_check_hints": [
            "lot_size",
            "tick_size",
            "min_notional",
            "rate_limit",
            "order_validator",
        ],
    },
    {
        "id": "walk_forward_oos",
        "name": "Walk-forward / OOS validation",
        "description": "Validation hors-echantillon systematique",
        "levels": {
            1: "Pas de validation OOS",
            2: "Train/test split manuel, pas de walk-forward",
            3: "Walk-forward simple, fenetres glissantes",
            4: "Walk-forward avec optimisation par fenetre, stabilite mesuree",
            5: "Walk-forward automatise, OOS par regime, degradation monitor",
        },
        "auto_check_hints": ["walk_forward", "oos", "out_of_sample", "window_splitter"],
    },
    {
        "id": "observability",
        "name": "Observability",
        "description": "Monitoring, logging, alerting, debugging",
        "levels": {
            1: "Aucun monitoring ou logging ad-hoc",
            2: "Logs disperses, pas de niveau systematique",
            3: "Logs structures (JSON), niveaux coherents",
            4: "Metriques temps reel, alertes, dashboard monitoring",
            5: "Tracing distribue, profiling automatique, alerte proactive",
        },
        "auto_check_hints": ["logging", "health", "monitor", "alert", "profiler"],
    },
    {
        "id": "live_readiness",
        "name": "Live readiness",
        "description": "Prete a passer en production reelle",
        "levels": {
            1: "Jamais teste en conditions live",
            2: "Paper trading manuel, pas de surveillance",
            3: "Paper trading automatise, sandbox exchange",
            4: "Limite de risque stricte, kill switch, monitoring live",
            5: "Deploiement progressif, rollback automatique, drills incidents",
        },
        "auto_check_hints": ["paper_trading", "sandbox", "kill_switch", "risk_limit"],
    },
]


def auto_score_domain(domain: dict[str, Any], inventory: dict[str, Any]) -> int:
    hints = domain.get("auto_check_hints", [])
    modules = (
        [r.get("path", "") for r in inventory] if isinstance(inventory, list) else []
    )
    module_text = " ".join(modules).lower()
    score_weight = sum(1 for h in hints if h.lower().replace("-", "_") in module_text)
    if score_weight <= 1:
        return 1
    elif score_weight <= 2:
        return 2
    elif score_weight <= 3:
        return 3
    elif score_weight < len(hints):
        return 4
    return 5


def compute_maturity(inventory_path: str | Path | None = None) -> list[dict[str, Any]]:
    inventory: Any = []
    if inventory_path and Path(inventory_path).exists():
        inventory = json.loads(Path(inventory_path).read_text())
    results = []
    for domain in DOMAINS:
        score = auto_score_domain(domain, inventory)
        next_level = score + 1
        next_desc = domain["levels"].get(next_level, "Objectif atteint")
        results.append(
            {
                "domain_id": domain["id"],
                "domain": domain["name"],
                "level": score,
                "level_description": domain["levels"][score],
                "next_level": next_level if next_level <= 5 else None,
                "next_goal": next_desc if next_level <= 5 else None,
                "description": domain["description"],
            }
        )
    return results


def main() -> None:
    import sys

    output_json = False
    domain_filter = None
    inventory_path: str | None = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--json":
            output_json = True
        elif a == "--domain" and i + 1 < len(args):
            domain_filter = args[i + 1]
            i += 1
        elif a == "--inventory" and i + 1 < len(args):
            inventory_path = args[i + 1]
            i += 1
        i += 1

    if inventory_path is None:
        default = Path.cwd() / "project_os" / "inventory.json"
        if default.exists():
            inventory_path = str(default)

    results = compute_maturity(inventory_path)
    if domain_filter:
        results = [
            r
            for r in results
            if domain_filter.lower() in r["domain"].lower()
            or domain_filter.lower() in r["domain_id"].lower()
        ]

    if output_json:
        out = {
            "generated_at": datetime.now().isoformat(),
            "domains": results,
            "summary": {
                "overall": (
                    round(sum(r["level"] for r in results) / len(results), 2)
                    if results
                    else 0
                ),
                "count": len(results),
            },
        }
        out_path = Path.cwd() / "project_os" / "maturity.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"-> {out_path}")
        return

    print(f"\n{'='*70}")
    print(f"  Maturity Assessment  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*70}")
    print(f"  {'Domaine':<38} {'Niveau':>6}  {'Prochain palier'}")
    print(f"  {'-'*38} {'-'*6}  {'-'*35}")
    for r in results:
        next_txt = r["next_goal"] if r["next_goal"] else "Atteint"
        next_short = next_txt[:35] if next_txt else "-"
        print(f"  {r['domain']:<38} {r['level']:>6}  {next_short}")
    print(f"{'='*70}")
    overall = (
        round(sum(r["level"] for r in results) / len(results), 2) if results else 0
    )
    print(f"\n  Maturite globale : {overall}/5  ({len(results)} domaines)")
    print()


if __name__ == "__main__":
    main()
