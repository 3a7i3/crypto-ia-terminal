"""Lecteur de la boite noire — suit le fichier, dechiffre, ne remonte jamais.

Contrat : docs/CONTRAT_SUPERVISEUR.md § 2 « Sources autorisees ».

Lecture SEULE. Le fichier est ouvert en "r", jamais en ecriture, et le
narrateur tourne dans son propre processus : il ne peut pas ralentir ni
perturber le moteur, quoi qu'il fasse.

Deux pieges traites explicitement :

1. **Le demarrage.** Le fichier compte 152 049 lignes (167 Mo, mesure du
   2026-08-06). Se placer au debut inonderait Telegram de deux mois
   d'histoire. On demarre donc en FIN de fichier — le narrateur raconte le
   present, pas les archives.
2. **La rotation.** Si le fichier est remplace ou tronque, la position
   memorisee devient absurde et on lirait du milieu d'une ligne. On detecte
   le changement d'inode et le retrecissement, et on repart proprement.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Iterator

_CHEMIN_DEFAUT = "databases/black_box.jsonl"


def _decodeur():
    """Dechiffreur de la boite noire, ou None s'il est indisponible.

    Import differe : le narrateur doit pouvoir etre teste et importe sans que
    la couche crypto soit presente.
    """
    try:
        from crypto.blackbox_encryption import BlackBoxEncryption

        return BlackBoxEncryption()
    except Exception:
        return None


@dataclass
class BoiteNoire:
    """Suit `black_box.jsonl` et rend les nouvelles entrees dechiffrees."""

    chemin: str = _CHEMIN_DEFAUT
    depuis_la_fin: bool = True

    _position: int = 0
    _signature: tuple = ()
    _amorce: bool = False
    _enc: object = field(default=None, repr=False)
    lignes_illisibles: int = 0

    # ── Etat du fichier ──────────────────────────────────────────────────────

    def _signature_courante(self):
        try:
            st = os.stat(self.chemin)
        except OSError:
            return ()
        return (st.st_dev, st.st_ino)

    def _taille(self) -> int:
        try:
            return os.path.getsize(self.chemin)
        except OSError:
            return 0

    def _amorcer(self) -> None:
        """Place le curseur, une seule fois, sans rien lire."""
        self._amorce = True
        self._signature = self._signature_courante()
        self._position = self._taille() if self.depuis_la_fin else 0

    # ── Lecture ──────────────────────────────────────────────────────────────

    def lire(self) -> Iterator[dict]:
        """Rend les entrees apparues depuis l'appel precedent.

        Ne leve jamais : un narrateur qui plante sur une ligne malformee
        cesserait de raconter, ce qui est pire que de sauter la ligne.
        """
        if not self._amorce:
            self._amorcer()
            return

        signature = self._signature_courante()
        if not signature:
            return
        taille = self._taille()

        if signature != self._signature or taille < self._position:
            # Fichier remplace ou tronque : repartir du debut du NOUVEAU
            # fichier, sinon on lit au milieu d'une ligne.
            self._signature = signature
            self._position = 0

        if taille == self._position:
            return

        if self._enc is None:
            self._enc = _decodeur()

        try:
            with open(self.chemin, encoding="utf-8", errors="replace") as fh:
                fh.seek(self._position)
                lignes = fh.readlines()
                # Une derniere ligne sans "\n" est en cours d'ecriture : on la
                # laisse pour le prochain tour plutot que de la lire coupee.
                if lignes and not lignes[-1].endswith("\n"):
                    incomplete = lignes.pop()
                    self._position = fh.tell() - len(incomplete.encode("utf-8"))
                else:
                    self._position = fh.tell()
        except OSError:
            return

        for ligne in lignes:
            entree = self._decoder(ligne.strip())
            if entree is not None:
                yield entree

    def _decoder(self, ligne: str):
        if not ligne:
            return None
        if self._enc is not None:
            try:
                data = self._enc.decrypt_line(ligne)
                if isinstance(data, str):
                    data = json.loads(data)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        # Repli : entrees en clair d'avant le chiffrement (pre-C-01).
        try:
            data = json.loads(ligne)
        except Exception:
            self.lignes_illisibles += 1
            return None
        return data if isinstance(data, dict) else None
