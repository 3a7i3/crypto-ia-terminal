"""Loopback GET-only viewer of verified J01 feed pages.

Limits are fixed in code: request target <=2 KiB, no request body, query
fields from a closed set, page <=100 events, response <=4 MiB, two requests
in flight (others get BUSY), 10 s timeout per socket operation (no deadline
for a whole request and no cap on open connections). Every request re-verifies
the whole stored journal through sentinel_activity; nothing is cached.

Loopback is not authentication: any process of any local account can connect.
The Host/Origin checks only block browser-mediated cross-site and DNS
rebinding reads. Do not run it on a shared multi-user host with real data.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

from sentinel_activity.feed import feed_page

LOOPBACK = "127.0.0.1"
MAX_ROOTS = 8
MAX_TARGET = 2_048
MAX_RESPONSE = 4 * 1024 * 1024
MAX_IN_FLIGHT = 2
SOCKET_TIMEOUT_S = 10
DEFAULT_LIMIT = 25
QUERY_FIELDS = frozenset({"limit", "cursor", "quest_id", "actor_id", "correlation_id"})
FILTER_FIELDS = ("quest_id", "actor_id", "correlation_id")
REQUEST_ERRORS = frozenset({"HOST_DENIED", "ORIGIN_DENIED", "QUERY_INVALID", "NOT_FOUND",
                            "METHOD_DENIED", "BODY_DENIED", "BUSY", "RESPONSE_TOO_LARGE",
                            "TARGET_TOO_LONG"})
_ROUTE = re.compile(r"/(?:(api)/)?ledger/([0-7])")
_LIMIT = re.compile(r"[1-9][0-9]?|100")
_HTTP_FOR_STATUS = {"PREFIX_VERIFIED": 200, "NO_DATA": 200, "CURSOR_INVALID": 400,
                    "BUSY": 503, "UNAVAILABLE": 503}
_HTTP_FOR_REQUEST = {"HOST_DENIED": 403, "ORIGIN_DENIED": 403, "QUERY_INVALID": 400, "NOT_FOUND": 404,
                     "METHOD_DENIED": 405, "BODY_DENIED": 400, "BUSY": 503,
                     "RESPONSE_TOO_LARGE": 503, "TARGET_TOO_LONG": 414}

CSS = (
    "body{font:14px/1.45 system-ui,sans-serif;margin:0 auto;max-width:1100px;padding:16px;"
    "color:#1d1d1f;background:#fafafa}"
    "header,section,article{background:#fff;border:1px solid #ddd;border-radius:6px;padding:12px;"
    "margin-bottom:12px}"
    ".badge{display:inline-block;padding:1px 6px;border-radius:4px;background:#ececec;font-size:12px}"
    ".SIMULATED{background:#fde9b8}.warn{color:#8a1c1c;font-weight:600}"
    "pre{white-space:pre-wrap;word-break:break-word;background:#f3f3f3;padding:6px;border-radius:4px}"
    "code{word-break:break-all}dl{display:grid;grid-template-columns:max-content 1fr;gap:2px 12px}"
    "dt{color:#555}form input{margin-right:6px}"
)
_CSS_HASH = base64.b64encode(hashlib.sha256(CSS.encode()).digest()).decode()
SECURITY_HEADERS = {
    "Content-Security-Policy": (f"default-src 'none'; style-src 'sha256-{_CSS_HASH}'; "
                                "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-Frame-Options": "DENY",
}


class RequestRefused(Exception):
    def __init__(self, code: str) -> None:
        assert code in REQUEST_ERRORS
        self.code = code
        super().__init__(code)


def admit_roots(paths) -> tuple[Path, ...]:
    """Syntactic admission only: nothing is opened, created or resolved here.

    Each request opens the root through ActivityStore, which refuses symlinks,
    foreign owners, loose permissions and missing journals (UNAVAILABLE).
    """
    roots = tuple(Path(path) for path in paths)
    if not 1 <= len(roots) <= MAX_ROOTS or len(set(roots)) != len(roots):
        raise ValueError("between 1 and 8 distinct LAB roots are required")
    for root in roots:
        if not root.is_absolute() or ".." in root.parts or not root.name.startswith("j01-lab-"):
            raise ValueError("a LAB root must be an absolute j01-lab-* directory path")
    return roots


def _e(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _query(params: dict) -> str:
    return urlencode({key: value for key, value in params.items() if value is not None})


def render_html(index: int, roots: tuple[Path, ...], feed: dict, params: dict) -> str:
    rows = []
    for item in feed["items"] or []:
        actor = item["actor"]
        refs = "".join(f"<li><code>{_e(ref)}</code></li>" for ref in item["evidence_refs"]) or "<li>—</li>"
        rows.append(
            "<article>"
            f"<div><span class='badge {_e(item['provenance'])}'>{_e(item['provenance'])}</span> "
            f"<strong>#{_e(item['sequence'])} {_e(item['event_type'])}</strong></div>"
            "<dl>"
            f"<dt>Enregistré</dt><dd>{_e(item['recorded_at_utc'])}</dd>"
            f"<dt>Survenu</dt><dd>{_e(item['occurred_at_utc'] or item['occurred_at_status'])}</dd>"
            f"<dt>Acteur</dt><dd><code>{_e(actor['id'])}</code> ({_e(actor['kind'])})</dd>"
            f"<dt>Quête</dt><dd><code>{_e(item['quest_id'] or '—')}</code></dd>"
            f"<dt>Corrélation</dt><dd><code>{_e(item['correlation_id'] or '—')}</code></dd>"
            f"<dt>Résumé</dt><dd>{_e(item['summary'])}</dd>"
            f"<dt>Raison déclarée</dt><dd>{_e(item['reason_declared'] or '—')}</dd>"
            f"<dt>Références</dt><dd><ul>{refs}</ul><small>texte inerte, jamais suivi</small></dd>"
            f"<dt>Empreinte</dt><dd><code>{_e(item['event_hash'])}</code></dd>"
            f"<dt>Masquage d'affichage</dt><dd>{_e(item['display']['redactions'])} remplacement(s)</dd>"
            "</dl>"
            f"<pre>{_e(json.dumps(item['payload'], ensure_ascii=False, sort_keys=True, indent=1))}</pre>"
            "</article>")
    ledgers = " · ".join(
        f"<a href='/ledger/{i}'>journal {i}</a>" if i != index else f"<strong>journal {i}</strong>"
        for i in range(len(roots)))
    status = feed["status"]
    verified = feed["items"] is not None
    next_link = ""
    if feed.get("next_cursor"):
        next_link = (f"<p><a href='/ledger/{index}?"
                     f"{_e(_query({**params, 'cursor': feed['next_cursor']}))}'>Page suivante</a></p>")
    summary = "".join(
        f"<dt>{_e(key)}</dt><dd><code>{_e(feed.get(key))}</code></dd>"
        for key in ("status", "completeness", "authenticity", "anchor", "ledger_id", "event_count",
                    "snapshot_watermark", "snapshot_head_hash", "filter_match_count", "page_limit"))
    warning = "" if verified else (
        f"<p class='warn'>Journal non vérifié : {_e(status)}. Ce n'est pas un fil vide.</p>")
    inputs = "".join(
        f"<label>{_e(name)} <input name='{_e(name)}' value='{_e(params.get(name) or '')}'></label>"
        for name in FILTER_FIELDS)
    return (
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Journal Sentinel J02</title><style>{CSS}</style></head><body>"
        "<header><strong>Fil d'activité J01 — lecture locale</strong><br>"
        "<span class='badge SIMULATED'>SIMULATED_ONLY</span> laboratoire local, aucune autorité, "
        "aucun agent réel démontré, complétude UNKNOWN, authenticité NOT_PROVEN.<br>"
        f"{ledgers}</header>"
        f"<section>{warning}<dl>{summary}</dl>"
        f"<form method='get' action='/ledger/{index}'>{inputs}"
        f"<label>limit <input name='limit' value='{_e(params.get('limit') or DEFAULT_LIMIT)}'></label>"
        "<button type='submit'>Filtrer</button></form></section>"
        f"{''.join(rows)}{next_link}</body></html>")


class ViewerHandler(BaseHTTPRequestHandler):
    server_version = "sentinel-viewer"
    sys_version = ""
    protocol_version = "HTTP/1.0"
    timeout = SOCKET_TIMEOUT_S

    def log_message(self, format, *args):  # noqa: A002 - BaseHTTPRequestHandler API
        # Never log request targets (cursors, filters) or headers.
        return

    def _send(self, code: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(code)
        for key, value in {**SECURITY_HEADERS, **(extra or {})}.items():
            self.send_header(key, value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _refusal(self, code: str) -> None:
        extra = {"Allow": "GET"} if code == "METHOD_DENIED" else None
        body = json.dumps({"status": code, "items": None}, sort_keys=True).encode()
        self._send(_HTTP_FOR_REQUEST[code], body, "application/json; charset=utf-8", extra)

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        """Errors raised by http.server itself (malformed request line, oversized headers, bad
        version) use the same JSON body and security headers as every other response."""
        self.close_connection = True
        self.request_version = self.protocol_version  # http.server falls back to headerless HTTP/0.9
        body = json.dumps({"status": "REQUEST_MALFORMED", "items": None}, sort_keys=True).encode()
        try:
            self._send(code, body, "application/json; charset=utf-8")
        except OSError:
            pass

    def _refuse_method(self) -> None:
        self._refusal("METHOD_DENIED")

    do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = do_TRACE = do_CONNECT = _refuse_method

    def _check_request(self) -> None:
        if len(self.path) > MAX_TARGET:
            raise RequestRefused("TARGET_TOO_LONG")
        port = self.server.server_address[1]
        allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if (self.headers.get("Host") or "").lower() not in allowed_hosts:
            raise RequestRefused("HOST_DENIED")
        origin = self.headers.get("Origin")
        if origin is not None and origin.lower() not in {"http://" + host for host in allowed_hosts}:
            raise RequestRefused("ORIGIN_DENIED")
        if (self.headers.get("Sec-Fetch-Site") or "same-origin").lower() not in {"same-origin", "none"}:
            raise RequestRefused("ORIGIN_DENIED")
        if self.headers.get("Transfer-Encoding") is not None or self.headers.get("Content-Length", "0") != "0":
            raise RequestRefused("BODY_DENIED")

    def _params(self, query: str) -> dict:
        try:
            pairs = parse_qsl(query, keep_blank_values=False, strict_parsing=bool(query), max_num_fields=8)
        except ValueError as exc:
            raise RequestRefused("QUERY_INVALID") from exc
        names = [name for name, _ in pairs]
        if len(names) != len(set(names)) or not set(names) <= QUERY_FIELDS:
            raise RequestRefused("QUERY_INVALID")
        params = dict(pairs)
        if "limit" in params and _LIMIT.fullmatch(params["limit"]) is None:
            raise RequestRefused("QUERY_INVALID")
        return params

    def do_GET(self) -> None:
        try:
            self._check_request()
            target = urlsplit(self.path)
            if target.fragment:
                raise RequestRefused("QUERY_INVALID")
            roots = self.server.roots
            if target.path == "/":
                if target.query:
                    raise RequestRefused("QUERY_INVALID")
                self._send(303, b"", "text/plain; charset=utf-8", {"Location": "/ledger/0"})
                return
            match = _ROUTE.fullmatch(target.path)
            if match is None or int(match.group(2)) >= len(roots):
                raise RequestRefused("NOT_FOUND")
            params = self._params(target.query)
            if not self.server.in_flight.acquire(blocking=False):
                raise RequestRefused("BUSY")
            try:
                index = int(match.group(2))
                feed = feed_page(roots[index], limit=int(params.get("limit", DEFAULT_LIMIT)),
                                 cursor_token=params.get("cursor"),
                                 **{name: params.get(name) for name in FILTER_FIELDS})
            finally:
                self.server.in_flight.release()
            code = _HTTP_FOR_STATUS.get(feed["status"], 500)
            if match.group(1):
                body = json.dumps(feed, ensure_ascii=True, sort_keys=True).encode()
                content_type = "application/json; charset=utf-8"
            else:
                body = render_html(index, roots, feed, params).encode("utf-8")
                content_type = "text/html; charset=utf-8"
            if len(body) > MAX_RESPONSE:
                raise RequestRefused("RESPONSE_TOO_LARGE")
            self._send(code, body, content_type)
        except RequestRefused as refused:
            self._refusal(refused.code)


class ViewerServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    request_queue_size = 8

    def __init__(self, roots: tuple[Path, ...], port: int) -> None:
        self.roots = admit_roots(roots)
        self.in_flight = threading.BoundedSemaphore(MAX_IN_FLIGHT)
        super().__init__((LOOPBACK, port), ViewerHandler)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="GET-only loopback viewer of J01 LAB journals")
    parser.add_argument("--root", action="append", required=True,
                        help="absolute j01-lab-* directory; repeatable, fixed at start-up")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("port must be within 1024..65535")
    try:
        server = ViewerServer(admit_roots(args.root), args.port)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"sentinel_viewer: http://{LOOPBACK}:{server.server_address[1]}/ (GET only, SIMULATED_ONLY)",
          file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
