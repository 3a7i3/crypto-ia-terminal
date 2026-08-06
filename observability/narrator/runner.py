"""Le Narrateur — assemblage et boucle.

Contrat : docs/CONTRAT_SUPERVISEUR.md.

`Narrateur.absorber()` est PUR : il prend des entrees et une heure, il rend
des messages. Aucune I/O, donc entierement testable. Toute la plomberie
(fichier, reseau, sommeil) vit dans `boucle()`, qui n'a pas de logique.

Processus SEPARE du moteur (ADR-0007). Il lit un fichier et parle a Telegram.
Il ne peut influencer aucune decision, meme en cas de bug : il n'a aucun
chemin d'ecriture vers le moteur.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from observability.narrator.budget import Budget, Emission
from observability.narrator.daily import Quotidien, jour_de
from observability.narrator.digest import Agregat
from observability.narrator.events import IGNORE, ROUTINE, classify

PERIODE_AGREGAT_S = 3600.0
_INTERVALLE_LECTURE_S = 20.0


@dataclass
class Narrateur:
    budget: Budget = field(default_factory=Budget)
    agregat: Agregat = field(default_factory=Agregat)
    quotidien: Quotidien = field(default_factory=Quotidien)
    periode_agregat_s: float = PERIODE_AGREGAT_S

    _prochain_agregat: float = 0.0
    _jour_courant: str = ""
    _deja_vu: set = field(default_factory=set, repr=False)

    # ── Coeur ────────────────────────────────────────────────────────────────

    def absorber(self, entrees: Iterable[dict], maintenant: float) -> list[Emission]:
        """Range les entrees, rend ce qui doit partir maintenant."""
        if not self._prochain_agregat:
            self._prochain_agregat = maintenant + self.periode_agregat_s

        sorties: list[Emission] = []

        for entree in entrees:
            verdict = classify(entree, self._deja_vu)

            if verdict.registre == IGNORE:
                continue

            # Le quotidien compte TOUT ce que le narrateur possede — direct
            # comme routine. L'agregat horaire, lui, ne porte que la routine :
            # un evenement deja raconte a l'unite n'a pas a etre recompte dans
            # le resume de l'heure.
            self.quotidien.observer(entree)

            if verdict.registre == ROUTINE:
                self.agregat.observer(entree)
                continue

            if verdict.cle:
                self._deja_vu.add(verdict.cle)

            quand = _ts(entree, maintenant)
            emission = self.budget.offrir(verdict.texte, quand, verdict.urgent)
            if emission is not None:
                sorties.append(emission)
            else:
                # Differe : il est deja compte par le budget, mais il doit
                # aussi peser dans l'agregat — sinon un evenement plafonne
                # disparaitrait des deux comptages a la fois.
                self.agregat.observer(entree)

        sorties += self._recapitulatif(maintenant)
        sorties += self._echeance(maintenant)
        return sorties

    def _recapitulatif(self, maintenant: float) -> list[Emission]:
        """Emet le recap de la journee ecoulee, au passage de minuit UTC."""
        jour = jour_de(maintenant)
        if not self._jour_courant:
            self._jour_courant = jour
            return []
        if jour == self._jour_courant:
            return []
        fini, self._jour_courant = self._jour_courant, jour
        texte = self.quotidien.rendre(fini)
        return [Emission(texte)] if texte else []

    def _echeance(self, maintenant: float) -> list[Emission]:
        if maintenant < self._prochain_agregat:
            return []
        self._prochain_agregat = maintenant + self.periode_agregat_s
        self._oublier_les_vieux_jours(maintenant)
        texte = self.agregat.rendre(self.budget.vider())
        return [Emission(texte)] if texte else []

    def _oublier_les_vieux_jours(self, maintenant: float) -> None:
        """Purge les cles de deduplication des jours passes.

        Sans cela l'ensemble grossit sans fin, et surtout « premier blocage du
        jour » finirait par ne plus jamais se declencher.
        """
        jour = datetime.fromtimestamp(maintenant, timezone.utc).strftime("%Y-%m-%d")
        self._deja_vu = {c for c in self._deja_vu if f":{jour}:" in f":{c}"}

    # ── Boucle ───────────────────────────────────────────────────────────────

    def boucle(self, source, emetteur, intervalle_s: float = _INTERVALLE_LECTURE_S):
        """Tourne jusqu'a interruption. Toute la plomberie est ici."""
        while True:
            try:
                for emission in self.absorber(source.lire(), time.time()):
                    emetteur.envoyer(emission.texte)
            except Exception:  # noqa: BLE001 — un narrateur ne doit jamais mourir
                pass
            time.sleep(intervalle_s)


def _ts(entree: dict, defaut: float) -> float:
    try:
        return float(entree.get("ts") or defaut)
    except (TypeError, ValueError):
        return defaut


def main() -> None:  # pragma: no cover — plomberie
    from observability.json_logger import get_logger
    from observability.narrator.reader import BoiteNoire
    from observability.narrator.sender import Emetteur

    log = get_logger("observability.narrator")
    emetteur = Emetteur(log=log)
    if not emetteur.configure:
        emetteur.envoyer("")  # declenche l'avertissement unique
    log.info(
        "[Narrateur] demarre — agregat toutes les %.0f min", PERIODE_AGREGAT_S / 60
    )
    Narrateur().boucle(BoiteNoire(), emetteur)


if __name__ == "__main__":  # pragma: no cover
    main()
