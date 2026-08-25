"""
Centralized JSON structured logger.

Every log line is a JSON object with:
    timestamp, trace_id, module, event, severity, message, context

Usage:
    from observability.json_logger import get_logger, new_trace_id

    log = get_logger("execution_engine")
    trace = new_trace_id()

    log.info("order_placed", trace_id=trace, symbol="BTCUSDT", qty=0.01)
    log.error("order_failed",  trace_id=trace, error=str(e))

Log files are written to logs/<category>/<date>.jsonl
Categories: runtime, trading, ai, market, errors, incidents, decisions, audits
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

# ------------------------------------------------------------------
# Directory layout
# ------------------------------------------------------------------

# DS-001: surchargeable via env (posée par conftest.py avant tout import
# de module de test) — sinon comportement inchangé, ancré au repo.
LOG_ROOT = Path(
    os.environ.get("OBS_LOG_ROOT") or Path(__file__).resolve().parent.parent / "logs"
)
_CATEGORIES = (
    "runtime",
    "trading",
    "ai",
    "market",
    "errors",
    "incidents",
    "decisions",
    "audits",
)

for _cat in _CATEGORIES:
    (LOG_ROOT / _cat).mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------
# Trace ID context (thread-local)
# ------------------------------------------------------------------

_local = threading.local()


def new_trace_id() -> str:
    return str(uuid.uuid4())


def set_trace_id(trace_id: str) -> None:
    _local.trace_id = trace_id


def current_trace_id() -> str:
    return getattr(_local, "trace_id", "")


# ------------------------------------------------------------------
# JSON formatter
# ------------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    """Formatter for the shared per-category handler.

    The module name is read from the LogRecord (`module_name` extra), not fixed
    at construction — a single handler is shared by every module writing to this
    category, so each line must carry its own producer.
    """

    def __init__(self, category: str) -> None:
        super().__init__()
        self._category = category

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "trace_id": getattr(record, "trace_id", None) or current_trace_id() or "",
            "module": getattr(record, "module_name", None) or record.name,
            "category": self._category,
            "event": getattr(record, "event", ""),
            "severity": record.levelname,
            "message": record.getMessage(),
            "context": getattr(record, "context", {}),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


# ------------------------------------------------------------------
# Shared per-category file handler (R1 — fixes the FD leak)
# ------------------------------------------------------------------
#
# Root cause of the observed leak: the previous code created ONE
# RotatingFileHandler per (module, category). With ~190 modules all logging to
# the shared `runtime` category, ~190 handlers opened the same file; each one
# rotated independently and the others kept the now-deleted inode open and
# wrote into it → FD leak, invisible disk retention, and silent post-rotation
# data loss.
#
# Fix: exactly ONE handler per category, shared by every module. A single owner
# performs rotation under its own lock → no competing rollover, no orphaned
# inode, no lost record. The handler also rolls to a new dated file at midnight
# so the `<date>.jsonl` names are truthful in a long-lived process.


class _DailySizeRotatingHandler(RotatingFileHandler):
    """One shared writer per category: size rotation (.1….7) within a day AND a
    clean switch to a new `<date>.jsonl` file when the calendar day changes."""

    def __init__(
        self,
        category: str,
        *,
        max_bytes: int,
        backup_count: int,
        encoding: str = "utf-8",
    ) -> None:
        self._category = category
        self._current_date = datetime.now().strftime("%Y-%m-%d")
        super().__init__(
            self._path_for(self._current_date),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding=encoding,
        )

    def _path_for(self, date_str: str) -> str:
        return str(LOG_ROOT / self._category / f"{date_str}.jsonl")

    def shouldRollover(self, record: logging.LogRecord) -> int:  # noqa: N802
        if datetime.now().strftime("%Y-%m-%d") != self._current_date:
            return 1
        return super().shouldRollover(record)

    def doRollover(self) -> None:  # noqa: N802
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self._current_date:
            # New day: open a fresh dated file, do NOT shuffle .1….7 backups.
            self._current_date = today
            if self.stream:
                self.stream.close()
                self.stream = None  # type: ignore[assignment]
            self.baseFilename = os.path.abspath(self._path_for(today))
            if not self.delay:
                self.stream = self._open()
            return
        super().doRollover()


_category_handlers: Dict[str, _DailySizeRotatingHandler] = {}
_category_handlers_lock = threading.Lock()


def _get_category_handler(category: str) -> _DailySizeRotatingHandler:
    """Return the single shared file handler for a category (create once)."""
    with _category_handlers_lock:
        h = _category_handlers.get(category)
        if h is None:
            h = _DailySizeRotatingHandler(
                category, max_bytes=50 * 1024 * 1024, backup_count=7
            )
            h.setFormatter(JsonFormatter(category))
            _category_handlers[category] = h
        return h


# ------------------------------------------------------------------
# Structured logger wrapper
# ------------------------------------------------------------------


class StructuredLogger:
    """
    Thin wrapper around stdlib logging that adds:
      - JSON output to the right category file
      - human-readable output to stdout
      - structured keyword arguments (trace_id, context, event)
    """

    _LEVEL_TO_CAT = {
        logging.DEBUG: "runtime",
        logging.INFO: "runtime",
        logging.WARNING: "runtime",
        logging.ERROR: "errors",
        logging.CRITICAL: "incidents",
    }

    def __init__(self, module: str, category: Optional[str] = None) -> None:
        self._module = module
        self._default_category = category
        self._loggers: Dict[str, logging.Logger] = {}
        self._lock = threading.Lock()

    def _get_logger(self, category: str) -> logging.Logger:
        with self._lock:
            if category in self._loggers:
                return self._loggers[category]
            name = f"sys.{self._module}.{category}"
            logger = logging.getLogger(name)
            logger.setLevel(logging.DEBUG)
            logger.propagate = False

            # SHARED JSON file handler — one per category, reused across all
            # modules (R1). Guard against double-attach if the same underlying
            # stdlib logger is reached twice.
            fh = _get_category_handler(category)
            if fh not in logger.handlers:
                logger.addHandler(fh)

            # Console handler (human readable) — per logger, writes to stdout
            # (fd 1), so it never leaks descriptors. Tagged to avoid duplicates.
            if not any(
                getattr(h, "_scios_console", False) for h in logger.handlers
            ):
                ch = logging.StreamHandler()
                ch._scios_console = True  # type: ignore[attr-defined]
                ch.setFormatter(
                    logging.Formatter(
                        f"%(asctime)s [%(levelname)-8s] [{self._module}] %(message)s",
                        datefmt="%H:%M:%S",
                    )
                )
                logger.addHandler(ch)

            self._loggers[category] = logger
            return logger

    def _log(
        self,
        level: int,
        msg: str,
        event: str = "",
        trace_id: str = "",
        context: Optional[Dict] = None,
        category: Optional[str] = None,
    ) -> None:
        cat = (
            category
            or self._default_category
            or self._LEVEL_TO_CAT.get(level, "runtime")
        )
        logger = self._get_logger(cat)
        extra = {
            "event": event,
            "trace_id": trace_id or current_trace_id(),
            "context": context or {},
            # module travels on the record so the shared category handler can
            # label each line with its true producer.
            "module_name": self._module,
        }
        logger.log(level, msg, extra=extra)

    @staticmethod
    def _fmt(event: str, args: tuple) -> str:
        """Format legacy %-style calls: _log.info("msg: %s", val) → "msg: val"."""
        if not args:
            return event
        try:
            return event % args
        except (TypeError, ValueError):
            return f"{event} {args}"

    def debug(self, event: str, *args, msg: str = "", **ctx) -> None:
        self._log(
            logging.DEBUG, self._fmt(msg or event, args), event=event, context=ctx
        )

    def info(self, event: str, *args, msg: str = "", **ctx) -> None:
        self._log(logging.INFO, self._fmt(msg or event, args), event=event, context=ctx)

    def warning(self, event: str, *args, msg: str = "", **ctx) -> None:
        self._log(
            logging.WARNING, self._fmt(msg or event, args), event=event, context=ctx
        )

    def error(self, event: str, *args, msg: str = "", **ctx) -> None:
        self._log(
            logging.ERROR, self._fmt(msg or event, args), event=event, context=ctx
        )

    def critical(self, event: str, *args, msg: str = "", **ctx) -> None:
        self._log(
            logging.CRITICAL, self._fmt(msg or event, args), event=event, context=ctx
        )

    def exception(self, event: str, *args, msg: str = "", **ctx) -> None:
        self._log(
            logging.ERROR, self._fmt(msg or event, args), event=event, context=ctx
        )

    # Category shortcuts
    def trade(self, event: str, **ctx) -> None:
        self._log(logging.INFO, event, event=event, context=ctx, category="trading")

    def decision(self, event: str, **ctx) -> None:
        self._log(logging.INFO, event, event=event, context=ctx, category="decisions")

    def audit(self, event: str, **ctx) -> None:
        self._log(logging.INFO, event, event=event, context=ctx, category="audits")

    def incident(self, event: str, **ctx) -> None:
        self._log(
            logging.CRITICAL, event, event=event, context=ctx, category="incidents"
        )

    def ai(self, event: str, **ctx) -> None:
        self._log(logging.INFO, event, event=event, context=ctx, category="ai")

    def market(self, event: str, **ctx) -> None:
        self._log(logging.INFO, event, event=event, context=ctx, category="market")


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

_loggers: Dict[str, StructuredLogger] = {}
_loggers_lock = threading.Lock()


def get_logger(module: str, category: Optional[str] = None) -> StructuredLogger:
    """Return (or create) a StructuredLogger for a module."""
    key = f"{module}:{category or ''}"
    with _loggers_lock:
        if key not in _loggers:
            _loggers[key] = StructuredLogger(module, category)
        return _loggers[key]
