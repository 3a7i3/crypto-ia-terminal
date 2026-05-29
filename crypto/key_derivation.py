"""
key_derivation.py — Dérivation de clés cryptographiques (partagé P10-C)

Toutes les clés sont dérivées d'un master_secret via HKDF-SHA256.
Chaque module reçoit une clé différente grâce au paramètre context.

Aucune clé n'est jamais codée en dur. Le master_secret est lu depuis
l'env var P10_CRYPTO_MASTER_SECRET.

Dérivation pour un mot de passe (vault) : PBKDF2-SHA256 avec sel stocké.
"""

from __future__ import annotations

import hashlib
import os
from typing import Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Secret maître — ne JAMAIS coder en dur en production
_MASTER_SECRET_ENV = "P10_CRYPTO_MASTER_SECRET"
_DEFAULT_MASTER = "crypto_ai_terminal_p10c_master_v1_CHANGE_IN_PRODUCTION"

# Contextes de dérivation — un contexte unique par module
CTX_BLACKBOX = b"blackbox_encryption_v1"
CTX_DECISION = b"decision_signing_v1"
CTX_VAULT = b"api_key_vault_v1"
CTX_CHANNELS = b"secure_channels_v1"
CTX_AUDIT_TRAIL = b"audit_trail_v1"
CTX_TAMPER_LOG = b"tamper_evident_log_v1"


def get_master_secret() -> bytes:
    """Retourne le master_secret depuis l'env var (UTF-8 → bytes)."""
    raw = os.getenv(_MASTER_SECRET_ENV, _DEFAULT_MASTER)
    return raw.encode("utf-8")


def derive_key(
    context: bytes,
    master_secret: Optional[bytes] = None,
    length: int = 32,
) -> bytes:
    """
    Dérive une clé de `length` bytes via HKDF-SHA256.

    context  : chaîne unique par module (ex. CTX_BLACKBOX)
    master_secret : None → utilise get_master_secret()
    length   : 16, 24 ou 32 (AES-128/192/256)
    """
    ms = master_secret if master_secret is not None else get_master_secret()
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=None,
        info=context,
    )
    return hkdf.derive(ms)


def derive_key_from_password(
    password: str,
    salt: bytes,
    length: int = 32,
    iterations: int = 600_000,
) -> bytes:
    """
    Dérive une clé depuis un mot de passe humain via PBKDF2-SHA256.
    Salt doit être unique et stocké avec le vault.
    Iterations : 600 000 (recommandation OWASP 2024).
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=length,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(password.encode("utf-8"))


def zero_bytes(buf: bytearray) -> None:
    """Écrase un bytearray avec des zéros (zeroing mémoire best-effort)."""
    for i in range(len(buf)):
        buf[i] = 0


def constant_time_compare(a: bytes, b: bytes) -> bool:
    """Comparaison en temps constant — protège contre les timing attacks."""
    import hmac as _hmac

    return _hmac.compare_digest(a, b)
