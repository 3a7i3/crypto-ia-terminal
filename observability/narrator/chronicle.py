"""Lecture du dernier releve de la chronique du burn-in.

Le Narrateur ne CALCULE pas la chronique : `tools/burnin_chronicle.py` la
produit (326 624 rejets lus, ~30 s), un timer systemd la rafraichit, et le
Narrateur relaie le dernier releve. Chacun son metier, et le narrateur reste
un processus leger qui n'ouvre qu'un fichier de quelques centaines d'octets.

Ce qui est relaye, et ce qui ne l'est pas : la **fenetre observee** (temps
reel, interruptions, couverture) n'a pas de proprietaire dans la matrice de
routage — c'est bien la vie interne de la machine. En revanche **N canonique
et la projection vers 500** appartiennent a ① rapport_automatique
(« gouvernance scientifique »), qui les emet deja. Ils sont volontairement
ignores ici.

Un releve perime est ANNONCE comme tel, jamais presente comme actuel : c'est
la meme regle que le PnL inconnu qui ne s'affiche pas a zero.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

CHEMIN = Path("databases/burnin_chronicle.jsonl")

# Au-dela, le releve decrit un autre moment que celui qu'on raconte.
PEREMPTION_H = 48.0


def dernier_releve(chemin: Path = CHEMIN) -> dict | None:
    """Dernier relevé de la chronique, ou None si illisible ou absent.

    Ne lit que la fin du fichier : la chronique est append-only et grandit
    d'une ligne par execution.
    """
    try:
        if not chemin.exists():
            return None
        derniere = ""
        with open(chemin, encoding="utf-8", errors="replace") as fh:
            for ligne in fh:
                ligne = ligne.strip()
                if ligne:
                    derniere = ligne
        if not derniere:
            return None
        releve = json.loads(derniere)
        return releve if isinstance(releve, dict) else None
    except (OSError, ValueError):
        return None


def _age_h(releve: dict, maintenant: float | None = None) -> float | None:
    horodatage = releve.get("genere_le")
    if not isinstance(horodatage, str):
        return None
    try:
        quand = datetime.fromisoformat(horodatage)
    except ValueError:
        return None
    if quand.tzinfo is None:
        quand = quand.replace(tzinfo=timezone.utc)
    ref = maintenant or datetime.now(timezone.utc).timestamp()
    return (ref - quand.timestamp()) / 3600.0


def _duree(secondes: float) -> str:
    jours = secondes / 86400
    if jours >= 1:
        return f"{jours:.1f} j"
    heures = secondes / 3600
    if heures >= 1:
        return f"{heures:.1f} h"
    return f"{secondes / 60:.0f} min"


def lignes(chemin: Path = CHEMIN, maintenant: float | None = None) -> list[str]:
    """Lignes a inserer dans le recapitulatif quotidien. [] si rien a dire."""
    releve = dernier_releve(chemin)
    if releve is None:
        return []

    observe = releve.get("observe_s")
    calendaire = releve.get("calendaire_s")
    if not isinstance(observe, (int, float)) or not isinstance(
        calendaire, (int, float)
    ):
        return []
    if calendaire <= 0:
        return []

    age = _age_h(releve, maintenant)
    if age is not None and age > PEREMPTION_H:
        # Un releve vieux de plusieurs jours decrit un autre moment. On le
        # date au lieu de le faire passer pour l'etat courant.
        return [
            "",
            f"Fenetre observee — releve vieux de {age / 24:.1f} j, "
            "non rafraichi (chronique non relancee)",
        ]

    out = ["", "FENETRE D'OBSERVATION"]
    couverture = releve.get("couverture_pct")
    couv = f"  ({couverture:.1f} %)" if isinstance(couverture, (int, float)) else ""
    out.append(f"Observe   {_duree(observe)} / {_duree(calendaire)} calendaires{couv}")

    interruptions = releve.get("interruptions")
    if isinstance(interruptions, int):
        detail = ""
        plus_longue = releve.get("plus_longue_interruption_s")
        if interruptions and isinstance(plus_longue, (int, float)):
            detail = f"  (plus longue {_duree(plus_longue)})"
        out.append(f"Arrets    {interruptions}{detail}")

    manquants = releve.get("jours_sans_fichier")
    if isinstance(manquants, list) and manquants:
        out.append(f"Jours sans donnees : {len(manquants)} — couverture non garantie")
    return out
