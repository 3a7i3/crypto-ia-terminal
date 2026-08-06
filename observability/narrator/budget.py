"""Plafond d'emission — fusion ANNONCEE, jamais troncature muette.

Contrat : docs/CONTRAT_SUPERVISEUR.md § 2 « Frequence maximale ».

Deux regles, et la seconde est celle qui compte :

1. Six messages directs par heure au maximum. Au-dela, les evenements sont
   mis en file et fusionnes dans l'agregat suivant.
2. Un plafond franchi est TOUJOURS annonce (« +14 evenements groupes »). Une
   troncature silencieuse se lit comme « il ne s'est rien passe » — c'est la
   meme faute que rendre une donnee absente comme un zero.

Une exception, deliberee : un evenement URGENT (arret, safe mode, vigilance
grave) passe toujours. Un plafond de debit qui avale une alerte de securite
serait un plafond mal concu.

Module pur : aucune I/O, aucune horloge implicite — le temps est un argument.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

_MAX_TITRES_MEMORISES = 12


@dataclass(frozen=True)
class Emission:
    """Ce que le Narrateur doit envoyer maintenant."""

    texte: str
    urgent: bool = False


@dataclass
class Budget:
    max_par_heure: int = 6
    fenetre_s: float = 3600.0

    _emissions: deque = field(default_factory=deque, repr=False)
    _differes_titres: list = field(default_factory=list, repr=False)
    _differes_total: int = 0

    # ── Fenetre glissante ────────────────────────────────────────────────────

    def _purger(self, maintenant: float) -> None:
        limite = maintenant - self.fenetre_s
        while self._emissions and self._emissions[0] <= limite:
            self._emissions.popleft()

    def restant(self, maintenant: float) -> int:
        self._purger(maintenant)
        return max(0, self.max_par_heure - len(self._emissions))

    # ── Offre ────────────────────────────────────────────────────────────────

    def offrir(self, texte: str, maintenant: float, urgent: bool = False):
        """Retourne une Emission si le message part, None s'il est differe.

        Un message differe n'est pas perdu : il est compte, et son titre est
        conserve pour l'agregat suivant.
        """
        if not texte:
            return None
        self._purger(maintenant)

        if urgent:
            # Compte dans la fenetre — pour que le debit reste visible — mais
            # ne peut jamais etre bloque par elle.
            self._emissions.append(maintenant)
            return Emission(texte, urgent=True)

        if len(self._emissions) >= self.max_par_heure:
            self._differer(texte)
            return None

        self._emissions.append(maintenant)
        return Emission(texte, urgent=False)

    def _differer(self, texte: str) -> None:
        self._differes_total += 1
        if len(self._differes_titres) < _MAX_TITRES_MEMORISES:
            self._differes_titres.append(texte.splitlines()[0].strip())

    # ── Reprise ──────────────────────────────────────────────────────────────

    @property
    def differes(self) -> int:
        return self._differes_total

    def vider(self) -> str:
        """Rend le texte des evenements differes, et remet le compteur a zero.

        Chaine vide si rien n'a ete differe — on n'annonce pas une fusion qui
        n'a pas eu lieu.
        """
        if not self._differes_total:
            return ""
        lignes = [f"+{self._differes_total} evenement(s) groupe(s) :"]
        lignes += [f"  · {t}" for t in self._differes_titres]
        reste = self._differes_total - len(self._differes_titres)
        if reste > 0:
            lignes.append(f"  · … et {reste} autre(s)")
        self._differes_titres = []
        self._differes_total = 0
        return "\n".join(lignes)
