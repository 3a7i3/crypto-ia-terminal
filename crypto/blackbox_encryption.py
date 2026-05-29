"""
blackbox_encryption.py — Chiffrement de la BlackBox (C-01)

AES-256-GCM pour le chiffrement. Authentification intégrée (AEAD).
Toute modification du ciphertext → InvalidTag → exception.

Format d'un bloc chiffré :
  [12 bytes nonce][N bytes ciphertext+tag(16)]

Usage :
    enc = BlackBoxEncryption()
    blob = enc.encrypt({"event": "TRADE", "symbol": "BTC/USDT"})
    data = enc.decrypt_to_dict(blob)
"""

from __future__ import annotations

import base64
import json
import os
from typing import Union

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from crypto.key_derivation import CTX_BLACKBOX, derive_key
from observability.json_logger import get_logger

_log = get_logger("crypto.blackbox_encryption")

_NONCE_SIZE = 12  # bytes — GCM standard
_TAG_SIZE = 16  # bytes — GCM tag intégré dans le ciphertext par AESGCM


class BlackBoxEncryption:
    """
    Chiffrement AES-256-GCM pour toutes les entrées de la BlackBox.

    Certification C-01 :
      - Chiffrement AES-256-GCM avec nonce aléatoire par entrée
      - AEAD : modification du ciphertext → InvalidTag détectée automatiquement
      - Rotation de clé via changement du master_secret
      - Aucune clé en clair dans les logs
    """

    def __init__(self, master_secret: Union[str, bytes, None] = None) -> None:
        ms: bytes
        if isinstance(master_secret, str):
            ms = master_secret.encode()
        elif isinstance(master_secret, bytes):
            ms = master_secret
        else:
            ms = None  # type: ignore[assignment]
        self._key = derive_key(CTX_BLACKBOX, master_secret=ms)
        self._aesgcm = AESGCM(self._key)

    # ── Chiffrement ───────────────────────────────────────────────────────────

    def encrypt(self, data: Union[dict, str, bytes]) -> bytes:
        """
        Chiffre data via AES-256-GCM.
        Retourne nonce(12) + ciphertext+tag.
        """
        plaintext = self._to_bytes(data)
        nonce = os.urandom(_NONCE_SIZE)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    def decrypt(self, encrypted: bytes) -> bytes:
        """
        Déchiffre et vérifie l'intégrité.
        Lève cryptography.exceptions.InvalidTag si tampered.
        """
        if len(encrypted) < _NONCE_SIZE + _TAG_SIZE:
            raise ValueError("bloc chiffré trop court")
        nonce = encrypted[:_NONCE_SIZE]
        ciphertext = encrypted[_NONCE_SIZE:]
        return self._aesgcm.decrypt(nonce, ciphertext, None)

    def decrypt_to_dict(self, encrypted: bytes) -> dict:
        return json.loads(self.decrypt(encrypted).decode("utf-8"))

    def decrypt_to_str(self, encrypted: bytes) -> str:
        return self.decrypt(encrypted).decode("utf-8")

    # ── Format JSONL (base64) ─────────────────────────────────────────────────

    def encrypt_line(self, entry: dict) -> str:
        """Chiffre et encode en base64 pour une ligne JSONL."""
        return base64.b64encode(self.encrypt(entry)).decode("ascii")

    def decrypt_line(self, line: str) -> dict:
        """Déchiffre une ligne JSONL base64."""
        return self.decrypt_to_dict(base64.b64decode(line.strip()))

    # ── Rotation de clé ───────────────────────────────────────────────────────

    def reencrypt(self, encrypted: bytes, new_master_secret: bytes) -> bytes:
        """
        Déchiffre avec la clé courante et rechiffre avec une nouvelle clé.
        Utilisé pour la rotation de clé.
        """
        plaintext = self.decrypt(encrypted)
        new_enc = BlackBoxEncryption(master_secret=new_master_secret)
        return new_enc.encrypt(plaintext)

    # ── Interne ───────────────────────────────────────────────────────────────

    @staticmethod
    def _to_bytes(data: Union[dict, str, bytes]) -> bytes:
        if isinstance(data, dict):
            return json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
        if isinstance(data, str):
            return data.encode("utf-8")
        return data
