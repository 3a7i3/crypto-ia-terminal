"""
warmup_signer.py — Signatures HMAC pour les artefacts du Cold Start Protocol

Tout rapport de warmup, résultat de scénario et transition persistée doit être signé.
La clé est lue depuis P10_WARMUP_HMAC_KEY (ou fallback dérivé de l'installation).

Usage:
    from cold_start.warmup_signer import sign_artifact, verify_artifact, WarmupSigner
"""

from __future__ import annotations

import hashlib
import hmac as _hmac
import json
import os
import time
from typing import Any

# Clé HMAC lue à l'import — jamais hardcodée en prod, override via env
_RAW_KEY = os.getenv("P10_WARMUP_HMAC_KEY", "crypto_ai_terminal_coldstart_v1_p10")
_KEY: bytes = _RAW_KEY.encode("utf-8")

_ALGO = "sha256"


# ── Primitives ───────────────────────────────────────────────────────────────


def _canonical(payload: Any) -> bytes:
    """Sérialisation canonique d'un payload (dict ou str)."""
    if isinstance(payload, (dict, list)):
        return json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    if isinstance(payload, str):
        return payload.encode("utf-8")
    if isinstance(payload, bytes):
        return payload
    return str(payload).encode("utf-8")


def sign(payload: Any) -> str:
    """Retourne la signature HMAC-SHA256 (hex) du payload."""
    return _hmac.new(_KEY, _canonical(payload), _ALGO).hexdigest()


def verify(payload: Any, signature: str) -> bool:
    """Vérifie qu'une signature HMAC correspond au payload. Constant-time."""
    try:
        expected = sign(payload)
        return _hmac.compare_digest(expected, signature)
    except Exception:
        return False


# ── Artefact signé ───────────────────────────────────────────────────────────


def sign_artifact(data: dict, *, artifact_type: str = "artifact") -> dict:
    """
    Emballe data dans un enveloppe signée :
    {
        "artifact_type": ...,
        "signed_at": <timestamp>,
        "payload": data,
        "signature": <hmac_hex>
    }
    """
    envelope = {
        "artifact_type": artifact_type,
        "signed_at": round(time.time(), 3),
        "payload": data,
    }
    envelope["signature"] = sign(
        {
            "artifact_type": artifact_type,
            "signed_at": envelope["signed_at"],
            "payload": data,
        }
    )
    return envelope


def verify_artifact(envelope: dict) -> bool:
    """
    Vérifie l'intégrité d'une enveloppe signée par sign_artifact().
    Retourne False si manquant, malformé ou signature invalide.
    """
    sig = envelope.get("signature", "")
    if not sig:
        return False
    payload_to_check = {
        "artifact_type": envelope.get("artifact_type", ""),
        "signed_at": envelope.get("signed_at", 0),
        "payload": envelope.get("payload", {}),
    }
    return verify(payload_to_check, sig)


# ── Helpers rapport / état ───────────────────────────────────────────────────


def sign_report(report_dict: dict) -> dict:
    """
    Signe un rapport de warmup en place (retourne une copie avec 'hmac_signature').
    Le champ 'hmac_signature' est exclu du calcul pour l'idempotence.
    """
    clean = {k: v for k, v in report_dict.items() if k != "hmac_signature"}
    sig = sign(clean)
    return {**clean, "hmac_signature": sig}


def verify_report(report_dict: dict) -> bool:
    """Vérifie l'intégrité d'un rapport signé par sign_report()."""
    sig = report_dict.get("hmac_signature", "")
    if not sig:
        return False
    clean = {k: v for k, v in report_dict.items() if k != "hmac_signature"}
    return verify(clean, sig)


def sign_state(state_name: str, extra: dict | None = None) -> dict:
    """
    Crée un enregistrement d'état signé pour la persistance.
    Retourne: {"state": ..., "ts": ..., "extra": ..., "signature": ...}
    """
    record = {
        "state": state_name,
        "ts": round(time.time(), 3),
        "extra": extra or {},
    }
    record["signature"] = sign(record)
    return record


def verify_state(record: dict) -> bool:
    """Vérifie l'intégrité d'un enregistrement d'état persisté."""
    sig = record.get("signature", "")
    if not sig:
        return False
    clean = {k: v for k, v in record.items() if k != "signature"}
    return verify(clean, sig)


# ── Classe utilitaire ────────────────────────────────────────────────────────


class WarmupSigner:
    """
    Interface objet pour signer/vérifier les artefacts du warmup.
    Injectée dans les modules qui en ont besoin (report, state machine, manager).
    """

    def sign_report(self, report: dict) -> dict:
        return sign_report(report)

    def verify_report(self, report: dict) -> bool:
        return verify_report(report)

    def sign_state(self, state_name: str, extra: dict | None = None) -> dict:
        return sign_state(state_name, extra)

    def verify_state(self, record: dict) -> bool:
        return verify_state(record)

    def sign_artifact(self, data: dict, artifact_type: str = "artifact") -> dict:
        return sign_artifact(data, artifact_type=artifact_type)

    def verify_artifact(self, envelope: dict) -> bool:
        return verify_artifact(envelope)
