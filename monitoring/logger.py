"""
monitoring/logger.py — Logger JSON structure (log structuré).

Chaque enregistrement est un objet JSON sur une ligne (JSON Lines / NDJSON).
Thread-safe. Aucune dependance externe.

Format de sortie :
  {"ts": 1747123456.789, "level": "INFO", "component": "execution_simulator",
   "event": "fill_completed", "symbol": "BTCUSDT", "latency_ms": 75}

Usage :
    logger = StructuredLogger("execution_simulator")
    logger.info("fill_completed", symbol="BTCUSDT", latency_ms=75)

    # Logger contextuel (herite du contexte parent)
    child = logger.bind(strategy_id="momentum_v2", fold=3)
    child.warning("low_fill_ratio", fill_ratio=0.4)

    # Sink fichier
    with open("pipeline.jsonl", "w") as f:
        logger = StructuredLogger("pipeline", sink=file_sink(f))
"""

from __future__ import annotations

import json
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, TextIO

# ---------------------------------------------------------------------------
# Niveaux
# ---------------------------------------------------------------------------

LEVELS: dict[str, int] = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}
_LEVEL_NAMES = {v: k for k, v in LEVELS.items()}
DEFAULT_LEVEL = "INFO"

Sink = Callable[["LogRecord"], None]


# ---------------------------------------------------------------------------
# LogRecord
# ---------------------------------------------------------------------------


@dataclass
class LogRecord:
    ts: float
    level: str
    component: str
    event: str
    data: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "ts": round(self.ts, 6),
            "level": self.level,
            "component": self.component,
            "event": self.event,
            **self.data,
        }

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False)


# ---------------------------------------------------------------------------
# Sinks
# ---------------------------------------------------------------------------


def file_sink(f: TextIO) -> Sink:
    """Sink ecrivant chaque record comme une ligne JSON dans `f`."""
    _lock = threading.Lock()

    def _write(record: LogRecord) -> None:
        line = record.as_json()
        with _lock:
            f.write(line + "\n")
            f.flush()

    return _write


def stderr_sink() -> Sink:
    return file_sink(sys.stderr)


def null_sink() -> Sink:
    """Sink muet — utile pour les tests ou le mode silencieux."""
    return lambda _: None


def memory_sink(records: list) -> Sink:
    """Sink qui accumule les LogRecord dans une liste (utile pour les tests)."""
    _lock = threading.Lock()

    def _append(record: LogRecord) -> None:
        with _lock:
            records.append(record)

    return _append


# ---------------------------------------------------------------------------
# StructuredLogger
# ---------------------------------------------------------------------------


class StructuredLogger:
    """
    Logger JSON structure thread-safe.

    component : nom du module/composant (ex : "execution_simulator")
    sink      : callable(LogRecord) — default stderr_sink()
    level     : niveau minimum pour emettre un log (DEBUG/INFO/WARNING/ERROR/CRITICAL)
    _ctx      : contexte herite (ne pas passer manuellement — utiliser bind())
    """

    def __init__(
        self,
        component: str,
        sink: Optional[Sink] = None,
        level: str = DEFAULT_LEVEL,
        _ctx: Optional[dict] = None,
    ) -> None:
        self.component = component
        self._sink = sink if sink is not None else stderr_sink()
        self._min_level = LEVELS.get(level.upper(), LEVELS[DEFAULT_LEVEL])
        self._ctx: dict = _ctx or {}

    def bind(self, **ctx) -> "StructuredLogger":
        """
        Retourne un nouveau logger avec le contexte enrichi.
        Utile pour propager fold_index, symbol, strategy_id, etc.
        """
        return StructuredLogger(
            component=self.component,
            sink=self._sink,
            level=_LEVEL_NAMES.get(self._min_level, DEFAULT_LEVEL),
            _ctx={**self._ctx, **ctx},
        )

    def _emit(self, level: str, event: str, **data) -> None:
        level_val = LEVELS.get(level, 0)
        if level_val < self._min_level:
            return
        record = LogRecord(
            ts=time.time(),
            level=level,
            component=self.component,
            event=event,
            data={**self._ctx, **data},
        )
        self._sink(record)

    def debug(self, event: str, **data) -> None:
        self._emit("DEBUG", event, **data)

    def info(self, event: str, **data) -> None:
        self._emit("INFO", event, **data)

    def warning(self, event: str, **data) -> None:
        self._emit("WARNING", event, **data)

    def error(self, event: str, **data) -> None:
        self._emit("ERROR", event, **data)

    def critical(self, event: str, **data) -> None:
        self._emit("CRITICAL", event, **data)
