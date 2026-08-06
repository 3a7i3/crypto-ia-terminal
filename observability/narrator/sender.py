"""Emetteur Telegram du Narrateur — dedie, sans repli.

Contrat : docs/CONTRAT_SUPERVISEUR.md § 2, et la regle de canal etablie le
2026-08-05 (commit 19d9eae, « supprime les replis silencieux entre canaux ») :

  Si le canal n'est pas configure, RIEN n'est emis et un avertissement est
  journalise UNE FOIS. Aucun repli vers un autre canal — deverser la vie
  interne du moteur dans le canal marche ou le canal portefeuille serait
  exactement la confusion que les contrats existent pour empecher.

Variables attendues, a renseigner par l'operateur — jamais par un agent :

    NARRATOR_BOT_TOKEN=...
    NARRATOR_CHAT_ID=...
"""

from __future__ import annotations

import json
import os
import urllib.request

_LIMITE_TELEGRAM = 4000


class Emetteur:
    """Envoi Telegram, silencieux et signale une fois si non configure."""

    def __init__(self, token: str = "", chat_id: str = "", log=None) -> None:
        self._token = token or os.getenv("NARRATOR_BOT_TOKEN", "")
        self._chat = str(chat_id or os.getenv("NARRATOR_CHAT_ID", ""))
        self._log = log
        self._averti = False
        self.envoyes = 0
        self.echecs = 0

    @property
    def configure(self) -> bool:
        return bool(self._token and self._chat)

    def envoyer(self, texte: str) -> bool:
        if not texte:
            return False
        if not self.configure:
            self._avertir_une_fois()
            return False
        try:
            payload = json.dumps(
                {"chat_id": self._chat, "text": texte[:_LIMITE_TELEGRAM]}
            ).encode("utf-8")
            requete = urllib.request.Request(
                f"https://api.telegram.org/bot{self._token}/sendMessage",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(requete, timeout=10) as reponse:
                ok = reponse.status == 200
        except Exception as exc:
            self.echecs += 1
            if self._log:
                self._log.debug("[Narrateur] envoi echoue: %s", exc)
            return False
        if ok:
            self.envoyes += 1
        else:
            self.echecs += 1
        return ok

    def _avertir_une_fois(self) -> None:
        if self._averti:
            return
        self._averti = True
        if self._log:
            self._log.warning(
                "[Narrateur] NARRATOR_BOT_TOKEN / NARRATOR_CHAT_ID non "
                "configures — narration DESACTIVEE. Aucun repli : la vie "
                "decisionnelle interne n'a pas d'autre canal legitime."
            )
