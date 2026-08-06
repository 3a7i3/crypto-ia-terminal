"""Recapitulatif quotidien — l'etat, et surtout le CHANGEMENT.

Contrat : docs/CONTRAT_SUPERVISEUR.md § 2.

Vingt-quatre agregats horaires disent l'etat vingt-quatre fois. Ce qu'un
proprietaire veut savoir en ouvrant le capot, c'est ce qui a BOUGE depuis
hier. D'ou la comparaison a la veille.

Un piege traite explicitement : **comparer une journee partielle a une
journee complete fabrique une chute imaginaire.** Si le narrateur demarre a
18 h, sa premiere journee couvre 6 h ; l'annoncer en baisse de 75 % serait un
mensonge produit par l'instrument, pas par la machine. La fenetre reellement
observee est donc mesuree, affichee, et l'ecart de volume est declare
incomparable quand les fenetres different trop.

Descriptif uniquement. Aucun taux, aucun verdict, aucune recommandation :
conclure appartient au Superviseur, qui reste gate (contrat § 4).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

from observability.narrator.events import HOLD, TRADE_REFUSED, _txt, couches_normalisees

_TOP_COUCHES = 6
# Au-dela de cet ecart entre les deux fenetres d'observation, les volumes ne
# sont plus comparables et on le dit au lieu d'afficher des deltas trompeurs.
_ECART_FENETRE_MAX_H = 2.0


def jour_de(ts: float) -> str:
    try:
        return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return "?"


@dataclass
class Journee:
    """Compteurs d'une journee UTC, et la fenetre reellement observee."""

    jour: str
    debut_ts: float = 0.0
    fin_ts: float = 0.0
    total: int = 0
    holds: int = 0
    blocages: int = 0
    couches: Counter = field(default_factory=Counter)

    @property
    def couverture_h(self) -> float:
        if not self.debut_ts or self.fin_ts <= self.debut_ts:
            return 0.0
        return (self.fin_ts - self.debut_ts) / 3600.0

    def observer(self, entree: dict) -> None:
        ts = entree.get("ts")
        if isinstance(ts, (int, float)):
            self.debut_ts = ts if not self.debut_ts else min(self.debut_ts, ts)
            self.fin_ts = max(self.fin_ts, ts)
        self.total += 1
        type_ = _txt(entree, "decision_type")
        if type_ == HOLD:
            self.holds += 1
            return
        if type_ != TRADE_REFUSED:
            return
        self.blocages += 1
        for couche in couches_normalisees(entree):
            self.couches[couche] += 1


def _nombre(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _delta(actuel: int, veille) -> str:
    """« (+2 104) », « (-402) », « (=) », ou "" si rien a comparer."""
    if veille is None:
        return ""
    ecart = actuel - veille
    if ecart == 0:
        return "  (=)"
    signe = "+" if ecart > 0 else "-"
    return f"  ({signe}{_nombre(abs(ecart))})"


@dataclass
class Quotidien:
    """Accumule par journee UTC et rend le recapitulatif de la veille."""

    courante: Journee = None
    precedente: Journee = None

    def observer(self, entree: dict) -> None:
        ts = entree.get("ts")
        if not isinstance(ts, (int, float)):
            return
        jour = jour_de(ts)
        if self.courante is None:
            self.courante = Journee(jour)
        elif jour != self.courante.jour:
            self.precedente = self.courante
            self.courante = Journee(jour)
        self.courante.observer(entree)

    # ── Rendu ────────────────────────────────────────────────────────────────

    def _journee(self, jour: str):
        """La journee demandee, ou la courante si aucune n'est precisee.

        Au moment ou le recapitulatif part, une entree du jour suivant peut
        deja avoir fait basculer `courante`. Designer la journee explicitement
        evite de resumer un jour a peine commence a la place de celui qui
        vient de finir.
        """
        if not jour:
            return self.courante, self.precedente
        if self.courante is not None and self.courante.jour == jour:
            return self.courante, self.precedente
        if self.precedente is not None and self.precedente.jour == jour:
            return self.precedente, None
        return None, None

    def rendre(self, jour: str = "") -> str:
        """Recapitulatif d'une journee, comparee a la precedente.

        Chaine vide si rien n'a ete observe : un silence reel ne merite pas un
        message qui dit « rien ».
        """
        j, v = self._journee(jour)
        if j is None or j.total == 0:
            return ""
        comparable = self._comparable(j, v)
        ref = v if comparable else None

        lignes = [f"*RECAPITULATIF — {j.jour}*"]
        lignes.append(f"Observe sur {j.couverture_h:.1f} h")
        lignes.append("")
        lignes.append(
            f"Decisions      {_nombre(j.total)}{_delta(j.total, ref and ref.total)}"
        )
        lignes.append(
            f"Sans signal    {_nombre(j.holds)}{_delta(j.holds, ref and ref.holds)}"
        )
        lignes.append(
            f"Blocages       {_nombre(j.blocages)}"
            f"{_delta(j.blocages, ref and ref.blocages)}"
        )

        if j.couches:
            lignes.append("")
            lignes.append("Par couche")
            for couche, n in j.couches.most_common(_TOP_COUCHES):
                # 0 et non None quand la veille existe : une couche apparue
                # doit afficher (+n), pas un blanc qui se lit « pas de donnee ».
                ancien = ref.couches.get(couche, 0) if ref else None
                lignes.append(f"  {couche:<16}{_nombre(n):>7}{_delta(n, ancien)}")

        lignes += self._mouvements(j, ref)
        lignes += self._avertissement_fenetre(j, v, comparable)
        lignes += self._chronique()
        return "\n".join(lignes)

    @staticmethod
    def _chronique() -> list[str]:
        """Fenetre d'observation du burn-in, relayee depuis la chronique.

        Le Narrateur ne la calcule pas — `tools/burnin_chronicle.py` la
        produit et un timer la rafraichit. Seule la FENETRE est relayee : N
        canonique et la projection vers 500 appartiennent a ①.
        """
        try:
            from observability.narrator.chronicle import lignes as _chronique_lignes

            return _chronique_lignes()
        except Exception:
            return []

    # ── Garde-fous ───────────────────────────────────────────────────────────

    @staticmethod
    def _comparable(j: Journee, v) -> bool:
        if v is None or v.total == 0:
            return False
        return abs(j.couverture_h - v.couverture_h) <= _ECART_FENETRE_MAX_H

    @staticmethod
    def _mouvements(j: Journee, ref) -> list[str]:
        """Couches apparues et disparues — le vrai « qu'est-ce qui a bouge »."""
        if ref is None:
            return []
        apparues = sorted(set(j.couches) - set(ref.couches))
        disparues = sorted(set(ref.couches) - set(j.couches))
        out = []
        if apparues:
            out.append(f"Couches apparues : {', '.join(apparues)}")
        if disparues:
            out.append(f"Couches disparues : {', '.join(disparues)}")
        return [""] + out if out else []

    @staticmethod
    def _avertissement_fenetre(j: Journee, v, comparable: bool) -> list[str]:
        if v is None or v.total == 0:
            return ["", "Premier recapitulatif — aucune veille pour comparer."]
        if comparable:
            return []
        return [
            "",
            f"Fenetres inegales ({j.couverture_h:.1f} h contre "
            f"{v.couverture_h:.1f} h) — les volumes ne sont pas comparables, "
            "aucun ecart n'est affiche.",
        ]
