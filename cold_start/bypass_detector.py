"""
bypass_detector.py — Détection de contournement du ColdStartManager (A-01)

Principe :
  Quand ColdStartManager atteint LIVE_READY, il écrit un token signé.
  advisor_loop doit appeler check_live_ready_token() avant d'exécuter.
  Si le token est absent ou invalide → BYPASS_DETECTED loggé dans BlackBox.

Token format (cache/startup/live_ready.token) :
  {
    "session_id": "abc12345",
    "warmup_score": 0.91,
    "issued_at": 1716800000.0,
    "valid_for_s": 3600,
    "signature": "<hmac>"
  }
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

from cold_start.warmup_signer import sign, verify
from observability.json_logger import get_logger

_log = get_logger("cold_start.bypass_detector")

_TOKEN_PATH = Path(
    os.getenv("P10_LIVE_READY_TOKEN_PATH", "cache/startup/live_ready.token")
)
# Durée de validité du token (1h par défaut — une session de trading)
_TOKEN_VALID_S = float(os.getenv("P10_TOKEN_VALID_S", "3600.0"))


# ── Écriture du token ─────────────────────────────────────────────────────────


def write_live_ready_token(
    session_id: str,
    warmup_score: float,
    *,
    valid_for_s: float = _TOKEN_VALID_S,
) -> Path:
    """
    Écrit un token LIVE_READY signé sur disque.
    Appelé par ColdStartManager._finalize() quand état = LIVE_READY.
    """
    _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "session_id": session_id,
        "warmup_score": round(warmup_score, 4),
        "issued_at": round(time.time(), 3),
        "valid_for_s": valid_for_s,
    }
    payload["signature"] = sign(payload)

    _TOKEN_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _log.info(
        "[BypassDetector] Token LIVE_READY émis — session=%s score=%.3f",
        session_id,
        warmup_score,
    )
    return _TOKEN_PATH


def revoke_live_ready_token() -> None:
    """Invalide le token (appelé au shutdown propre)."""
    try:
        _TOKEN_PATH.unlink(missing_ok=True)
        _log.info("[BypassDetector] Token révoqué")
    except Exception as exc:
        _log.debug("[BypassDetector] révocation: %s", exc)


# ── Vérification ──────────────────────────────────────────────────────────────


class BypassCheckResult:
    __slots__ = ("ok", "reason", "session_id", "warmup_score", "age_s")

    def __init__(
        self,
        ok: bool,
        reason: str = "",
        session_id: str = "",
        warmup_score: float = 0.0,
        age_s: float = 0.0,
    ) -> None:
        self.ok = ok
        self.reason = reason
        self.session_id = session_id
        self.warmup_score = warmup_score
        self.age_s = age_s

    def __bool__(self) -> bool:
        return self.ok


def check_live_ready_token() -> BypassCheckResult:
    """
    Vérifie que le token LIVE_READY est présent, valide, non expiré.

    Retourne BypassCheckResult.ok = True seulement si tout est bon.
    En cas d'échec, le motif est dans .reason.
    """
    if not _TOKEN_PATH.exists():
        return BypassCheckResult(
            ok=False,
            reason="token absent — ColdStartManager non exécuté ou warmup incomplet",
        )

    try:
        data = json.loads(_TOKEN_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return BypassCheckResult(ok=False, reason=f"token illisible: {exc}")

    # Vérifier signature
    sig = data.pop("signature", "")
    if not verify(data, sig):
        return BypassCheckResult(
            ok=False, reason="signature token invalide — falsification ?"
        )
    data["signature"] = sig  # remettre

    # Vérifier expiration
    issued_at = float(data.get("issued_at", 0))
    valid_for_s = float(data.get("valid_for_s", _TOKEN_VALID_S))
    age_s = time.time() - issued_at
    if age_s > valid_for_s:
        return BypassCheckResult(
            ok=False,
            reason=f"token expiré ({age_s:.0f}s > {valid_for_s:.0f}s) — relancer le warmup",
            age_s=age_s,
        )

    return BypassCheckResult(
        ok=True,
        session_id=data.get("session_id", ""),
        warmup_score=float(data.get("warmup_score", 0.0)),
        age_s=age_s,
    )


def assert_no_bypass(
    black_box_path: str = "databases/black_box.jsonl",
) -> None:
    """
    Vérifie le token et logue BYPASS_DETECTED dans la BlackBox si absent/invalide.
    Lève RuntimeError si bypass détecté — bloque l'exécution live.
    """
    result = check_live_ready_token()
    if not result.ok:
        _log.critical("[BypassDetector] BYPASS DETECTE — %s", result.reason)
        _archive_bypass_event(result.reason, black_box_path)
        raise RuntimeError(
            f"[ColdStart] Bypass ColdStartManager détecté : {result.reason}\n"
            "Le système ne peut pas trader sans warmup validé."
        )
    _log.info(
        "[BypassDetector] Token valide — session=%s score=%.3f age=%.0fs",
        result.session_id,
        result.warmup_score,
        result.age_s,
    )


def _archive_bypass_event(reason: str, bb_path: str) -> None:
    """Archive l'événement BYPASS_DETECTED dans la BlackBox."""
    try:
        p = Path(bb_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "event": "BYPASS_DETECTED",
            "reason": reason,
            "ts": round(time.time(), 3),
        }
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        _log.debug("[BypassDetector] archivage bypass: %s", exc)
