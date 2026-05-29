"""
decision_signer.py — Signature Ed25519 des DecisionPackets (C-02)

Chaque décision de trading est signée individuellement.
La signature porte : contenu canonique + horodatage signé_at.
Modification du contenu OU du timestamp → InvalidSignature.

Persistance des clés :
  La clé privée Ed25519 est générée une fois et sauvegardée chiffrée
  (AES-256-GCM) dans P10_DECISION_KEY_PATH. Le master_secret la protège.

Usage :
    signer = DecisionSigner()
    signed = signer.sign({"symbol": "BTC/USDT", "action": "BUY", "size": 100.0})
    assert signer.verify(signed)
"""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from crypto.key_derivation import CTX_DECISION, derive_key
from observability.json_logger import get_logger

_log = get_logger("crypto.decision_signer")

_KEY_PATH = Path(
    os.getenv("P10_DECISION_KEY_PATH", "cache/startup/decision_signing.key")
)
_SIG_FIELD = "ed25519_signature"
_TIME_FIELD = "signed_at"


class DecisionSigner:
    """
    Signature Ed25519 des décisions de trading.

    Certification C-02 :
      - Ed25519 — clé 256 bits, signature 64 bytes
      - Signature porte contenu canonique + horodatage
      - Modification de tout champ → InvalidSignature
      - Clé privée chiffrée sur disque (AES-256-GCM via master_secret)
    """

    def __init__(
        self,
        master_secret: Optional[bytes] = None,
        key_path: Optional[Path] = None,
    ) -> None:
        self._key_path = key_path or _KEY_PATH
        self._master_secret = master_secret
        self._private_key = self._load_or_generate()
        self._public_key = self._private_key.public_key()

    # ── API publique ──────────────────────────────────────────────────────────

    def sign(self, packet: dict) -> dict:
        """
        Signe le paquet. Ajoute 'signed_at' et 'ed25519_signature'.
        Toute modification ultérieure invalide la signature.
        """
        signed = {k: v for k, v in packet.items() if k not in (_SIG_FIELD, _TIME_FIELD)}
        signed[_TIME_FIELD] = round(time.time(), 3)
        canonical = _canonical(signed)
        sig_bytes = self._private_key.sign(canonical)
        signed[_SIG_FIELD] = base64.b64encode(sig_bytes).decode("ascii")
        return signed

    def verify(self, signed_packet: dict) -> bool:
        """
        Vérifie la signature Ed25519.
        Retourne False si absent, invalide, ou contenu modifié.
        """
        packet = dict(signed_packet)
        sig_b64 = packet.pop(_SIG_FIELD, None)
        if not sig_b64:
            return False
        try:
            sig_bytes = base64.b64decode(sig_b64)
            canonical = _canonical(packet)
            self._public_key.verify(sig_bytes, canonical)
            return True
        except (InvalidSignature, Exception):
            return False

    def public_key_hex(self) -> str:
        """Retourne la clé publique en hex (pour distribution / vérification externe)."""
        raw = self._public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
        return raw.hex()

    # ── Persistance chiffrée ──────────────────────────────────────────────────

    def _load_or_generate(self) -> Ed25519PrivateKey:
        """Charge la clé depuis disque (déchiffrée) ou génère une nouvelle clé."""
        if self._key_path.exists():
            try:
                return self._load_key()
            except Exception as exc:
                _log.warning(
                    "[DecisionSigner] clé corrompue, nouvelle générée: %s", exc
                )
        return self._generate_and_save()

    def _generate_and_save(self) -> Ed25519PrivateKey:
        key = Ed25519PrivateKey.generate()
        pem = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        self._key_path.parent.mkdir(parents=True, exist_ok=True)
        # Chiffrer la clé PEM avec AES-256-GCM avant stockage
        from crypto.blackbox_encryption import BlackBoxEncryption

        enc = BlackBoxEncryption(master_secret=self._master_secret)
        blob = enc.encrypt(pem)
        self._key_path.write_bytes(blob)
        _log.info("[DecisionSigner] nouvelle clé Ed25519 générée → %s", self._key_path)
        return key

    def _load_key(self) -> Ed25519PrivateKey:
        from cryptography.hazmat.primitives.serialization import load_pem_private_key

        from crypto.blackbox_encryption import BlackBoxEncryption

        blob = self._key_path.read_bytes()
        enc = BlackBoxEncryption(master_secret=self._master_secret)
        pem = enc.decrypt(blob)
        return load_pem_private_key(pem, password=None)


# ── Interne ───────────────────────────────────────────────────────────────────


def _canonical(data: dict) -> bytes:
    """JSON canonique trié pour la signature."""
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
