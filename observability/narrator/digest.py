"""Agregat horaire — une phrase a la place de 1600 evenements.

Contrat : docs/CONTRAT_SUPERVISEUR.md § 2 « En agregat ».

Ce que cet agregat compte, et pourquoi si peu de choses : la matrice de
routage (TELEGRAM_CHANNEL_CONTRACTS.md § 1) attribue deja un proprietaire
unique a presque tout. Les candidats et les scores sont a ④, le seuil
effectif et l'oscillation a ⑤, les trades et l'equity a ②, la sante a ①.

Ce qu'aucun canal ne possede, et qui est donc le territoire propre du
Narrateur : **quelle couche a bloque, et pour quel motif**. C'est la vie
decisionnelle interne — la reponse a « pourquoi les 300 autres candidats
n'ont pas donne de trade ».

Module pur : aucune I/O, aucun import du moteur.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from observability.narrator.events import HOLD, TRADE_REFUSED, _txt, couches_normalisees

_TOP_COUCHES = 5


@dataclass
class Agregat:
    """Accumule la routine d'une periode, puis la rend en quelques lignes."""

    total: int = 0
    holds: int = 0
    blocages: int = 0
    _couches: Counter = field(default_factory=Counter, repr=False)

    @property
    def vide(self) -> bool:
        return self.total == 0

    # ── Accumulation ─────────────────────────────────────────────────────────

    def observer(self, entry: dict) -> None:
        """Comptabilise un evenement de routine. N'emet rien."""
        if not isinstance(entry, dict):
            return
        self.total += 1
        type_ = _txt(entry, "decision_type")
        if type_ == HOLD:
            self.holds += 1
            return
        if type_ != TRADE_REFUSED:
            return
        self.blocages += 1
        for couche in couches_normalisees(entry):
            self._couches[couche] += 1

    # ── Rendu ────────────────────────────────────────────────────────────────

    def rendre(self, differes: str = "", periode: str = "DERNIERE HEURE") -> str:
        """Rend l'agregat et remet les compteurs a zero.

        Retourne "" si rien ne s'est passe ET qu'aucun evenement n'a ete
        differe : un silence reel ne merite pas un message qui dit « rien ».
        """
        if self.vide and not differes:
            self._reset()
            return ""

        lignes = [f"*{periode}*"]
        lignes.append(f"{self.total} decision(s) observee(s)")
        if self.holds:
            lignes.append(f"Sans signal exploitable : {self.holds}")
        if self.blocages:
            lignes.append(f"Blocages : {self.blocages}")
            for couche, n in self._couches.most_common(_TOP_COUCHES):
                lignes.append(f"  · {couche}  {n}")
            reste = len(self._couches) - _TOP_COUCHES
            if reste > 0:
                lignes.append(f"  · … {reste} autre(s) couche(s)")
        # Pas de bloc « motifs les plus frequents » : mesure du 2026-08-06,
        # `reason` vaut « Refus: <refused_by> » — une recopie de la ligne
        # au-dessus, aux valeurs de seuil pres. Le compter n'ajoutait rien et
        # fabriquait une statistique de seuil effectif, propriete du canal ⑤.
        # Le motif complet reste dans le message DIRECT, ou il est utile.
        if differes:
            lignes.append("")
            lignes.append(differes)

        self._reset()
        return "\n".join(lignes)

    def _reset(self) -> None:
        self.total = 0
        self.holds = 0
        self.blocages = 0
        self._couches = Counter()
