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
import threading
import uuid
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

# ------------------------------------------------------------------
# Directory layout
# ------------------------------------------------------------------

LOG_ROOT = Path(__file__).resolve().parent.parent / "logs"
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
    def __init__(self, module: str, category: str) -> None:
        super().__init__()
        self._module = module
        self._category = category

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "trace_id": getattr(record, "trace_id", None) or current_trace_id() or "",
            "module": self._module,
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

            # JSON file handler
            date_str = datetime.now().strftime("%Y-%m-%d")
            log_file = LOG_ROOT / category / f"{date_str}.jsonl"
            fh = RotatingFileHandler(
                log_file, maxBytes=50 * 1024 * 1024, backupCount=7, encoding="utf-8"
            )
            fh.setFormatter(JsonFormatter(self._module, category))
            logger.addHandler(fh)

            # Console handler (human readable)
            ch = logging.StreamHandler()
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
