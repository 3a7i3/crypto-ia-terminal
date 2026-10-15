"""API de présentation LAB : GET-only, loopback, lecture seule des artefacts LAB."""

from __future__ import annotations

import hmac
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from lab01 import PROVENANCE

ID_RE = re.compile(r"^LAB01-[a-z_]+-[0-9a-f]{12}$")
UI_PATH = Path(__file__).resolve().parent / "ui" / "index.html"
MAX_BYTES = 8 * 1024 * 1024
LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def make_handler(root: Path, token: str | None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "lab01"
        sys_version = ""

        def log_message(self, *a):  # pas de journal d'accès contenant des jetons
            pass

        def _send(
            self, code: int, body: bytes, ctype: str = "application/json"
        ) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'unsafe-inline'; "
                "style-src 'unsafe-inline'; connect-src 'self'",
            )
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj) -> None:
            if isinstance(obj, dict):
                obj = {"provenance": PROVENANCE, **obj}
            self._send(code, json.dumps(obj, sort_keys=True).encode())

        def _err(self, code: int, error: str) -> None:
            self._json(code, {"error": error})

        def _authorized(self) -> bool:
            if token is None:
                return True
            got = self.headers.get("Authorization", "")
            return hmac.compare_digest(got, "Bearer " + token)

        def _read(self, path: Path):
            try:
                if path.stat().st_size > MAX_BYTES:
                    return None, "LAB_ARTIFACT_TOO_LARGE"
                return path.read_text(encoding="utf-8"), None
            except FileNotFoundError:
                return None, "LAB_ARTIFACT_MISSING"
            except OSError:
                return None, "LAB_ARTIFACT_UNREADABLE"

        def do_GET(self):
            path = self.path.split("?", 1)[0].rstrip("/") or "/"
            if path in ("/", "/ui"):
                try:
                    return self._send(200, UI_PATH.read_bytes(), "text/html")
                except OSError:
                    return self._err(503, "LAB_UI_MISSING")
            if not path.startswith("/lab/"):
                return self._err(404, "NOT_FOUND")
            if not self._authorized():
                return self._err(401, "UNAUTHORIZED")
            if path == "/lab/health":
                return self._json(200, {"status": "ok", "read_only": True})
            if path == "/lab/experiments":
                text, err = self._read(root / "index.json")
                if err:
                    return self._err(503, err)
                return self._json(200, json.loads(text))
            m = re.match(r"^/lab/experiments/([^/]+)(/events)?$", path)
            if not m or not ID_RE.match(m.group(1)):
                return self._err(404, "NOT_FOUND")
            d = root / m.group(1)
            if m.group(2):
                text, err = self._read(d / "events.jsonl")
                if err:
                    return self._err(503 if err != "LAB_ARTIFACT_MISSING" else 404, err)
                events = [json.loads(x) for x in text.splitlines() if x]
                return self._json(200, {"experiment_id": m.group(1), "events": events})
            text, err = self._read(d / "result.json")
            if err:
                return self._err(503 if err != "LAB_ARTIFACT_MISSING" else 404, err)
            return self._json(200, json.loads(text))

        def _refuse(self):
            self.send_response(405)
            self.send_header("Allow", "GET")
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _refuse

    return Handler


def build_server(root, port: int, token: str | None = None, host: str = "127.0.0.1"):
    if host not in LOOPBACK:
        raise ValueError("LAB_API_LOOPBACK_ONLY")
    return ThreadingHTTPServer((host, port), make_handler(Path(root), token))


def serve(root, port: int, token_file: str | None) -> None:
    token = None
    if token_file:
        token = Path(token_file).read_text().strip()
        if len(token) < 24:
            raise SystemExit("LAB_TOKEN_TOO_SHORT")
    srv = build_server(root, port, token)
    print(
        f"LAB-01 API (SYNTHETIC, GET-only) sur http://127.0.0.1:{port}/ — "
        f"auth={'bearer' if token else 'AUCUNE'}"
    )
    srv.serve_forever()
