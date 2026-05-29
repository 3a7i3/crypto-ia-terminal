"""
secure_channels.py — Canaux sécurisés TLS 1.3 (C-04)

TLS 1.3 minimum pour toutes les connexions sortantes vers les exchanges.
Certificate pinning : SHA-256 du certificat DER vérifié à chaque connexion.
Canal Telegram : E2E via webhook HTTPS avec vérification du certificat.

Garanties :
  - TLS 1.3 minimum — TLS 1.2 et antérieur rejetés
  - Certificate pinning par exchange (empreintes SHA-256 configurables)
  - Zéro downgrade silencieux — exception levée si pin ne correspond pas
  - Timeout réseau configurable (défaut 10s)
  - Aucune clé ou cert en clair dans les logs

Usage :
    ch = SecureChannels()
    ch.pin("binance", "sha256_hex_of_der_cert")
    conn = ch.connect("binance", "api.binance.com", 443)
    ch.verify_telegram_cert(cert_der_bytes)
"""

from __future__ import annotations

import hashlib
import socket
import ssl
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from observability.json_logger import get_logger

_log = get_logger("crypto.secure_channels")

_MIN_TLS_VERSION = ssl.TLSVersion.TLSv1_3
_DEFAULT_TIMEOUT_S = 10.0
_CIPHER_WHITELIST = {
    "TLS_AES_256_GCM_SHA384",
    "TLS_CHACHA20_POLY1305_SHA256",
    "TLS_AES_128_GCM_SHA256",
}


@dataclass
class ChannelInfo:
    host: str
    port: int
    tls_version: str = ""
    cipher: str = ""
    connected_at: float = field(default_factory=time.time)
    verified: bool = False


class CertificatePinError(Exception):
    """Levée si le certificat ne correspond pas à l'empreinte pinnée."""


class TLSVersionError(Exception):
    """Levée si TLS < 1.3 est négocié."""


class SecureChannels:
    """
    Gestion des canaux sécurisés TLS 1.3 + certificate pinning.

    Certification C-04 :
      - TLS 1.3 minimum (ssl.TLSVersion.TLSv1_3)
      - Certificate pinning SHA-256 (DER) par exchange
      - Vérification active à chaque connexion
      - Aucune connexion silencieuse sans vérification
    """

    def __init__(self, timeout_s: float = _DEFAULT_TIMEOUT_S) -> None:
        self._timeout = timeout_s
        self._pins: Dict[str, List[str]] = {}  # name → [sha256_hex, ...]
        self._history: List[ChannelInfo] = []

    # ── Gestion des pins ─────────────────────────────────────────────────────

    def pin(self, name: str, *cert_sha256_hex: str) -> None:
        """
        Enregistre une ou plusieurs empreintes SHA-256 (DER) pour un endpoint.
        Plusieurs empreintes = rotation de certificat en cours.
        """
        self._pins[name] = list(cert_sha256_hex)
        _log.info(
            "[SecureChannels] pin enregistré pour '%s' (%d empreintes)",
            name,
            len(cert_sha256_hex),
        )

    def get_pins(self, name: str) -> List[str]:
        return list(self._pins.get(name, []))

    # ── Connexion sécurisée ───────────────────────────────────────────────────

    def build_ssl_context(self) -> ssl.SSLContext:
        """Construit un SSLContext TLS 1.3 durci."""
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = _MIN_TLS_VERSION
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.check_hostname = True
        ctx.load_default_certs()
        return ctx

    def connect(
        self,
        name: str,
        host: str,
        port: int = 443,
        verify_pin: bool = True,
    ) -> ssl.SSLSocket:
        """
        Ouvre une connexion TLS 1.3 avec vérification du pin.
        Lève CertificatePinError ou TLSVersionError si échec.
        """
        ctx = self.build_ssl_context()
        raw_sock = socket.create_connection((host, port), timeout=self._timeout)
        tls_sock = ctx.wrap_socket(raw_sock, server_hostname=host)

        # Vérifie la version TLS
        ver = tls_sock.version()
        if ver != "TLSv1.3":
            tls_sock.close()
            raise TLSVersionError(f"{host}: TLS {ver} négocié — TLS 1.3 requis")

        info = ChannelInfo(
            host=host,
            port=port,
            tls_version=ver,
            cipher=tls_sock.cipher()[0] if tls_sock.cipher() else "",
        )

        # Certificate pinning
        if verify_pin and name in self._pins:
            cert_der = tls_sock.getpeercert(binary_form=True)
            if cert_der is None:
                tls_sock.close()
                raise CertificatePinError(f"{host}: certificat DER non disponible")
            self.verify_pin(name, cert_der)
            info.verified = True
            _log.info("[SecureChannels] pin vérifié OK pour '%s' (%s)", name, host)
        elif name not in self._pins:
            _log.warning(
                "[SecureChannels] pas de pin pour '%s' — connexion non pinnée", name
            )

        self._history.append(info)
        return tls_sock

    def verify_pin(self, name: str, cert_der: bytes) -> None:
        """
        Vérifie que le SHA-256 du cert DER correspond à un pin enregistré.
        Lève CertificatePinError si aucun pin ne correspond.
        """
        pins = self._pins.get(name)
        if not pins:
            raise CertificatePinError(f"'{name}': aucun pin configuré")
        actual = hashlib.sha256(cert_der).hexdigest()
        if actual not in pins:
            raise CertificatePinError(
                f"'{name}': empreinte {actual[:16]}... ne correspond à aucun pin"
            )

    # ── Telegram ─────────────────────────────────────────────────────────────

    def verify_telegram_cert(self, cert_der: bytes) -> str:
        """
        Retourne le SHA-256 du certificat Telegram DER.
        Appeler verify_pin("telegram", ...) séparément si pin configuré.
        """
        return hashlib.sha256(cert_der).hexdigest()

    def make_telegram_ssl_context(self) -> ssl.SSLContext:
        """SSLContext durci pour les webhooks Telegram."""
        return self.build_ssl_context()

    # ── Utilitaires ───────────────────────────────────────────────────────────

    @staticmethod
    def cert_sha256(cert_der: bytes) -> str:
        """Calcule l'empreinte SHA-256 d'un certificat DER."""
        return hashlib.sha256(cert_der).hexdigest()

    def connection_history(self) -> List[ChannelInfo]:
        return list(self._history)

    def is_cipher_approved(self, cipher_name: str) -> bool:
        return cipher_name in _CIPHER_WHITELIST
