"""tools/burnin_chronicle.py — memoire du temps reellement observe du burn-in.

Audit PASSIF, lecture seule sur les donnees, append-only sur sa propre
chronique. Ne recommande rien, ne modifie aucun seuil (CLAUDE.md, ADR-0007).

## La question

« Depuis combien de temps le burn-in tourne-t-il *vraiment* ? »

Le temps calendaire depuis l'epoque V4 est trivial a calculer et il est
**faux** : le moteur s'arrete. Quatre redemarrages le 2026-08-06, des
migrations, des incidents — chacun creuse un trou que personne n'enregistrait.
`capital_throttle.py:31` porte deja la trace de cette confusion : un compteur
annoncait des jours ecoules « alors que le PROCESSUS avait exactement 3 jours
d'uptime ».

Un debit calcule sur le temps calendaire sous-estime la machine ; une date
d'arrivee a N=500 calculee dessus est optimiste. Les deux chiffres sont donnes
cote a cote, jamais l'un sans l'autre.

## La methode

Le moteur ecrit un rejet a chaque candidat refuse — plusieurs milliers par
jour, en continu. `databases/rejections/` est donc son pouls : **un trou dans
les rejets est un arret du moteur**. On ne demande son etat a personne, on le
lit dans ce qu'il a laisse.

Un cycle dure ~5 min. Un intervalle superieur a `--seuil` minutes (10 par
defaut) signifie qu'au moins un cycle a manque : c'est une interruption.

## Ce que l'outil ne fait pas

Il ne dit pas *pourquoi* le moteur s'est arrete — la boite noire et le
journal systemd le disent. Il ne projette rien d'autre que la prolongation
du debit mesure, et affiche les deux hypotheses plutot que de choisir.

Usage :
    python tools/burnin_chronicle.py [--seuil 10] [--json] [--sans-ecriture]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = (
    Path(__file__).resolve().parents[1] if "__file__" in globals() else Path.cwd()
)
sys.path.insert(0, str(_REPO_ROOT))

from scripts.data_quality import CLEAN_DATA_SINCE_ACTIVE  # noqa: E402

CHRONIQUE = Path("databases/burnin_chronicle.jsonl")
REJETS = Path("databases/rejections")
GATE_N = 500

# Extraction ciblee du seul champ utile : json.loads sur des millions de
# lignes coute des minutes, ce motif coute des secondes.
_TS = re.compile(rb'"ts":\s*([0-9.]+)')


# ── Coeur mesurable ──────────────────────────────────────────────────────────


def detecter_segments(horodatages: list[float], seuil_s: float) -> list[tuple]:
    """Decoupe une suite d'horodatages en segments d'activite continue.

    Un ecart superieur a `seuil_s` ferme le segment courant : le moteur
    n'ecrivait plus, donc il ne tournait pas.
    """
    if not horodatages:
        return []
    ordonnes = sorted(horodatages)
    segments = []
    debut = precedent = ordonnes[0]
    for ts in ordonnes[1:]:
        if ts - precedent > seuil_s:
            segments.append((debut, precedent))
            debut = ts
        precedent = ts
    segments.append((debut, precedent))
    return segments


def resumer(segments: list[tuple], fin_fenetre: float) -> dict:
    """Temps observe, temps d'arret, interruptions. Aucune interpretation."""
    if not segments:
        return {
            "observe_s": 0.0,
            "calendaire_s": 0.0,
            "arret_s": 0.0,
            "interruptions": 0,
            "plus_longue_interruption_s": 0.0,
            "debut": None,
            "fin": None,
        }
    debut, fin = segments[0][0], segments[-1][1]
    observe = sum(f - d for d, f in segments)
    trous = [segments[i + 1][0] - segments[i][1] for i in range(len(segments) - 1)]
    # Le silence entre le dernier evenement et maintenant est un arret en
    # cours, pas une fenetre observee. L'ignorer gonflerait le taux de
    # couverture juste apres un arret.
    queue = max(0.0, fin_fenetre - fin)
    if queue > 0:
        trous.append(queue)
    calendaire = max(fin, fin_fenetre) - debut
    return {
        "observe_s": observe,
        "calendaire_s": calendaire,
        "arret_s": calendaire - observe,
        "interruptions": len(trous),
        "plus_longue_interruption_s": max(trous) if trous else 0.0,
        "debut": debut,
        "fin": fin,
    }


def projeter(n: int, jours: float, cible: int = GATE_N):
    """Jours restants pour atteindre `cible` au rythme observe.

    None si le rythme est nul ou la cible deja franchie — une division par
    zero rendue comme « 0 jour » serait une promesse, pas une mesure.
    """
    if n >= cible:
        return 0.0
    if jours <= 0 or n <= 0:
        return None
    return (cible - n) / (n / jours)


# ── Lecture ──────────────────────────────────────────────────────────────────


def lire_horodatages(dossier: Path, depuis: float) -> tuple[list, list]:
    """Horodatages des rejets posterieurs a `depuis`, et jours manquants."""
    horodatages: list[float] = []
    fichiers = sorted(dossier.glob("rejections_*.jsonl"))
    jours_presents = set()
    for fichier in fichiers:
        jour = fichier.stem.replace("rejections_", "")
        jours_presents.add(jour)
        try:
            with open(fichier, "rb") as fh:
                for ligne in fh:
                    m = _TS.search(ligne)
                    if not m:
                        continue
                    ts = float(m.group(1))
                    if ts >= depuis:
                        horodatages.append(ts)
        except OSError:
            continue
    return horodatages, sorted(_jours_manquants(jours_presents, depuis))


def _jours_manquants(presents: set, depuis: float) -> set:
    """Jours sans fichier de rejets entre l'epoque et aujourd'hui.

    Un jour absent n'est PAS un jour d'arret : le fichier peut avoir ete
    archive. On le signale au lieu de le compter — confondre les deux
    fabriquerait une interruption qui n'a peut-etre jamais eu lieu.
    """
    debut = datetime.fromtimestamp(depuis, timezone.utc).date()
    fin = datetime.now(timezone.utc).date()
    attendus = set()
    jour = debut
    while jour <= fin:
        attendus.add(jour.isoformat())
        jour += timedelta(days=1)
    return attendus - presents


def compter_n_canonique() -> int:
    try:
        from tools.cri_calculator import load_clean_trades

        return len(load_clean_trades())
    except Exception:
        return -1


# ── Rendu ────────────────────────────────────────────────────────────────────


def _duree(secondes: float) -> str:
    jours = secondes / 86400
    if jours >= 1:
        return f"{jours:.1f} j"
    heures = secondes / 3600
    if heures >= 1:
        return f"{heures:.1f} h"
    return f"{secondes / 60:.0f} min"


def rendre(rapport: dict) -> str:
    r = rapport
    obs_j = r["observe_s"] / 86400
    cal_j = r["calendaire_s"] / 86400
    lignes = [
        "CHRONIQUE DU BURN-IN",
        "=" * 52,
        f"Epoque V4        {r['epoque']}",
        f"Temps calendaire {_duree(r['calendaire_s'])}",
        f"Temps OBSERVE    {_duree(r['observe_s'])}   ({r['couverture_pct']:.1f} %)",
        f"Arret cumule     {_duree(r['arret_s'])}"
        f"   sur {r['interruptions']} interruption(s)",
        f"Plus longue      {_duree(r['plus_longue_interruption_s'])}",
        "",
    ]
    if r["n"] < 0:
        lignes.append("N canonique      indisponible (loader en echec)")
        return "\n".join(lignes)

    lignes.append(f"N canonique      {r['n']} / {GATE_N}")
    lignes.append("")
    lignes.append("Debit et projection vers N=500")
    for etiquette, jours, reste in (
        ("sur temps calendaire", cal_j, r["reste_calendaire_j"]),
        ("sur temps OBSERVE   ", obs_j, r["reste_observe_j"]),
    ):
        taux = r["n"] / jours if jours > 0 else 0.0
        if reste is None:
            lignes.append(f"  {etiquette}  {taux:.1f}/j   -> indeterminee")
        else:
            date = datetime.now(timezone.utc) + timedelta(days=reste)
            lignes.append(
                f"  {etiquette}  {taux:.1f}/j   -> {reste:.0f} j "
                f"({date.strftime('%Y-%m-%d')})"
            )
    lignes.append("")
    lignes.append(
        "Les deux chiffres sont donnes ensemble : le calendaire suppose que "
        "le moteur\ntourne sans interruption, ce que la ligne « Arret cumule » "
        "dement."
    )
    if r["jours_sans_fichier"]:
        lignes.append("")
        lignes.append(
            f"Jours sans fichier de rejets ({len(r['jours_sans_fichier'])}) : "
            f"{', '.join(r['jours_sans_fichier'][:6])}"
            + (" …" if len(r["jours_sans_fichier"]) > 6 else "")
        )
        lignes.append(
            "  Un fichier absent n'est pas une preuve d'arret — il peut avoir "
            "ete archive.\n  Signale, jamais compte comme interruption."
        )
    return "\n".join(lignes)


# ── Assemblage ───────────────────────────────────────────────────────────────


def construire(seuil_min: float = 10.0) -> dict:
    depuis = CLEAN_DATA_SINCE_ACTIVE.timestamp()
    horodatages, manquants = lire_horodatages(REJETS, depuis)
    maintenant = datetime.now(timezone.utc).timestamp()
    segments = detecter_segments(horodatages, seuil_min * 60)
    resume = resumer(segments, maintenant)
    n = compter_n_canonique()
    obs_j = resume["observe_s"] / 86400
    cal_j = resume["calendaire_s"] / 86400
    return {
        **resume,
        "genere_le": datetime.now(timezone.utc).isoformat(),
        "epoque": CLEAN_DATA_SINCE_ACTIVE.strftime("%Y-%m-%d %H:%M UTC"),
        "seuil_interruption_min": seuil_min,
        "couverture_pct": (
            100.0 * resume["observe_s"] / resume["calendaire_s"]
            if resume["calendaire_s"] > 0
            else 0.0
        ),
        "n": n,
        "rejets_lus": len(horodatages),
        "jours_sans_fichier": manquants,
        "reste_observe_j": projeter(n, obs_j) if n >= 0 else None,
        "reste_calendaire_j": projeter(n, cal_j) if n >= 0 else None,
    }


def memoriser(rapport: dict, chemin: Path = CHRONIQUE) -> None:
    """Ajoute le releve a la chronique. Append-only : rien n'est reecrit."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with open(chemin, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rapport, ensure_ascii=False) + "\n")


def main() -> int:  # pragma: no cover — plomberie
    ap = argparse.ArgumentParser(description="Chronique du burn-in (passif)")
    ap.add_argument("--seuil", type=float, default=10.0, help="minutes sans rejet")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--sans-ecriture", action="store_true")
    args = ap.parse_args()

    rapport = construire(args.seuil)
    if not args.sans_ecriture:
        memoriser(rapport)
    print(
        json.dumps(rapport, ensure_ascii=False, indent=2)
        if args.json
        else rendre(rapport)
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
