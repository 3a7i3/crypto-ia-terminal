"""
Error Bus — central exception capture, categorization, and routing.

Every unhandled exception in the system should flow through here.
The bus:
  - assigns a category and severity to each error
  - routes to subscribers (incident manager, alerting, logging)
  - tracks error rates per module
  - triggers PANIC if a critical error threshold is exceeded

Usage:
    from errors.error_bus import error_bus, ErrorCategory

    # From any module's except block:
    try:
        risky_operation()
    except Exception as e:
        error_bus.emit(
            module="execution_engine",
            error=e,
            trace_id=trace_id,
            category=ErrorCategory.EXECUTION,
            context={"symbol": "BTCUSDT", "side": "long"},
        )

    # Subscribe to errors:
    error_bus.subscribe(ErrorCategory.EXECUTION, my_alert_fn)

    # Global exception hook (install once at startup):
    error_bus.install_global_hook()
"""

from __future__ import annotations

import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

from observability.json_logger import get_logger
from observability.metrics_bus import metrics_bus

log = get_logger("error_bus", category="errors")


class ErrorCategory(Enum):
    EXECUTION = auto()  # order placement, fills
    EXCHANGE = auto()  # API errors, connectivity
    DATA = auto()  # market data, feed corruption
    AI = auto()  # model errors, NaN, assertion
    RISK = auto()  # risk engine failures
    SYSTEM = auto()  # OS, memory, process
    WEBSOCKET = auto()  # websocket disconnects, corruption
    DATABASE = auto()  # persistence failures
    UNKNOWN = auto()


class ErrorSeverity(Enum):
    LOW = 1  # logged, no action
    MEDIUM = 2  # logged + metric + warning
    HIGH = 3  # logged + metric + alert + module DEGRADED
    CRITICAL = 4  # logged + metric + alert + possible PANIC


# Severity mapping per category (default)
_CATEGORY_DEFAULT_SEVERITY: Dict[ErrorCategory, ErrorSeverity] = {
    ErrorCategory.EXECUTION: ErrorSeverity.HIGH,
    ErrorCategory.EXCHANGE: ErrorSeverity.HIGH,
    ErrorCategory.DATA: ErrorSeverity.MEDIUM,
    ErrorCategory.AI: ErrorSeverity.MEDIUM,
    ErrorCategory.RISK: ErrorSeverity.CRITICAL,
    ErrorCategory.SYSTEM: ErrorSeverity.CRITICAL,
    ErrorCategory.WEBSOCKET: ErrorSeverity.HIGH,
    ErrorCategory.DATABASE: ErrorSeverity.HIGH,
    ErrorCategory.UNKNOWN: ErrorSeverity.MEDIUM,
}

# How many CRITICAL errors per module before forcing PANIC
PANIC_THRESHOLD = 5
PANIC_WINDOW_SEC = 300.0  # within 5 minutes


@dataclass
class ErrorEvent:
    module: str
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    trace_id: str = ""
    exception_type: str = ""
    traceback: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "trace_id": self.trace_id,
            "module": self.module,
            "category": self.category.name,
            "severity": self.severity.name,
            "exception_type": self.exception_type,
            "message": self.message,
            "context": self.context,
            "traceback": self.traceback,
        }


# Callback type
ErrorHandler = Callable[[ErrorEvent], None]


class ErrorBus:
    """
    Central error routing hub. Thread-safe.
    Modules emit errors here; subscribers receive them.
    """

    def __init__(self) -> None:
        self._subscribers: Dict[Optional[ErrorCategory], List[ErrorHandler]] = {}
        self._history: List[ErrorEvent] = []
        self._critical_timestamps: Dict[str, List[float]] = {}  # module -> timestamps
        self._lock = threading.RLock()
        self._max_history = 5_000

    # ------------------------------------------------------------------
    # Emit API
    # ------------------------------------------------------------------

    def emit(
        self,
        module: str,
        error: Exception,
        trace_id: str = "",
        category: Optional[ErrorCategory] = None,
        severity: Optional[ErrorSeverity] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ErrorEvent:
        cat = category or ErrorCategory.UNKNOWN
        sev = severity or _CATEGORY_DEFAULT_SEVERITY.get(cat, ErrorSeverity.MEDIUM)

        tb = traceback.format_exc()
        event = ErrorEvent(
            module=module,
            category=cat,
            severity=sev,
            message=str(error),
            trace_id=trace_id,
            exception_type=type(error).__name__,
            traceback=tb if tb != "NoneType: None\n" else "",
            context=context or {},
        )

        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history.pop(0)

        # Metrics
        metrics_bus.increment(module, f"errors.{cat.name.lower()}")
        metrics_bus.increment("error_bus", f"total.{sev.name.lower()}")

        # Log
        if sev in {ErrorSeverity.HIGH, ErrorSeverity.CRITICAL}:
            log.error(
                "error_emitted",
                module=module,
                category=cat.name,
                severity=sev.name,
                trace_id=trace_id,
                error_type=type(error).__name__,
                message=str(error),
            )
        else:
            log.warning(
                "error_emitted",
                module=module,
                category=cat.name,
                severity=sev.name,
                message=str(error),
            )

        # Update module registry
        from system.module_registry import module_registry

        module_registry.report_error(module, str(error))

        # Notify subscribers
        self._dispatch(event)

        # PANIC threshold check
        if sev == ErrorSeverity.CRITICAL:
            self._check_panic_threshold(module, event)

        return event

    def emit_raw(
        self,
        module: str,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        trace_id: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> ErrorEvent:
        """Emit an error without an exception object."""
        return self.emit(
            module=module,
            error=Exception(message),
            trace_id=trace_id,
            category=category,
            severity=severity,
            context=context,
        )

    # ------------------------------------------------------------------
    # Subscribe API
    # ------------------------------------------------------------------

    def subscribe(
        self,
        handler: ErrorHandler,
        category: Optional[ErrorCategory] = None,
    ) -> None:
        """
        Subscribe to errors. category=None means all categories.
        """
        with self._lock:
            self._subscribers.setdefault(category, []).append(handler)

    def _dispatch(self, event: ErrorEvent) -> None:
        # Category-specific subscribers
        handlers = list(self._subscribers.get(event.category, []))
        # Global subscribers (category=None)
        handlers += list(self._subscribers.get(None, []))
        for h in handlers:
            try:
                h(event)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # PANIC threshold
    # ------------------------------------------------------------------

    def _check_panic_threshold(self, module: str, event: ErrorEvent) -> None:
        now = time.time()
        with self._lock:
            timestamps = self._critical_timestamps.setdefault(module, [])
            timestamps.append(now)
            # Evict old timestamps outside window
            cutoff = now - PANIC_WINDOW_SEC
            self._critical_timestamps[module] = [t for t in timestamps if t >= cutoff]
            count = len(self._critical_timestamps[module])

        if count >= PANIC_THRESHOLD:
            from system.state_manager import state_manager

            state_manager.force_panic(
                f"error_bus: {module} raised {count} CRITICAL errors "
                f"in {PANIC_WINDOW_SEC:.0f}s"
            )

    # ------------------------------------------------------------------
    # Global exception hook
    # ------------------------------------------------------------------

    def install_global_hook(self) -> None:
        """
        Install as sys.excepthook so uncaught exceptions are captured.
        Call once at process startup.
        """
        original = sys.excepthook

        def hook(exc_type, exc_value, exc_tb):
            self.emit(
                module="__global__",
                error=exc_value,
                category=ErrorCategory.SYSTEM,
                severity=ErrorSeverity.CRITICAL,
            )
            original(exc_type, exc_value, exc_tb)

        sys.excepthook = hook

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def recent(self, n: int = 50) -> List[ErrorEvent]:
        with self._lock:
            return list(self._history[-n:])

    def by_module(self, module: str, limit: int = 20) -> List[ErrorEvent]:
        with self._lock:
            return [e for e in reversed(self._history) if e.module == module][:limit]

    def by_severity(self, severity: ErrorSeverity, limit: int = 50) -> List[ErrorEvent]:
        with self._lock:
            return [e for e in reversed(self._history) if e.severity == severity][
                :limit
            ]

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self._history)
            by_sev: Dict[str, int] = {}
            by_cat: Dict[str, int] = {}
            for e in self._history:
                by_sev[e.severity.name] = by_sev.get(e.severity.name, 0) + 1
                by_cat[e.category.name] = by_cat.get(e.category.name, 0) + 1
        return {
            "total_errors": total,
            "by_severity": by_sev,
            "by_category": by_cat,
            "panic_threshold": PANIC_THRESHOLD,
            "panic_window_sec": PANIC_WINDOW_SEC,
        }


# Singleton
error_bus = ErrorBus()
