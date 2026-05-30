"""
health_endpoint.py — Endpoint HTTP /health exposant l'état de la RuntimeStateMachine.

Répond à : curl -s http://localhost:<port>/health | jq '.status'
Résultat : "normal" | "degraded" | "critical" | "safe_mode" | "recovery"

Usage :
    sm = RuntimeStateMachine()
    server = HealthEndpoint(sm, port=8765)
    server.start()        # démarre en background thread
    ...
    server.stop()
"""

from __future__ import annotations

import http.server
import json
import socket
import threading
from typing import TYPE_CHECKING

from observability.json_logger import get_logger

if TYPE_CHECKING:
    from quant_hedge_ai.runtime.runtime_state_machine import RuntimeStateMachine

_log = get_logger("quant_hedge_ai.runtime.health_endpoint")


class _HealthHandler(http.server.BaseHTTPRequestHandler):

    state_machine: "RuntimeStateMachine"  # injecté avant bind

    def do_GET(self) -> None:
        if self.path not in ("/health", "/health/"):
            self.send_error(404)
            return
        snap = self.__class__.state_machine.snapshot()
        body = json.dumps(
            {
                "status": snap["state"].lower(),
                "state": snap["state"],
                "can_trade": snap["can_trade"],
                "can_fetch_data": snap["can_fetch_data"],
                "size_factor": snap["size_factor"],
                "error_count_window": snap["error_count_window"],
                "fault_counts": snap["fault_counts"],
                "last_error_ago_s": snap["last_error_ago_s"],
            },
            ensure_ascii=False,
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_) -> None:  # silence access logs
        pass


class HealthEndpoint:
    """
    Serveur HTTP léger exposant /health.

    Thread-safe. Démarre dans un daemon thread : il s'arrête automatiquement
    à la fin du processus. Appeler stop() pour un arrêt propre explicite.
    """

    def __init__(
        self,
        state_machine: "RuntimeStateMachine",
        port: int = 8765,
        host: str = "127.0.0.1",
    ) -> None:
        self._sm = state_machine
        self._port = port
        self._host = host
        self._server: http.server.HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> int:
        """
        Démarre le serveur dans un thread daemon.
        Retourne le port effectif (utile si port=0 → auto-assigné).
        """
        # Crée un handler lié à notre state machine
        handler = type(
            "_BoundHealthHandler",
            (_HealthHandler,),
            {"state_machine": self._sm},
        )
        self._server = http.server.HTTPServer((self._host, self._port), handler)
        actual_port = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name=f"health-endpoint-{actual_port}",
        )
        self._thread.start()
        _log.info("[HealthEndpoint] démarré sur %s:%d", self._host, actual_port)
        return actual_port

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    @property
    def port(self) -> int:
        if self._server is None:
            return self._port
        return self._server.server_address[1]

    @staticmethod
    def find_free_port() -> int:
        """Retourne un port libre sur localhost (utile pour les tests)."""
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]
