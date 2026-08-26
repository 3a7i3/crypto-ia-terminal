"""Types du contrat d'admission de portefeuille (Phase 5.2.1).

Design (Phase 3 Q4-Q5, Phase 4 §2-§4, corrections opérateur Phase 5.2) :

  * ``AdmissionVerdict`` : verdict produit par la couche décision
    (Level A/B/C). Immuable. Contient les compteurs au moment du check
    pour permettre au simulateur une défense en profondeur TOCTOU
    (re-vérification ``hard_max_at_check`` vs ``len(_positions)`` juste
    avant l'écriture).

  * ``MissingAdmissionVerdict`` : exception TYPÉE distincte d'un rejet.
    Signale un CONTRACT BREACH architectural (aucun verdict n'a été
    calculé). Sémantiquement différent d'un ``REJECTED_BY_POLICY`` :
    l'un est un défaut de câblage, l'autre une décision stratégique
    légitime. Ne jamais confondre.

  * ``AdmissionAttempt`` : événement journal PRE-écriture. Enregistre
    l'intention (``symbol``, snapshot ``n_before``, ``hard_max``,
    verdict brut, ``level`` actif). Persisté AVANT toute mutation
    (voir ``admission_ledger.py``, arrivé au commit P5-02).

  * ``AdmissionOutcome`` : événement journal POST-écriture. Enregistre
    le résultat de la frontière d'écriture (``write_result``,
    ``n_after``, ``position_identity``, ``anomaly``). Relié à l'attempt
    par ``attempt_id``.

Deux événements distincts append-only : jamais de mutation d'une ligne
existante. Cohérent avec ``paper_trades.jsonl`` (OPEN/CLOSE liés par
``trade_id``).

INVARIANT (à faire respecter par ``mexc_simulator`` en P5-04) :
  aucune mutation de ``_virtual_portfolio._positions`` n'a le droit de
  survenir sans un ``AdmissionAttempt`` persisté portant un
  ``attempt_id``, et sans un ``AdmissionOutcome`` ultérieur portant le
  même ``attempt_id``.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class AdmissionLevel(str, Enum):
    """Niveau d'activation courant du contrôle d'admission.

    Piloté par ``PAPER_PORTFOLIO_BRAIN_LEVEL`` (voir P5-04).

    * ``OFF`` — comportement historique, aucun contrôle Level A/B/C.
    * ``A``  — INV-001 seul (canonical ``n_positions < hard_max``).
    * ``B``  — Level A décide + shadow PortfolioBrain journalisé.
    * ``C``  — PortfolioBrain strict devient bloquant. NON activé en P5.
    """

    OFF = "off"
    A = "A"
    B = "B"
    C = "C"


class AdmissionDecision(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AdmissionBlocker(str, Enum):
    """Cause structurée d'un ``REJECTED``.

    Vocabulaire distinct des raisons humaines : chaque valeur pointe
    vers une couche du pipeline. Persisté dans le ledger — casser une
    valeur invaliderait des lignes historiques.
    """

    NONE = "NONE"
    SIGNAL = "SIGNAL"  # INV-002 : personality.max_positions atteint
    PORTFOLIO_HARD_CEILING = "PORTFOLIO_HARD_CEILING"  # INV-001
    PORTFOLIO_STRICT = "PORTFOLIO_STRICT"  # Level C futur (exposure, corr, …)
    OVER_LIMIT_RESTORED = "OVER_LIMIT_RESTORED"  # INV-003
    OVER_LIMIT_POLICY_TIGHTENED = "OVER_LIMIT_POLICY_TIGHTENED"  # INV-004
    STALE_TOCTOU = "STALE_TOCTOU"  # re-vérif à la frontière d'écriture


class WriteResult(str, Enum):
    """Résultat effectif à la frontière d'écriture ``MexcSimulator``."""

    FILLED = "FILLED"
    REJECTED_DUPLICATE = "REJECTED_DUPLICATE"
    REJECTED_INSUFFICIENT_CAPITAL = "REJECTED_INSUFFICIENT_CAPITAL"
    REJECTED_STALE = "REJECTED_STALE"
    REJECTED_ADMISSION = "REJECTED_ADMISSION"


class MissingAdmissionVerdict(Exception):
    """Contrat rompu : la frontière d'écriture a été atteinte sans verdict.

    Distinguer explicitement de :

    * ``REJECTED_BY_POLICY`` : verdict présent, décision négative.
      C'est une décision légitime — journalisée comme
      ``ADMISSION_OUTCOME`` avec ``write_result=REJECTED_ADMISSION``.

    * ``MissingAdmissionVerdict`` : aucun verdict produit — bug
      architectural. Le raise fait remonter la responsabilité à
      l'appelant qui a oublié de produire un verdict avant d'appeler
      ``place_market_order``. Le simulateur ne doit ni approuver ni
      rejeter silencieusement ce cas.
    """

    def __init__(self, symbol: str, context: str = "") -> None:
        self.symbol = symbol
        self.context = context
        message = (
            f"MEXC_ADMISSION_CONTRACT_MISSING: {symbol} — "
            "admission verdict manquant à la frontière d'écriture"
        )
        if context:
            message += f" ({context})"
        super().__init__(message)


def _new_attempt_id() -> str:
    """Attempt ID triable chronologiquement : ``adm_<UTC-YYYYMMDDTHHMMSS>_<hex8>``.

    La granularité seconde suffit pour l'audit ; l'unicité vient du
    fragment UUID (8 hex = 32 bits d'entropie, largement suffisant
    pour éviter les collisions même à haute fréquence).
    """
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
    frag = uuid.uuid4().hex[:8]
    return f"adm_{ts}_{frag}"


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class AdmissionVerdict:
    """Verdict d'admission — produit AVANT le write, consommé par la frontière.

    Les champs ``n_at_check`` et ``hard_max_at_check`` permettent une
    re-vérification TOCTOU côté simulateur : si l'état a bougé entre
    la production du verdict et la mutation, la frontière peut
    refuser (``WriteResult.REJECTED_STALE``) au lieu d'écrire à
    l'aveugle.
    """

    decision: AdmissionDecision
    level: AdmissionLevel
    n_at_check: int
    hard_max_at_check: int
    blocker: AdmissionBlocker = AdmissionBlocker.NONE
    reason: str = ""
    checked_by: str = "unknown"


@dataclass(frozen=True)
class AdmissionAttempt:
    """Événement journal PRE-écriture — persisté avant toute mutation."""

    attempt_id: str
    ts: float
    ts_iso: str
    cycle_id: str
    symbol: str
    n_before: int
    hard_max: int
    level: AdmissionLevel
    decision: AdmissionDecision
    blocker: AdmissionBlocker
    reason: str
    verdict_checked_by: str
    event: str = "ADMISSION_ATTEMPT"
    schema_version: int = 1


@dataclass(frozen=True)
class AdmissionOutcome:
    """Événement journal POST-écriture, relié par ``attempt_id``."""

    attempt_id: str
    ts: float
    ts_iso: str
    symbol: str
    write_result: WriteResult
    n_after: int
    position_identity: str = ""
    anomaly: str = ""
    event: str = "ADMISSION_OUTCOME"
    schema_version: int = 1


def make_attempt(
    verdict: AdmissionVerdict,
    cycle_id: str,
    symbol: str,
) -> AdmissionAttempt:
    """Construit un ``AdmissionAttempt`` capturant l'état du ``verdict``."""
    now = time.time()
    return AdmissionAttempt(
        attempt_id=_new_attempt_id(),
        ts=now,
        ts_iso=_iso(now),
        cycle_id=str(cycle_id),
        symbol=symbol,
        n_before=verdict.n_at_check,
        hard_max=verdict.hard_max_at_check,
        level=verdict.level,
        decision=verdict.decision,
        blocker=verdict.blocker,
        reason=verdict.reason,
        verdict_checked_by=verdict.checked_by,
    )


def make_outcome(
    attempt: AdmissionAttempt,
    write_result: WriteResult,
    n_after: int,
    position_identity: str = "",
    anomaly: str = "",
) -> AdmissionOutcome:
    """Construit un ``AdmissionOutcome`` relié à ``attempt`` par ``attempt_id``."""
    now = time.time()
    return AdmissionOutcome(
        attempt_id=attempt.attempt_id,
        ts=now,
        ts_iso=_iso(now),
        symbol=attempt.symbol,
        write_result=write_result,
        n_after=n_after,
        position_identity=position_identity,
        anomaly=anomaly,
    )


__all__ = [
    "AdmissionAttempt",
    "AdmissionBlocker",
    "AdmissionDecision",
    "AdmissionLevel",
    "AdmissionOutcome",
    "AdmissionVerdict",
    "MissingAdmissionVerdict",
    "WriteResult",
    "make_attempt",
    "make_outcome",
]
