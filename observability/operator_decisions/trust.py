"""Politique de confiance D5B-R2 (prototype hors runtime) — voir ADR-0020.

Vérification Ed25519 d'énoncés signés sur un encodage canonique (JSON trié,
séparateurs compacts, UTF-8). La politique (`TrustPolicy`) est une
configuration du VÉRIFICATEUR, passée au constructeur de
`DurableGovernedStore` ; aucune clé, aucun booléen ni aucune référence
fournis dans une requête n'établissent leur propre autorité.

Aucune autorité réelle n'est désignée (ADR-0020 §3) : toute politique
construite ici est `operational=False` par défaut et les clés des tests sont
des fixtures non opérationnelles générées à la volée.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from observability.operator_decisions.producer import ContractError

ADMISSION_APPROVER = "ADMISSION_APPROVER"
AVAILABILITY_AUTHORITY = "AVAILABILITY_AUTHORITY"
ROLES = frozenset({ADMISSION_APPROVER, AVAILABILITY_AUTHORITY})

ADMISSION_APPROVAL = "ADMISSION_APPROVAL"
AVAILABILITY_ATTESTATION = "AVAILABILITY_ATTESTATION"

# Rang de priorité (plus grand = plus urgent) — sert uniquement à refuser une
# auto-promotion ; aucune règle de décision nouvelle n'est introduite.
PRIORITY_RANK = {"UNKNOWN": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


class TrustError(ContractError):
    """Un énoncé signé n'est pas authentique ou pas autorisé : échec fermé."""


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def parse_utc(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise TrustError(f"{label} : horodatage UTC 'Z' requis")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TrustError(f"{label} : horodatage invalide") from exc
    return parsed


@dataclass(frozen=True)
class TrustedKey:
    key_id: str
    role: str
    identity: str
    public_key: bytes  # clé publique Ed25519 brute (32 octets)
    scopes: frozenset[str] = frozenset()  # owner_registry autorisés (approbateur)


@dataclass(frozen=True)
class SignedStatement:
    """Énoncé signé : charge canonique + identifiant de clé + signature hex.

    Aucune clé publique n'est transportée : `key_id` est résolu dans la
    politique du vérificateur.
    """

    payload: Mapping
    key_id: str
    signature_hex: str

    def digest_material(self) -> dict:
        return {"payload": dict(self.payload), "key_id": self.key_id,
                "signature_hex": self.signature_hex}


@dataclass(frozen=True)
class TrustPolicy:
    policy_version: str
    keys: tuple[TrustedKey, ...]
    revoked_key_ids: frozenset[str] = frozenset()
    max_clock_skew_seconds: int = 60
    max_validity_seconds: int = 3600
    operational: bool = False  # ADR-0020 §3 : aucune autorité réelle désignée
    _index: dict = field(default_factory=dict, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.policy_version, str) or not self.policy_version.strip():
            raise ContractError("version de politique requise")
        if self.operational:
            raise ContractError(
                "politique opérationnelle refusée : aucune autorité de confiance "
                "réelle n'est désignée (ADR-0020 §3, blocage de certification)"
            )
        index: dict[str, TrustedKey] = {}
        identities: dict[str, str] = {}
        for key in self.keys:
            if not isinstance(key, TrustedKey) or key.role not in ROLES:
                raise ContractError("clé de confiance ou rôle invalide")
            if key.key_id in index:
                raise ContractError("identifiant de clé dupliqué")
            if identities.setdefault(key.identity, key.role) != key.role:
                raise ContractError(
                    "une même identité ne peut détenir les deux rôles "
                    "(séparation des pouvoirs)"
                )
            Ed25519PublicKey.from_public_bytes(key.public_key)  # valide le format
            index[key.key_id] = key
        object.__setattr__(self, "_index", index)

    def verify(self, statement: object, *, role: str, statement_type: str) -> tuple[dict, TrustedKey]:
        """Vérifie signature, clé, rôle, révocation, type et version de politique."""
        if not isinstance(statement, SignedStatement):
            raise TrustError("énoncé signé requis (aucune preuve libre acceptée)")
        key = self._index.get(statement.key_id)
        if key is None:
            raise TrustError("clé inconnue de la politique du vérificateur")
        if statement.key_id in self.revoked_key_ids:
            raise TrustError("clé révoquée")
        if key.role != role:
            raise TrustError(f"rôle incorrect : {key.role} au lieu de {role}")
        payload = dict(statement.payload)
        try:
            signature = bytes.fromhex(statement.signature_hex)
            Ed25519PublicKey.from_public_bytes(key.public_key).verify(
                signature, canonical_bytes(payload)
            )
        except (InvalidSignature, ValueError, TypeError) as exc:
            raise TrustError("signature invalide") from exc
        if payload.get("statement_type") != statement_type:
            raise TrustError("type d'énoncé inattendu")
        if payload.get("policy_version") != self.policy_version:
            raise TrustError("version de politique inconnue du vérificateur")
        return payload, key

    def check_validity(self, payload: Mapping, now: datetime) -> None:
        """Fenêtre de validité, dérive d'horloge et durée maximale (ADR-0020 §9)."""
        issued = parse_utc(payload.get("issued_at_utc"), "issued_at_utc")
        expires = parse_utc(payload.get("expires_at_utc"), "expires_at_utc")
        if now.tzinfo is None:
            raise TrustError("horloge injectée : datetime UTC conscient requis")
        skew = timedelta(seconds=self.max_clock_skew_seconds)
        if expires <= issued or expires - issued > timedelta(seconds=self.max_validity_seconds):
            raise TrustError("durée de validité invalide ou excessive")
        if issued - skew > now:
            raise TrustError("énoncé émis dans le futur (hors tolérance de dérive)")
        if now >= expires:
            raise TrustError("énoncé expiré")


# --- Outils de fixture (tests uniquement, jamais opérationnels) -------------

def sign_statement(private_key: Ed25519PrivateKey, key_id: str, payload: Mapping) -> SignedStatement:
    """Signe une charge. Réservé aux fixtures NON OPÉRATIONNELLES des tests."""
    body = dict(payload)
    return SignedStatement(body, key_id, private_key.sign(canonical_bytes(body)).hex())


def public_bytes(private_key: Ed25519PrivateKey) -> bytes:
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    return private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def trusted_key(private_key: Ed25519PrivateKey, key_id: str, role: str,
                identity: str, scopes: Iterable[str] = ()) -> TrustedKey:
    return TrustedKey(key_id, role, identity, public_bytes(private_key), frozenset(scopes))


__all__ = [
    "ADMISSION_APPROVAL", "ADMISSION_APPROVER", "AVAILABILITY_ATTESTATION",
    "AVAILABILITY_AUTHORITY", "PRIORITY_RANK", "SignedStatement", "TrustError",
    "TrustPolicy", "TrustedKey", "canonical_bytes", "parse_utc",
    "public_bytes", "sign_statement", "trusted_key",
]
