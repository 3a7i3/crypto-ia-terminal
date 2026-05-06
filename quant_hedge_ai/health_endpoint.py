"""
health_endpoint.py — Endpoint HTTP /health (Phase 8).

Serveur HTTP léger (stdlib pure, pas de dépendances externes) exposant :
  GET /health        → JSON {status, uptime, components, timestamp}
  GET /health/detail → JSON complet avec métriques détaillées
  GET /metrics       → JSON plat pour monitoring externe

Démarrage dans un thread daemon :
    from quant_hedge_ai.health_endpoint import HealthServer
    server = HealthServer(port=8765)
    server.start()          # non-bloquant
    server.update("paper_engine", {"balance": 9800.0, "ok": True})
    server.stop()
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_PORT = int(os.getenv("HEALTH_PORT", "8765"))
_STARTED_AT   = time.time()


class _HealthHandler(BaseHTTPRequestHandler):
    """Handler HTTP minimaliste — lit le state depuis le server parent."""

    server: "HealthServer"   # type: ignore[assignment]

    def log_message(self, fmt: str, *args: Any) -> None:
        logger.debug("[HealthEndpoint] " + fmt, *args)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.rstrip("/")

        if path == "/health":
            payload = self.server.health_summary()
        elif path == "/health/detail":
            payload = self.server.health_detail()
        elif path == "/metrics":
            payload = self.server.metrics()
        else:
            self._respond(404, {"error": "Not found", "path": self.path})
            return

        self._respond(200, payload)

    def _respond(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class HealthServer:
    """
    Serveur HTTP /health thread-safe.

    Les composants s'enregistrent via update() ; le serveur agrège leur statut.
    Un composant est "dégradé" si son dict contient ok=False ou status != "ok".
    """

    def __init__(self, port: int = _DEFAULT_PORT) -> None:
        self.port = port
        self._components: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._started_at = time.time()

    # ── Cycle de vie ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """Démarre le serveur dans un thread daemon (non-bloquant)."""
        if self._server is not None:
            return

        server = HTTPServer(("0.0.0.0", self.port), _HealthHandler)
        server.health_server = self   # référence pour le handler
        # Monkey-patch pour que _HealthHandler.server pointe sur HealthServer
        # Le HTTPServer wrappe lui-même, on passe via un attribut custom
        server.__class__ = type(
            "PatchedHTTPServer",
            (HTTPServer,),
            {
                "health_summary": lambda s: self.health_summary(),
                "health_detail":  lambda s: self.health_detail(),
                "metrics":        lambda s: self.metrics(),
            },
        )

        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever, daemon=True, name="health-endpoint"
        )
        self._thread.start()
        logger.info("[HealthServer] Démarré sur http://0.0.0.0:%d/health", self.port)

    def stop(self) -> None:
        """Arrête le serveur proprement."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None
        logger.info("[HealthServer] Arrêté")

    @property
    def is_running(self) -> bool:
        return self._server is not None

    # ── API de mise à jour ────────────────────────────────────────────────────

    def update(self, component: str, state: dict) -> None:
        """Met à jour l'état d'un composant (thread-safe)."""
        with self._lock:
            self._components[component] = {**state, "_updated_at": time.time()}

    def remove(self, component: str) -> None:
        with self._lock:
            self._components.pop(component, None)

    # ── Réponses JSON ─────────────────────────────────────────────────────────

    def health_summary(self) -> dict:
        status = self._global_status()
        return {
            "status": status,
            "uptime_seconds": round(time.time() - self._started_at, 1),
            "components_ok": sum(1 for c in self._component_statuses().values() if c == "ok"),
            "components_degraded": sum(1 for c in self._component_statuses().values() if c != "ok"),
            "timestamp": time.time(),
        }

    def health_detail(self) -> dict:
        summary = self.health_summary()
        with self._lock:
            components_copy = {k: dict(v) for k, v in self._components.items()}
        return {
            **summary,
            "components": components_copy,
            "component_statuses": self._component_statuses(),
        }

    def metrics(self) -> dict:
        """Format plat pour monitoring externe (Prometheus-like)."""
        result: dict = {
            "uptime_seconds": round(time.time() - self._started_at, 1),
            "global_status": self._global_status(),
        }
        with self._lock:
            for name, state in self._components.items():
                safe = name.replace("/", "_").replace("-", "_")
                for k, v in state.items():
                    if k.startswith("_"):
                        continue
                    if isinstance(v, (int, float, bool)):
                        result[f"{safe}_{k}"] = v
        return result

    # ── Internals ─────────────────────────────────────────────────────────────

    def _component_statuses(self) -> dict[str, str]:
        statuses = {}
        with self._lock:
            for name, state in self._components.items():
                if state.get("ok") is False:
                    statuses[name] = "degraded"
                elif state.get("status", "ok") != "ok":
                    statuses[name] = state["status"]
                else:
                    statuses[name] = "ok"
        return statuses

    def _global_status(self) -> str:
        statuses = self._component_statuses()
        if not statuses:
            return "ok"
        if any(s == "critical" for s in statuses.values()):
            return "critical"
        if any(s == "degraded" for s in statuses.values()):
            return "degraded"
        return "ok"
