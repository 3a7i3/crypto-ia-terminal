"""Ledger append-only des admissions de portefeuille (Phase 5.2.2).

Passif : observe et prouve. Ne décide jamais — sinon on créerait une
quatrième autorité (correction opérateur Phase 5.2). Deux événements
distincts persistés dans un JSONL unique :

    ADMISSION_ATTEMPT    (pre-write, journalisation d'intention)
    ADMISSION_OUTCOME    (post-write, résultat de la frontière)

Reliés par ``attempt_id`` — reconstruction causale possible en
post-mortem.

Chemin canonique : ``databases/admission_ledger.jsonl``.
Override : env var ``PAPER_ADMISSION_LEDGER`` (lu au ``__init__``,
pas à l'import — permet ``monkeypatch.setenv`` dans les tests).

Format identique à ``paper_trading/recorder.py`` (JSONL append-only,
une ligne par événement, tolérance aux lignes malformées à la lecture).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Union

from paper_trading.admission_types import (
    AdmissionAttempt,
    AdmissionOutcome,
)

_DEFAULT_PATH = "databases/admission_ledger.jsonl"


def _serialize(event: Union[AdmissionAttempt, AdmissionOutcome]) -> str:
    return json.dumps(asdict(event), ensure_ascii=False) + "\n"


class AdmissionLedger:
    """Journal append-only, thread-friendly.

    L'append d'une ligne courte (< PIPE_BUF, ~4 KiB) est atomique sur
    POSIX. Aucun ``flock`` explicite ici — même politique que
    ``paper_trading/recorder.py`` (audité). Si le besoin de multi-writer
    stricte apparaît, il sera traité comme un changement d'architecture
    séparé, sur les DEUX ledgers.
    """

    def __init__(self, log_path: Optional[str] = None) -> None:
        self._path = Path(
            log_path or os.getenv("PAPER_ADMISSION_LEDGER", _DEFAULT_PATH)
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record_attempt(self, attempt: AdmissionAttempt) -> None:
        self._append(attempt)

    def record_outcome(self, outcome: AdmissionOutcome) -> None:
        self._append(outcome)

    def events(self) -> list[dict]:
        """Lecture brute : liste de dicts, tolérante aux lignes malformées."""
        if not self._path.exists():
            return []
        out: list[dict] = []
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    # Corruption partielle du ledger — ligne ignorée, audit continue
                    pass
        return out

    def pairs(self) -> list[tuple[dict, Optional[dict]]]:
        """Reconstruit les paires ``(attempt, outcome)`` par ``attempt_id``.

        Un attempt sans outcome est retourné avec ``outcome=None`` : signal
        d'écriture avortée avant journalisation du résultat.

        Ordre chronologique par ``attempt_id`` (triable — format
        ``adm_YYYYMMDDTHHMMSS_hex8``).
        """
        attempts: dict[str, dict] = {}
        outcomes: dict[str, dict] = {}
        for evt in self.events():
            aid = evt.get("attempt_id")
            if not aid:
                continue
            if evt.get("event") == "ADMISSION_ATTEMPT":
                attempts[aid] = evt
            elif evt.get("event") == "ADMISSION_OUTCOME":
                outcomes[aid] = evt
        return [(attempts[aid], outcomes.get(aid)) for aid in sorted(attempts)]

    def _append(self, event: Union[AdmissionAttempt, AdmissionOutcome]) -> None:
        line = _serialize(event)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line)


_ledger: Optional[AdmissionLedger] = None


def get_admission_ledger() -> AdmissionLedger:
    """Singleton — lecture env var à l'appel (pas au chargement du module)."""
    global _ledger
    if _ledger is None:
        _ledger = AdmissionLedger()
    return _ledger


def reset_admission_ledger_singleton() -> None:
    """Test hook : force la reconstruction du singleton après ``monkeypatch``."""
    global _ledger
    _ledger = None


__all__ = [
    "AdmissionLedger",
    "get_admission_ledger",
    "reset_admission_ledger_singleton",
]
