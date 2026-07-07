from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List, Optional

from observability.json_logger import get_logger
from observability.system_snapshot import SystemSnapshot

_log = get_logger("observability.system_snapshot_event_bus")

Listener = Callable[[SystemSnapshot], None]


class SystemSnapshotEventBus:
    def __init__(self, max_workers: int = 3) -> None:
        self._listeners: List[Listener] = []
        self._lock = threading.Lock()
        self._executor: Optional[ThreadPoolExecutor] = None
        self._max_workers = max_workers
        self._active = False

    def start(self) -> None:
        with self._lock:
            if self._active:
                return
            self._executor = ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix="snapshot_bus",
            )
            self._active = True

    def stop(self) -> None:
        with self._lock:
            if self._executor is not None and self._active:
                self._executor.shutdown(wait=True)
                self._active = False

    def subscribe(self, listener: Listener) -> None:
        with self._lock:
            self._listeners.append(listener)

    def publish(self, snapshot: SystemSnapshot) -> None:
        if not self._listeners:
            return
        if not self._active:
            self.start()
        with self._lock:
            listeners = list(self._listeners)
            executor = self._executor
        if executor is None:
            return
        for listener in listeners:
            try:
                executor.submit(self._safe_call, listener, snapshot)
            except RuntimeError:
                break

    def _safe_call(self, listener: Listener, snapshot: SystemSnapshot) -> None:
        try:
            listener(snapshot)
        except Exception as exc:
            _log.warning("[SnapshotBus] listener error: %s", exc)


_bus: Optional[SystemSnapshotEventBus] = None
_bus_lock = threading.Lock()


def get_snapshot_bus(max_workers: int = 3) -> SystemSnapshotEventBus:
    global _bus
    with _bus_lock:
        if _bus is None:
            _bus = SystemSnapshotEventBus(max_workers=max_workers)
            _bus.start()
        return _bus
