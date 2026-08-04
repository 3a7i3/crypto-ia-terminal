#!/usr/bin/env python3
"""Audit d'attribution du seuil de décision — outil de mesure (gel scientifique OK).

Question mesurée
----------------
Le seuil d'acceptation (`min_signal_score` effectif) varie pendant une époque de
collecte. Ce script mesure *de combien*, *où*, et surtout **combien de décisions
en ont réellement changé** — la seule quantité qui relie une mutation de politique
à la population de trades.

Pourquoi c'est possible sans replay
-----------------------------------
Aucun trade ne porte le seuil en vigueur (`databases/paper_trades*.jsonl` n'a pas
de champ de seuil ; `runtime_config_version` est constant sur toute l'époque et
n'est jamais incrémenté par les mutations adaptatives). En revanche **chaque refus
le porte en clair** :

    "gate_failed": ["signal_score (55<64)"]        → score 55, seuil effectif 64

Le flux de refus est donc l'instrument de mesure du seuil. Les logs runtime, eux,
ne survivent pas : ils ne sont ni versionnés ni migrés entre VM.

Définitions
-----------
base(régime)   Seuil minimal observé pour ce régime sur la fenêtre. Approximation
               par le minimum empirique : les deltas individuels (regret, ATE,
               governor, transition) ne sont PAS persistés séparément, seule leur
               somme est observable via le seuil final.
marge          seuil - score. Comparable entre régimes, contrairement au seuil
               absolu : un refus à 2 points de la frontière est le même événement
               décisionnel en `sideways` (64) qu'en `bull_trend` (72).
flip           Refus qui aurait passé le gate si le seuil avait été à sa base,
               c.-à-d. base <= score < seuil_effectif.
flip gate-seul Flip dont `all_blockers` ne contient que `gate`. C'est le seul cas
               où le delta a *réellement* changé la décision : ailleurs une autre
               couche bloquait de toute façon, et le delta était redondant.

Limites — à lire avant d'interpréter
------------------------------------
1. Le seuil n'est lisible que lorsque `signal_score` est une condition échouée.
   Les cycles bloqués en amont n'apparaissent pas : les VALEURS de seuil sont
   fiables, les PROPORTIONS sont conditionnées à ce sous-ensemble.
2. `decision_packet(REJECTED)` est présent dans 100 % des refus — c'est un
   marqueur de conséquence, pas un bloqueur. Il est exclu du décompte, sans quoi
   le nombre de flips gate-seul est artificiellement nul.
3. Les flips n'ont jamais été tradés : leur résultat est inobservable. Ce script
   mesure l'effet du seuil sur la POPULATION de décisions, jamais sur la
   PERFORMANCE. Cette dernière exige un contrefactuel (replay), hors de portée ici.
4. `base` est une borne inférieure empirique, pas la constante du code. Si un
   régime a passé toute la fenêtre au-dessus de sa base réelle, ses flips sont
   sous-comptés.

Usage
-----
    python tools/threshold_attribution_audit.py <repertoire_rejections>

Le répertoire doit contenir des `rejections_YYYY-MM-DD.jsonl`. Pour l'époque V4,
ils sont dans `backups/vps-corpus-20260731/tier2-rejections-observation.tar.gz`
sous `databases/rejections/`.
"""

from __future__ import annotations

import collections
import glob
import os
import re
import statistics
import sys

# Marqueur de conséquence, jamais une cause de refus (cf. Limites §2).
CONSEQUENCE_MARKERS = {"decision_packet(REJECTED)"}

_RX_THRESHOLD = re.compile(r"signal_score \(([\d.]+)<(\d+)\)")
_RX_REGIME = re.compile(r'"regime":\s*"([^"]*)"')
_RX_BLOCKERS = re.compile(r'"all_blockers":\s*\[([^\]]*)\]')


def load_rejections(directory: str) -> list[tuple[float, int, str, list[str]]]:
    """(score, seuil_effectif, regime, bloqueurs) pour chaque refus exploitable.

    Lecture par expression régulière plutôt que `json.loads` : le corpus fait
    plusieurs centaines de Mo et seuls quatre champs sont nécessaires.
    """
    pattern = os.path.join(directory, "rejections_*.jsonl")
    records: list[tuple[float, int, str, list[str]]] = []
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m_thr = _RX_THRESHOLD.search(line)
                if not m_thr:
                    continue
                m_reg = _RX_REGIME.search(line)
                m_blk = _RX_BLOCKERS.search(line)
                blockers = []
                if m_blk:
                    blockers = [
                        tok.strip().strip("\"'")
                        for tok in m_blk.group(1).split(",")
                        if tok.strip()
                    ]
                    blockers = [b for b in blockers if b not in CONSEQUENCE_MARKERS]
                records.append(
                    (
                        float(m_thr.group(1)),
                        int(m_thr.group(2)),
                        m_reg.group(1) if m_reg else "?",
                        blockers,
                    )
                )
    return records


def observed_base(records) -> dict[str, int]:
    """Seuil de base par régime = minimum empirique observé (cf. Limites §4)."""
    base: dict[str, int] = {}
    for _score, threshold, regime, _blk in records:
        base[regime] = min(base.get(regime, 10**9), threshold)
    return base


def report_thresholds(records, base) -> None:
    per_regime = collections.defaultdict(collections.Counter)
    for _score, threshold, regime, _blk in records:
        per_regime[regime][threshold] += 1
    print("\n=== Seuils effectifs observés, par régime ===")
    for regime in sorted(per_regime, key=lambda r: -sum(per_regime[r].values())):
        seuils = sorted(per_regime[regime])
        total = sum(per_regime[regime].values())
        print(f"  {regime:<24} base={base[regime]:<4} seuils={seuils}  n={total:,}")


def report_margin(records) -> None:
    """La marge est la variable comparable entre régimes (cf. Définitions)."""
    margins = [threshold - score for score, threshold, _r, _b in records]
    buckets = collections.Counter()
    for m in margins:
        if m <= 2:
            buckets["0-2"] += 1
        elif m <= 5:
            buckets["2-5"] += 1
        elif m <= 10:
            buckets["5-10"] += 1
        else:
            buckets[">10"] += 1
    print("\n=== Marge (seuil - score) — distance à la frontière de décision ===")
    print(f"  médiane={statistics.median(margins):.1f}  max={max(margins):.0f}")
    for key in ("0-2", "2-5", "5-10", ">10"):
        n = buckets[key]
        print(f"    marge {key:>5} : {n:>8,} ({100 * n / len(margins):4.1f} %)")


def report_flips(records, base) -> None:
    """Combien de décisions le delta au-dessus de la base a-t-il changées ?"""
    total = collections.Counter()
    flips = collections.Counter()
    flips_gate_only = collections.Counter()
    scores_gate_only = collections.Counter()

    for score, threshold, regime, blockers in records:
        total[regime] += 1
        floor = base[regime]
        if threshold > floor and score >= floor:
            flips[regime] += 1
            if blockers == ["gate"]:
                flips_gate_only[regime] += 1
                scores_gate_only[int(score)] += 1

    print("\n=== Decision flips — refus imputables au delta au-dessus de la base ===")
    header = (
        f"{'régime':<24} {'refus':>9} {'flips':>8} {'%':>6} {'gate-seul':>10} {'%':>6}"
    )
    print(header)
    for regime in sorted(total, key=lambda r: -total[r]):
        n = total[regime]
        print(
            f"  {regime:<22} {n:>9,} {flips[regime]:>8,}"
            f" {100 * flips[regime] / n:>5.1f} {flips_gate_only[regime]:>10,}"
            f" {100 * flips_gate_only[regime] / n:>5.1f}"
        )
    gate_only_total = sum(flips_gate_only.values())
    print(
        f"\n  TOTAL flips={sum(flips.values()):,}"
        f"  dont GATE SEUL={gate_only_total:,}"
    )
    print(
        f"  → {gate_only_total:,} signaux refusés UNIQUEMENT parce que le seuil"
        " était au-dessus de sa base."
    )
    print(
        "  → leur résultat est inobservable : ils n'ont jamais été tradés (Limites §3)."
    )

    if scores_gate_only:
        print("\n  Scores de ces flips gate-seul :")
        for score in sorted(scores_gate_only):
            print(f"    score {score}: {scores_gate_only[score]:,}")


def main(argv: list[str]) -> int:
    # Console Windows en cp1252 : les accents et les flèches font planter l'écriture.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):  # flux non reconfigurable (pipe, capture)
        pass

    if len(argv) != 2:
        print(__doc__)
        return 1
    directory = argv[1]
    if not os.path.isdir(directory):
        print(f"ERREUR — répertoire introuvable : {directory}")
        return 1

    records = load_rejections(directory)
    if not records:
        print(
            f"ERREUR — aucun refus exploitable dans {directory}.\n"
            "Un zéro ici signifie 'dénominateur absent', jamais 'aucune mutation'."
        )
        return 1

    print(f"Refus exploitables : {len(records):,}")
    base = observed_base(records)
    report_thresholds(records, base)
    report_margin(records)
    report_flips(records, base)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
