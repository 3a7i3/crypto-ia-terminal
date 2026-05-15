#!/usr/bin/env python3
"""
roadmap_state.py  --  Phase courante, status, blockers, prochaines actions.

Utilisation :
  python project_os/roadmap_state.py                        # etat courant
  python project_os/roadmap_state.py --json                 # sortie JSON brute
  python project_os/roadmap_state.py --advance              # passer a la phase suivante
  python project_os/roadmap_state.py --block "Raison"       # ajouter un bloqueur
  python project_os/roadmap_state.py --unblock              # lever le dernier bloqueur
  python project_os/roadmap_state.py --action "Texte"       # ajouter une prochaine action
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

INITIAL_STATE: dict[str, Any] = {
    "current_phase": "P1",
    "phases": [
        {
            "id": "P1",
            "name": "Stabilization",
            "goal": "Stabiliser la vision et l'etat projet",
            "status": "active",
            "gate_criteria": "100% modules critiques references + etat quotidien reproductible",
            "gate_met": False,
            "completed_at": None,
            "deliverables": [
                "project_os/scanner.py + inventory.json",
                "project_os/test_scanner.py + test_coverage.json",
                "project_os/dep_mapper.py + dep_graph.json",
                "project_os/maturity.py + maturity.json",
                "project_os/debt_map.py + debt_map.json",
                "project_os/roadmap_state.py",
                "project_os/reporter.py",
                "docs/index.md hub documentation",
            ],
        },
        {
            "id": "P2",
            "name": "Simulation Realism",
            "goal": "Reduire l'ecart backtest / realite",
            "status": "pending",
            "gate_criteria": "Ecart simulation vs replay mesure et en baisse. Rejet ordres invalides = 100%",
            "gate_met": False,
            "completed_at": None,
            "deliverables": [
                "execution_simulator/ (slippage, latence, spread, fills partiels)",
                "exchange_constraints/ (precision, rate limits, validation ordres)",
                "Tests 100% deterministes",
            ],
        },
        {
            "id": "P3",
            "name": "Statistical Robustness",
            "goal": "Verifier la validite hors-echantillon",
            "status": "pending",
            "gate_criteria": "Decisions basees sur OOS exclusivement. Stabilite mesuree par regime.",
            "gate_met": False,
            "completed_at": None,
            "deliverables": [
                "walk_forward/ (rolling windows + OOS)",
                "metrics/oos_metrics.py + stability_score.py",
                "monitor/degradation_tracker.py",
            ],
        },
        {
            "id": "P4",
            "name": "Hardening",
            "goal": "Fiabiliser l'infrastructure de recherche",
            "status": "pending",
            "gate_criteria": "Pipeline stable, incidents detectables et reproductibles",
            "gate_met": False,
            "completed_at": None,
            "deliverables": [
                "monitoring/ (logs structures, metriques temps reel)",
                "Profiling (goulots d'etranglement identifies)",
                "tests/integration/ + tests/stress/",
                "docs/runbooks/",
            ],
        },
        {
            "id": "P5",
            "name": "Limited Live",
            "goal": "Transition prudente vers le reel",
            "status": "pending",
            "gate_criteria": "Aucun deploiement reel sans KPI de robustesse valides depuis P3",
            "gate_met": False,
            "completed_at": None,
            "deliverables": [
                "paper_trading/ (simulation temps reel)",
                "Sandbox exchange (API test)",
                "Cap de risque strict (position max, drawdown max)",
            ],
        },
    ],
    "blockers": [],
    "next_actions": [
        "Finaliser project_os/ complet (1.8 docs/index.md)",
        "Generer dep_graph.json, maturity.json, debt_map.json, reporter daily",
        "Demarrer execution_simulator/ (P2 - step 2.1)",
    ],
    "history": [],
}


def _state_path() -> Path:
    return Path.cwd() / "project_os" / "roadmap_state.json"


def load_state() -> dict[str, Any]:
    path = _state_path()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return dict(INITIAL_STATE)


def save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def advance_phase(state: dict[str, Any]) -> dict[str, Any]:
    phases = state["phases"]
    current = next((p for p in phases if p["status"] == "active"), None)
    if current:
        current["status"] = "completed"
        current["completed_at"] = datetime.now().isoformat()
        current["gate_met"] = True
        state["history"].append(
            {
                "event": "phase_completed",
                "phase": current["id"],
                "timestamp": datetime.now().isoformat(),
            }
        )
    phase_ids = [p["id"] for p in phases]
    if current:
        idx = phase_ids.index(current["id"]) + 1
        if idx < len(phases):
            phases[idx]["status"] = "active"
            state["current_phase"] = phases[idx]["id"]
            state["history"].append(
                {
                    "event": "phase_started",
                    "phase": phases[idx]["id"],
                    "timestamp": datetime.now().isoformat(),
                }
            )
    return state


def add_blocker(state: dict[str, Any], reason: str) -> dict[str, Any]:
    state["blockers"].append(
        {
            "reason": reason,
            "created_at": datetime.now().isoformat(),
            "resolved": False,
        }
    )
    state["history"].append(
        {
            "event": "blocker_added",
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        }
    )
    return state


def resolve_blocker(state: dict[str, Any]) -> dict[str, Any]:
    for b in reversed(state["blockers"]):
        if not b["resolved"]:
            b["resolved"] = True
            b["resolved_at"] = datetime.now().isoformat()
            state["history"].append(
                {
                    "event": "blocker_resolved",
                    "reason": b["reason"],
                    "timestamp": datetime.now().isoformat(),
                }
            )
            break
    return state


def add_action(state: dict[str, Any], action: str) -> dict[str, Any]:
    state["next_actions"].append(action)
    return state


def _print_state(state: dict[str, Any]) -> None:
    print(f"\n{'='*70}")
    print(f"  Roadmap State  |  Phase courante : {state['current_phase']}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*70}\n")

    print(f"  {'ID':<6} {'Phase':<25} {'Statut':<12} {'Gate atteint'}")
    print(f"  {'-'*6} {'-'*25} {'-'*12} {'-'*12}")
    for p in state["phases"]:
        gate = "Oui" if p.get("gate_met") else "-"
        print(f"  {p['id']:<6} {p['name']:<25} {p['status']:<12} {gate}")

    active_blockers = [b for b in state.get("blockers", []) if not b.get("resolved")]
    if active_blockers:
        print(f"\n  Bloqueurs actifs ({len(active_blockers)}) :")
        for b in active_blockers:
            print(f"    ! {b['reason']}  (depuis {b['created_at'][:10]})")

    actions = state.get("next_actions", [])
    if actions:
        print(f"\n  Prochaines actions :")
        for i, a in enumerate(actions, 1):
            print(f"    {i}. {a}")

    history = state.get("history", [])
    if history:
        print(f"\n  Historique ({len(history)} evenements)")
        for h in history[-5:]:
            print(
                f"    [{h['timestamp'][:10]}] {h['event']} — {h.get('phase', h.get('reason', ''))}"
            )

    print(f"{'='*70}\n")


def main() -> None:
    state = load_state()
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--json":
            print(json.dumps(state, indent=2))
            return
        elif a == "--advance":
            state = advance_phase(state)
            save_state(state)
            print(f"Phase avancee -> {state['current_phase']}")
            return
        elif a == "--block" and i + 1 < len(args):
            state = add_blocker(state, args[i + 1])
            save_state(state)
            print(f"Bloqueur ajoute : {args[i + 1]}")
            return
        elif a == "--unblock":
            state = resolve_blocker(state)
            save_state(state)
            print("Bloqueur resolu.")
            return
        elif a == "--action" and i + 1 < len(args):
            state = add_action(state, args[i + 1])
            save_state(state)
            print(f"Action ajoutee : {args[i + 1]}")
            return
        i += 1

    _print_state(state)


if __name__ == "__main__":
    main()
