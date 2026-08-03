#!/usr/bin/env python3
"""Dépose les observations déjà mesurées dans le magasin scientifique.

Amorçage unique de `knowledge/` avec les faits établis par la campagne de
mesure de la Phase A. Chaque énoncé est descriptif : aucune cause, aucune
interprétation — les inférences correspondantes appartiennent à des
Hypothesis, qui n'existent pas encore.

Refuse de s'exécuter si le journal existe déjà : les identifiants ne sont
jamais réattribués, une seconde exécution créerait des doublons.

Usage :
    python tools/seed_observations.py [--root knowledge]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scios.objects import ObjectStore, Observation, measurement  # noqa: E402

EPOCH_V4 = "EPO-004"

CARTOGRAPHY = measurement(
    tool="tools/runtime_cartographer.py + mesure .pyc sur l'hôte de production",
    method=(
        "analyse AST du graphe d'import du dépôt, puis relevé des .pyc présents "
        "sur 136.85.107.18 pour le processus PID 62316 exécutant le commit f427895"
    ),
    limitations=(
        "un .pyc prouve au moins un import depuis le déploiement, pas un import "
        "à chaque cycle ; fenêtre d'observation courte ; CPython n'écrit pas de "
        ".pyc pour le script __main__"
    ),
    inputs=("artifacts/cartography.json", "artifacts/prod_executed_modules.txt"),
)

BURN_IN = measurement(
    tool="tools/cri_calculator.py",
    method="agrégation des trades propres postérieurs à CLEAN_DATA_SINCE_V4",
    limitations=(
        "N=139 est en deçà de la puissance visée ; la fidélité du simulateur "
        "d'exécution est NON MESURÉE, donc l'écart au réel n'est pas borné"
    ),
    inputs=("databases/paper_trades.jsonl",),
)

HORIZON = measurement(
    tool="AUDIT-EMP-002/003",
    method="corrélation de rang score/rendement à plusieurs horizons",
    limitations=(
        "mesuré sur les candidats observés, pas sur les seuls trades exécutés ; "
        "sur ces derniers la résolution est insuffisante pour poser la question"
    ),
    inputs=("databases/regret/regret_horizons_*.jsonl",),
)

SEEDS = [
    dict(
        provenance=CARTOGRAPHY,
        statement=(
            "210 modules du dépôt possèdent un .pyc écrit par le processus de "
            "production sur 1115 modules au total ; l'analyse statique du même "
            "dépôt en atteint entre 102 et 170."
        ),
        metrics={"executed": 210, "total": 1115, "static_low": 102, "static_high": 170},
        source_events=("artifacts/prod_executed_modules.txt",),
    ),
    dict(
        provenance=CARTOGRAPHY,
        statement=(
            "52 modules classés ORPHAN ou TEST_ONLY par l'analyse statique "
            "possèdent un .pyc écrit par le processus de production."
        ),
        metrics={"faux_negatifs": 52},
    ),
    dict(
        provenance=CARTOGRAPHY,
        statement=(
            "La variable trade_allowed est affectée en 5 endroits de "
            "core/advisor_loop.py : ligne 1983, puis 5626, 5658, 5734 et 5808."
        ),
        metrics={"sites": 5, "lignes": [1983, 5626, 5658, 5734, 5808]},
    ),
    dict(
        provenance=CARTOGRAPHY,
        statement=(
            "Deux classes de machine d'état et deux modules de kill switch "
            "possèdent un .pyc écrit par le processus de production."
        ),
        metrics={"machines_etat": 2, "kill_switch": 2},
    ),
    dict(
        provenance=CARTOGRAPHY,
        statement=(
            "69 noms de classe sont définis dans plusieurs fichiers hors tests ; "
            "pour 8 de ces noms, les deux définitions possèdent un .pyc écrit "
            "par le processus de production."
        ),
        metrics={"noms_dupliques": 69, "paires_doublement_executees": 8},
    ),
    dict(
        provenance=BURN_IN,
        statement=(
            "Sur l'époque V4, N = 139 trades propres, PF = 0.617, WR = 34.9 %, "
            "t = -1.571."
        ),
        metrics={"n": 139, "pf": 0.617, "wr": 0.349, "t": -1.571},
        n=139,
        epoch_id=EPOCH_V4,
    ),
    dict(
        provenance=HORIZON,
        statement=(
            "La corrélation de rang entre le score et le rendement vaut 0.16 à "
            "l'horizon 12-24 h (AUC = 0.60) et n'est pas distinguable de zéro à "
            "l'horizon 1 h ; la durée de détention réalisée médiane est 5.92 h."
        ),
        metrics={"rho_12_24h": 0.16, "auc_12_24h": 0.60, "detention_h": 5.92},
        epoch_id=EPOCH_V4,
    ),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="knowledge")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent / args.root
    store = ObjectStore(root)
    if store.journal.exists():
        print(
            f"{store.journal} existe déjà — amorçage refusé.\n"
            "Les identifiants ne sont jamais réattribués : une seconde "
            "exécution créerait des doublons."
        )
        return 1

    for seed in SEEDS:
        obs = store.create(Observation, 2026, **seed)
        print(f"{obs.id}  {obs.statement[:72]}...")

    problemes = store.verify()
    print(f"\n{len(SEEDS)} observations déposées — intégrité : ", end="")
    print("OK" if not problemes else f"{len(problemes)} violation(s): {problemes}")
    return 0 if not problemes else 2


if __name__ == "__main__":
    raise SystemExit(main())
