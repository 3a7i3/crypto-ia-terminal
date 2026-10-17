"""Serveur local de Governance Tower : loopback uniquement, une page, un panel.

Frontière distincte de l'Operator App : processus, port, code et absence de
session propres. Aucune route ne modifie quoi que ce soit hors du processus ;
``POST /api/sentinel/ask`` ne fait que poser une question à Sentinel.

Protections du prototype (prérequis, pas une authentification) : bind loopback
vérifié, en-tête ``Host`` contrôlé (anti DNS-rebinding), en-tête ``X-GT-Request``
obligatoire (anti-CSRF), corps borné, débit limité, CSP stricte. Une exposition
réseau exigerait une authentification dédiée et une gate distincte.
"""

from __future__ import annotations

import ipaddress
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from governance_tower import AGENT_ID, CAPABILITY, OPERATIONAL_AUTHORITY
from governance_tower.contracts import to_jsonable
from governance_tower.sentinel.agent import Sentinel
from governance_tower.sentinel.llm_adapter import GT01_LLM_LIVE
from governance_tower.sentinel.policy import SHORTCUT_LABELS

UI_DIR = Path(__file__).resolve().parent / "ui"
STATIC = {
    "/": ("index.html", "text/html"),
    "/index.html": ("index.html", "text/html"),
    "/app.js": ("app.js", "text/javascript"),
    "/styles.css": ("styles.css", "text/css"),
    # Exemple SYNTHETIC versionné (aperçu ``#apercu``), conforme au contrat AgentRun ; jamais une réponse.
    "/sample_run.json": ("sample_run.json", "application/json"),
}
MAX_BODY = 8_192
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


class NotLoopback(ValueError):
    pass


def require_loopback(host: str) -> str:
    try:
        if ipaddress.ip_address(host).is_loopback:
            return host
    except ValueError:
        pass
    raise NotLoopback(f"bind refusé hors loopback: {host[:60]}")


class RateLimiter:
    def __init__(self, per_minute: int = 30) -> None:
        self.per_minute = per_minute
        self._hits: list[float] = []
        self._lock = threading.Lock()

    def allow(self) -> bool:
        now = time.monotonic()
        with self._lock:
            self._hits = [t for t in self._hits if now - t < 60]
            if len(self._hits) >= self.per_minute:
                return False
            self._hits.append(now)
            return True


def make_handler(sentinel: Sentinel, port: int, scenario: str | None, limiter: RateLimiter):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}

    class Handler(BaseHTTPRequestHandler):
        server_version = "governance-tower"
        sys_version = ""

        def log_message(self, *args: Any) -> None:  # aucune question journalisée en clair
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Content-Security-Policy", CSP)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: Any) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False, sort_keys=True).encode(), "application/json")

        def _host_ok(self) -> bool:
            return self.headers.get("Host", "") in allowed_hosts

        def do_GET(self) -> None:  # noqa: N802
            if not self._host_ok():
                return self._json(403, {"error": "HOST_REFUSED"})
            path = self.path.split("?", 1)[0]
            if path == "/api/status":
                return self._json(200, status_payload(sentinel, scenario))
            if path in STATIC:
                name, ctype = STATIC[path]
                return self._send(200, (UI_DIR / name).read_bytes(), ctype)
            return self._json(404, {"error": "NOT_FOUND"})

        def do_POST(self) -> None:  # noqa: N802
            if not self._host_ok():
                return self._json(403, {"error": "HOST_REFUSED"})
            if self.path != "/api/sentinel/ask":
                return self._json(404, {"error": "NOT_FOUND"})
            if self.headers.get("X-GT-Request") != "1":
                return self._json(403, {"error": "CSRF_HEADER_REQUIRED"})
            origin = self.headers.get("Origin")
            if origin is not None and origin.removeprefix("http://") not in allowed_hosts:
                return self._json(403, {"error": "ORIGIN_REFUSED"})
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self._json(415, {"error": "JSON_REQUIRED"})
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if length < 0:
                return self._json(411, {"error": "LENGTH_REQUIRED"})
            if length > MAX_BODY:
                return self._json(413, {"error": "BODY_TOO_LARGE"})
            if not limiter.allow():
                return self._json(429, {"error": "RATE_LIMITED"})
            try:
                body = json.loads(self.rfile.read(length) or b"null")
            except (ValueError, UnicodeDecodeError):
                return self._json(400, {"error": "INVALID_JSON"})
            if (
                not isinstance(body, dict)
                or not set(body) <= {"question", "shortcut"}
                or not isinstance(body.get("question", ""), str)
                or not isinstance(body.get("shortcut"), (str, type(None)))
                or len(body.get("question", "")) > 2_000
            ):
                return self._json(400, {"error": "INVALID_REQUEST"})
            try:
                run = sentinel.ask(body.get("question", ""), body.get("shortcut"))
            except Exception:  # jamais de trace interne vers le client
                return self._json(500, {"error": "SENTINEL_ERROR"})
            return self._json(200, run.to_dict())

        def _method_not_allowed(self) -> None:
            self._json(405, {"error": "METHOD_NOT_ALLOWED"})

        do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = _method_not_allowed  # noqa: N815

    return Handler


def status_payload(sentinel: Sentinel, scenario: str | None) -> dict[str, Any]:
    return {
        "app": "GOVERNANCE TOWER",
        "agent": AGENT_ID,
        "capability": CAPABILITY,
        "operational_authority": OPERATIONAL_AUTHORITY,
        "mode": sentinel.mode,
        "scenario": scenario,
        "sources": [to_jsonable(s) for s in sentinel.source_status()],
        "audit": sentinel.audit_state,
        "shortcuts": [{"id": i, "label": label} for i, label in SHORTCUT_LABELS],
        # GOV-TOWER-01 : informations d'état, jamais des permissions.
        "reasoner": sentinel.reasoner_name,
        "llm_live": GT01_LLM_LIVE,
        "github_budget": sentinel.github_budget(),
    }


def make_server(sentinel: Sentinel, host: str = "127.0.0.1", port: int = 8765, scenario: str | None = None) -> ThreadingHTTPServer:
    require_loopback(host)
    server = ThreadingHTTPServer((host, port), None)  # type: ignore[arg-type]
    actual_port = server.server_address[1]
    server.RequestHandlerClass = make_handler(sentinel, actual_port, scenario, RateLimiter())
    return server
