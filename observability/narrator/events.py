"""Classification et mise en mots des evenements de la boite noire.

Contrat : docs/CONTRAT_SUPERVISEUR.md § 2.

Trois registres, et la distinction est tout le contrat :

  DIRECT   ce qui CHANGE un etat — emis tout de suite, ~20-50/jour
  ROUTINE  le flux normal — jamais emis a l'unite, seulement agrege
  IGNORE   ce qui appartient a un autre canal — jamais emis ici

Mesure du 2026-08-06 sur 4000 evenements consecutifs : 2333 TRADE_REFUSED,
1661 HOLD, 6 SYSTEM_EVENT. Soit ~1600 evenements/heure, 26/minute. Sans cette
separation, le canal depasse les limites Telegram et devient illisible — c'est
le mode d'echec principal, pas un detail de reglage.

Module pur : aucune I/O, aucun import du moteur de decision (contrat § 6-1).
Il ne connait que des dictionnaires.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

# Types de `DecisionType` (quant_hedge_ai/agents/intelligence/black_box.py).
# Recopies en constantes de chaine plutot qu'importes : le narrateur doit
# rester decouple du moteur. Un test verifie que les deux listes coincident,
# pour qu'un ajout la-bas ne passe pas inapercu ici.
TRADE_EXECUTED = "TRADE_EXECUTED"
TRADE_REFUSED = "TRADE_REFUSED"
HOLD = "HOLD"
POSITION_CLOSED = "POSITION_CLOSED"
HALT_TRIGGERED = "HALT_TRIGGERED"
SAFE_MODE = "SAFE_MODE"
REGIME_CHANGE = "REGIME_CHANGE"
AWARENESS_ALERT = "AWARENESS_ALERT"
RULE_TRIGGERED = "RULE_TRIGGERED"
SYSTEM_EVENT = "SYSTEM_EVENT"

TOUS_LES_TYPES = frozenset(
    {
        TRADE_EXECUTED,
        TRADE_REFUSED,
        HOLD,
        POSITION_CLOSED,
        HALT_TRIGGERED,
        SAFE_MODE,
        REGIME_CHANGE,
        AWARENESS_ALERT,
        RULE_TRIGGERED,
        SYSTEM_EVENT,
    }
)

# Un evenement n'a qu'un seul canal proprietaire
# (docs/TELEGRAM_CHANNEL_CONTRACTS.md § 1). Ceux-ci ont deja le leur : les
# relayer ici fabriquerait un neuvieme conflit dans une matrice qui en compte
# huit non resolus.
APPARTIENT_AILLEURS = {
    TRADE_EXECUTED: "② PaperArena",
    POSITION_CLOSED: "② PaperArena",
    REGIME_CHANGE: "④ QuantCrypto",
}

DIRECT = "direct"
ROUTINE = "routine"
IGNORE = "ignore"

_NIVEAUX_GRAVES = frozenset({"DANGER", "CRITICAL", "VETO"})

COUCHE_INCONNUE = "couche non precisee"


@dataclass(frozen=True)
class Narration:
    """Verdict de classification pour un evenement."""

    registre: str
    texte: str = ""
    urgent: bool = False
    cles: tuple = ()
    motif_ignore: str = ""


# ── Helpers de rendu ─────────────────────────────────────────────────────────


def _txt(entry: dict, champ: str) -> str:
    """Valeur texte, ou "" si absente. Une absence n'est jamais rendue."""
    v = entry.get(champ)
    if v is None:
        return ""
    v = str(v).strip()
    return "" if v in {"", "?", "unknown", "None"} else v


def _couches(entry: dict) -> list[str]:
    """Couches refusantes, telles quelles — avec leurs parametres."""
    brut = entry.get("refused_by") or []
    if isinstance(brut, str):
        brut = [brut]
    return [str(c).strip() for c in brut if str(c).strip()]


def couche_normalisee(couche: str) -> str:
    """Nom de la COUCHE seule, sans ses parametres.

    Mesure du 2026-08-06 sur 2500 evenements reels : `refused_by` porte les
    valeurs de seuil — « gate: signal_score (57<66) », « (59<66) », « (62<72) »…
    Deduplique tel quel, chaque valeur devient un « premier blocage du jour »
    distinct : 46 messages directs en 1 h 30, soit ~700/jour contre 20-50 vises.
    Le contrat etait respecte a la lettre et viole en pratique.

    Deux raisons de couper avant les parametres, pas une :

    1. La question du Narrateur est « QUELLE couche a bloque », pas « avec
       quelle valeur » — la valeur figure deja dans le message direct.
    2. Compter les valeurs de seuil sur une periode PRODUIRAIT une statistique
       de seuil effectif, propriete du canal ⑤ (min-max, ecart-type,
       oscillation). Le Narrateur n'a pas a la fabriquer.
    """
    nu = str(couche).strip()
    if ":" in nu:
        nu = nu.split(":", 1)[0]
    if "(" in nu:
        nu = nu.split("(", 1)[0]
    return nu.strip() or COUCHE_INCONNUE


def couches_normalisees(entry: dict) -> list[str]:
    """Couches refusantes, dedupliquees et sans parametres."""
    vues = []
    for c in _couches(entry):
        n = couche_normalisee(c)
        if n not in vues:
            vues.append(n)
    return vues or ["couche non precisee"]


def _jour(ts: Any) -> str:
    try:
        return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return "?"


def _heure(ts: Any) -> str:
    try:
        return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%H:%M UTC")
    except Exception:
        return ""


def _ligne(label: str, valeur: str) -> list[str]:
    """Une ligne, ou rien du tout si la valeur est inconnue.

    Regle eprouvee trois fois le 2026-08-05 (PnL ouvert, solde futures, prix
    manquant) : une donnee absente ne se rend jamais comme un zero ou un
    tiret. Elle disparait.
    """
    return [f"{label} {valeur}"] if valeur else []


def _entete(entry: dict, titre: str) -> list[str]:
    h = _heure(entry.get("ts"))
    return [f"{titre}{f'  —  {h}' if h else ''}"]


# ── Rendus par type ──────────────────────────────────────────────────────────


def _rendu_halt(entry: dict) -> str:
    lignes = _entete(entry, "ARRET — la machine se met en securite")
    lignes += _ligne("Motif :", _txt(entry, "reason"))
    lignes += _ligne("Vigilance :", _txt(entry, "awareness_level"))
    return "\n".join(lignes)


def _rendu_safe_mode(entry: dict) -> str:
    lignes = _entete(entry, "SAFE MODE")
    lignes += _ligne("Motif :", _txt(entry, "reason"))
    return "\n".join(lignes)


def _rendu_vigilance(entry: dict) -> str:
    niveau = _txt(entry, "awareness_level")
    lignes = _entete(entry, f"VIGILANCE → {niveau}" if niveau else "VIGILANCE")
    lignes += _ligne("Motif :", _txt(entry, "reason"))
    return "\n".join(lignes)


def _rendu_regle(entry: dict) -> str:
    lignes = _entete(entry, "REGLE INTERNE DECLENCHEE")
    lignes += _ligne("", _txt(entry, "reason"))
    lignes += _ligne("Sur :", _txt(entry, "symbol"))
    return "\n".join(lignes)


def _rendu_systeme(entry: dict) -> str:
    lignes = _entete(entry, "SYSTEME")
    lignes += _ligne("", _txt(entry, "reason"))
    return "\n".join(lignes)


def _rendu_premier_blocage(entry: dict, nouvelles: list[str]) -> str:
    """Le titre porte les couches NOUVELLES, le corps garde le detail complet.

    Mesure du 2026-08-06 en service reel : un refus cumulant `gate` et `meta`
    arrivait apres que chacune ait deja ete annoncee seule, et se presentait
    quand meme en « premier blocage » — un troisieme message qui n'apprenait
    rien. Le titre dit donc ce qui est reellement nouveau.
    """
    titre = "PREMIER BLOCAGE DU JOUR"
    if nouvelles:
        titre += f" — {', '.join(nouvelles)}"
    lignes = _entete(entry, titre)
    sym = _txt(entry, "symbol")
    sig = _txt(entry, "signal")
    score = entry.get("score")
    detail = " ".join(x for x in (sym, sig) if x)
    if isinstance(score, (int, float)) and not isinstance(score, bool):
        detail = f"{detail} score {int(score)}".strip()
    lignes += _ligne("", detail)

    # Le detail COMPLET des couches, avec leurs parametres. `reason` ne porte
    # que la premiere couche (mesure du 2026-08-06) : afficher « meta » en
    # titre et « gate: signal_score (66<68) » en motif faisait un message qui
    # se contredisait lui-meme.
    complet = _couches(entry)
    lignes += _ligne("Couches :", ", ".join(complet))

    motif = _txt(entry, "reason")
    noyau = motif[len("Refus:") :].strip() if motif.startswith("Refus:") else motif
    if noyau and noyau not in ", ".join(complet):
        lignes += _ligne("Motif :", motif)
    return "\n".join(lignes)


# ── Classification ───────────────────────────────────────────────────────────


def classify(entry: dict, deja_vu: Iterable[str] = ()) -> Narration:
    """Range un evenement dans son registre et le met en mots.

    `deja_vu` porte les cles de deduplication deja emises — c'est ce qui fait
    qu'une couche bloquante n'est racontee qu'a sa PREMIERE occurrence du
    jour. Les 2332 refus suivants partent dans l'agregat horaire.
    """
    if not isinstance(entry, dict):
        return Narration(IGNORE, motif_ignore="entree illisible")

    type_ = _txt(entry, "decision_type")
    if not type_:
        return Narration(IGNORE, motif_ignore="type absent")

    proprietaire = APPARTIENT_AILLEURS.get(type_)
    if proprietaire:
        return Narration(IGNORE, motif_ignore=f"appartient a {proprietaire}")

    if type_ == HALT_TRIGGERED:
        return Narration(DIRECT, _rendu_halt(entry), urgent=True)

    if type_ == SAFE_MODE:
        return Narration(DIRECT, _rendu_safe_mode(entry), urgent=True)

    if type_ == AWARENESS_ALERT:
        grave = _txt(entry, "awareness_level").upper() in _NIVEAUX_GRAVES
        return Narration(DIRECT, _rendu_vigilance(entry), urgent=grave)

    if type_ == RULE_TRIGGERED:
        return Narration(DIRECT, _rendu_regle(entry))

    if type_ == SYSTEM_EVENT:
        return Narration(DIRECT, _rendu_systeme(entry))

    if type_ == TRADE_REFUSED:
        couches = couches_normalisees(entry)
        if couches == [COUCHE_INCONNUE]:
            # Mesure du 2026-08-06 : 68 refus sur 861 arrivent sans
            # `refused_by`, motif « HOLD — pas de signal ». Annoncer un
            # « PREMIER BLOCAGE DU JOUR » sans savoir quelle couche a bloque
            # n'apprend rien et consomme une place du plafond. Ils sont
            # comptes dans l'agregat, jamais racontes a l'unite.
            return Narration(ROUTINE)

        # Une cle PAR COUCHE, pas une cle par combinaison. Mesure du
        # 2026-08-06 en service reel : apres « gate » seule et « meta » seule,
        # un refus cumulant les deux se presentait en troisieme « premier
        # blocage » — meme faute de granularite que les valeurs de seuil, une
        # couche plus haut. Chaque couche ne s'annonce qu'une fois par jour,
        # quelles que soient ses compagnes.
        jour = _jour(entry.get("ts"))
        vues = set(deja_vu)
        cles = tuple(f"blocage:{jour}:{c}" for c in couches)
        nouvelles = [c for c, k in zip(couches, cles) if k not in vues]
        if not nouvelles:
            return Narration(ROUTINE, cles=cles)
        return Narration(DIRECT, _rendu_premier_blocage(entry, nouvelles), cles=cles)

    # HOLD et tout type inconnu : la routine. Un type qu'on ne connait pas ne
    # devient jamais une alerte par defaut.
    return Narration(ROUTINE)
