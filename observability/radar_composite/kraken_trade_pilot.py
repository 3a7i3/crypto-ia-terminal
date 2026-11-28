"""MEO-01 bounded public capture: Kraken Spot WS v2 ``trade`` channel, BTC/USDT only.

Public data only: no key, token, account, private channel, order, service,
systemd unit or app wiring. One WebSocket connection, no reconnection, a fixed
REST allow-list (identity, clocks and at most three ``Trades`` pages for the
cross-check). Every frame is kept raw with its UTC and monotonic receipt times
in nanoseconds and its SHA-256; results come only from the offline replay
(``observability.meo_trades_replay``).

Reused without modification: ``bbo_wire`` (RFC 6455 codec), ``bbo_pilot``
(WebSocket connection, append-only evidence, watchdog, bounded operations) and
the Kraken identity/clock checks of the L3 pilot.

Usage (from a checkout of the exact commit):
    python3 -m observability.radar_composite.kraken_trade_pilot dry-run --out DIR
    python3 -m observability.radar_composite.kraken_trade_pilot code-sha256
    python3 -m observability.radar_composite.kraken_trade_pilot run --out DIR \\
        --code-sha256 HEX --confirm-public-collection MEO01-TRADES
``run`` opens public network connections and is only for a separately
authorised capture GO (MEO-01 / L2).

Exit codes: 0 completed, 2 stopped by a stop condition, 3 preflight refused,
4 usage / evidence error.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import heapq
import json
import os
import platform
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import bbo_pilot as bp
from . import bbo_wire as wire
from . import pilot as l3
from .decoders import strict_json
from .instruments import instrument_dict, spot_instrument

PILOT = "CAT-MEO-01/KRAKEN-TRADES"
PILOT_VERSION = 1
WS_URL = bp.KRAKEN_WS
WS_SYMBOL = "BTC/USDT"
REST_PAIR, REST_KEY, BASE_ASSET, BASE_ALT = "XBTUSDT", "XBTUSDT", "XXBT", "XBT"
SUBSCRIBE = {"method": "subscribe", "params": {"channel": "trade", "symbol": [WS_SYMBOL], "snapshot": True},
             "req_id": 1}
CAPTURE_MS = 15 * 60_000
MAX_SECONDS = 1_080
CLOCK_TOLERANCE_MS = l3.KRAKEN_CLOCK_TOLERANCE_MS  # 2 000 ms, Kraken Time has a 1 s resolution
CROSS_CHECK_LOOKBACK_S = 120
REST_PAGE_ROWS = 1000
REST_BUDGET = {"time": 2, "assetPairs": 1, "assets": 1, "trades": 3}
CAPS = {"max_frames": 50_000, "max_frame_bytes": wire.MAX_MESSAGE_BYTES,
        "max_storage_bytes": 20 * 1024 * 1024}
STOP_HTTP = (403, 418, 429, 451)
CONFIRM_TOKEN = "MEO01-TRADES"
DRY_RUN_START_MS = 1_795_128_000_000
STATIC_URLS = {
    "time": f"{l3.KRAKEN}/0/public/Time",
    "assetPairs": f"{l3.KRAKEN}/0/public/AssetPairs?pair={REST_PAIR}",
    "assets": f"{l3.KRAKEN}/0/public/Assets?asset={BASE_ASSET}",
}
_TRADES_URL = re.compile(r"https://api\.kraken\.com/0/public/Trades\?pair=XBTUSDT&since=(0|[1-9][0-9]{0,19})")
HYPOTHESES = {
    "H1": "side is the side of the taker order (documented, hashed excerpt)",
    "H2": "trade_id increases by exactly 1 per trade of the book",
    "H3": "meaning of the native timestamp (documented as book order update timestamp)",
    "H4": "price and qty are plain decimal literals without exponent",
    "H5": "order inside a frame and native time follow trade_id",
    "H6": "the subscription and every trade echo the symbol BTC/USDT",
    "H7": "one WS trade row equals one REST trade row (id, price, qty, side)",
}
CODE_FILES = ("kraken_trade_pilot.py", "bbo_pilot.py", "bbo_wire.py", "bbo_book.py", "bbo_schema.py",
              "pilot.py", "decoders.py", "instruments.py", "composite.py", "coverage.py", "schema.py")


def trades_url(since):
    url = f"{l3.KRAKEN}/0/public/Trades?pair={REST_PAIR}&since={since}"
    if not _TRADES_URL.fullmatch(url):
        raise l3.Refused("Trades cursor outside the allow-list")
    return url


def allowed_url(url):
    return url in STATIC_URLS.values() or bool(_TRADES_URL.fullmatch(url))


def code_identity():
    """SHA-256 of every capture source file and one digest over them (checked by ``run``)."""
    root = Path(__file__).resolve().parent
    files = {n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in CODE_FILES}
    vqc = root.parent / "venue_quote_comparison.py"
    if vqc.is_file():
        files["../venue_quote_comparison.py"] = hashlib.sha256(vqc.read_bytes()).hexdigest()
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {"git_head": l3.code_identity()["git_head"], "files_sha256": files, "digest": digest}


# ---------------------------------------------------------------- clocks and evidence (ns receipts)

class NsClock(l3.RealClock):
    def wall_ns(self):
        return time.time_ns()

    def mono_ns(self):
        return time.monotonic_ns()


class FakeNsClock(l3.FakeClock):
    def wall_ns(self):
        return self.now * 1_000_000

    def mono_ns(self):
        return self.now * 1_000_000


class NsEvidence(bp.Evidence):
    """``bbo_pilot.Evidence`` with receipt times read once, in nanoseconds.

    The millisecond fields are derived from the same reading, so the two never
    disagree. Everything else (storage budget, append-only, seal) is inherited.
    """

    def record(self, venue, kind, payload=b"", *, final=False, **extra):
        wall_ns, mono_ns = self.clock.wall_ns(), self.clock.mono_ns()
        wall, mono = wall_ns // 1_000_000, mono_ns // 1_000_000
        digest = hashlib.sha256(payload).hexdigest()
        entry = {"seq": self.seq + 1, "venue": venue, "kind": kind, "recv_wall_ms": wall,
                 "recv_mono_ms": mono, "recv_wall_ns": wall_ns, "recv_mono_ns": mono_ns,
                 "t_ms": self.t_ms(mono), "offset": self.offset, "bytes": len(payload),
                 "sha256": digest, **extra}
        line = (json.dumps(entry, sort_keys=True) + "\n").encode()
        if self.cap is not None:
            limit = self.cap - bp.MANIFEST_MAX_BYTES - (0 if final else bp.STORAGE_RESERVE_BYTES)
            if self.used() + len(payload) + len(line) > limit:
                if final:
                    raise bp.PilotStop("STORAGE_RESERVE_EXHAUSTED", refused_kind=kind)
                raise bp.PilotStop("BUDGET_STORAGE_EXHAUSTED", refused_kind=kind, refused_bytes=len(payload),
                                   refused_sha256=digest, used_bytes=self.used(), cap_bytes=self.cap)
        self.critical += 1
        try:
            self.seq += 1
            self.raw.write(payload)
            self.raw.flush()
            self.offset += len(payload)
            self.log.write(line)
            self.log.flush()
            self.log_bytes += len(line)
        finally:
            self.critical -= 1
        return entry


# ---------------------------------------------------------------- pilot

class TradePilot:
    # Watchdog and bounded-operation helpers reused from the BBO pilot (not copied).
    _arm_watchdog = bp.BboPilot._arm_watchdog
    _disarm_watchdog = bp.BboPilot._disarm_watchdog
    _on_deadline = bp.BboPilot._on_deadline
    _record = bp.BboPilot._record
    _remaining_s = bp.BboPilot._remaining_s
    _check_duration = bp.BboPilot._check_duration
    _bounded = bp.BboPilot._bounded
    _offset = l3.Pilot._offset

    def __init__(self, out, session, clock, *, evidence_kind="OBSERVATION", caps=None,
                 capture_ms=CAPTURE_MS, max_seconds=MAX_SECONDS, watchdog_s=None):
        if evidence_kind not in ("OBSERVATION", "SYNTHETIC"):
            raise l3.Refused("unknown evidence kind")
        self.session, self.clock, self.kind = session, clock, evidence_kind
        self.caps = {**CAPS, **(caps or {})}
        self.capture_ms, self.max_seconds = capture_ms, max_seconds
        self.watchdog_s = max_seconds if watchdog_s is None else watchdog_s
        self.evidence = NsEvidence(out, clock, self.caps["max_storage_bytes"])
        self.rest_used = {k: 0 for k in REST_BUDGET}
        self._deadline_pending = False
        self.failures = self.frames = 0
        self.t0 = self.stop_code = self.stop_detail = None
        self.ack_wall_ms = None
        self.opened_ms = None

    # -- REST (allow-listed GET only)
    def get(self, endpoint, url, *, purpose):
        if endpoint not in REST_BUDGET or not allowed_url(url):
            raise l3.Refused("REST request outside the allow-list")
        if self.rest_used[endpoint] >= REST_BUDGET[endpoint]:
            raise l3.Stop(f"BUDGET_REST_KRAKEN_{endpoint.upper()}")
        self._check_duration()
        if self._remaining_s() < bp.REST_TIMEOUT_S + bp.REST_MARGIN_S:
            raise bp.PilotStop("BUDGET_DURATION_INSUFFICIENT_FOR_REST", endpoint=endpoint)
        self.rest_used[endpoint] += 1
        sent = self.clock.wall_ms()
        status, headers, body, error = self.session.rest(url)
        entry = self._record("kraken", "rest", body, endpoint=endpoint, purpose=purpose, url=url,
                             sent_ms=sent, status=status, error=error,
                             headers={k.lower(): v for k, v in headers.items()
                                      if k.lower() in l3.KEPT_HEADERS})
        entry["received_ms"] = entry["recv_wall_ms"]
        if status in STOP_HTTP:
            raise l3.Stop(f"HTTP_{status}")
        failed = status != 200
        if status == 200:
            try:
                errs = strict_json(body).get("error")
            except (ValueError, AttributeError):
                errs, failed = None, True
            if errs:
                text = " ".join(map(str, errs))
                if any(s in text for s in ("Too many requests", "Rate limit", "Temporary lockout")):
                    raise l3.Stop("KRAKEN_RATE_LIMIT")
                failed = True
        self.failures = self.failures + 1 if failed else 0
        if self.failures >= l3.MAX_CONSECUTIVE_FAILURES:
            raise l3.Stop("THREE_CONSECUTIVE_FAILURES")
        return entry, body, failed

    def preflight(self):
        """Kraken half of the L3 preflight: clock, pair identity, base alias."""
        checks = {}
        e, body, _ = self.get("time", STATIC_URLS["time"], purpose="clock")
        checks["kraken_clock_offset_ms"] = self._offset(e, body, "kraken")
        e, body, failed = self.get("assetPairs", STATIC_URLS["assetPairs"], purpose="identity")
        res = strict_json(body).get("result", {}) if not failed else {}
        pair = res.get(REST_KEY) if isinstance(res, dict) else None
        if not isinstance(res, dict) or set(res) != {REST_KEY} or not isinstance(pair, dict) \
                or pair.get("altname") != REST_PAIR or pair.get("base") != BASE_ASSET \
                or pair.get("status") != "online":
            raise l3.Stop("PREFLIGHT_KRAKEN_IDENTITY")
        e, body, failed = self.get("assets", STATIC_URLS["assets"], purpose="identity")
        assets = strict_json(body).get("result", {}) if not failed else {}
        if not isinstance(assets, dict) or assets.get(BASE_ASSET, {}).get("altname") != BASE_ALT:
            raise l3.Stop("PREFLIGHT_KRAKEN_ASSET_ALIAS")
        checks["kraken_identity"] = f"{REST_KEY} base={BASE_ASSET} altname={BASE_ALT}"
        k = checks["kraken_clock_offset_ms"]
        if k is None or abs(k) > CLOCK_TOLERANCE_MS:
            raise l3.Stop("PREFLIGHT_KRAKEN_CLOCK")
        return checks

    # -- WebSocket
    def _open(self):
        timeout = self._bounded(bp.CONNECT_TIMEOUT_S)
        try:
            self.session.open("kraken", timeout_s=timeout)
        except (wire.WireError, OSError) as exc:
            code = exc.code if isinstance(exc, wire.WireError) else type(exc).__name__.upper()
            self._record("kraken", "ws_error", b"", detail=code, purpose="initial")
            raise bp.PilotStop("WS_REFUSED_KRAKEN", detail=code) from exc
        self._record("kraken", "ws_open", b"", purpose="initial")
        text = json.dumps(SUBSCRIBE, sort_keys=True)
        timeout = self._bounded(bp.SEND_TIMEOUT_S)
        try:
            self.session.send_text("kraken", text, timeout_s=timeout)
        except (wire.WireError, OSError) as exc:
            code = exc.code if isinstance(exc, wire.WireError) else type(exc).__name__.upper()
            self._record("kraken", "send_failed", text.encode(), purpose="subscribe", detail=code)
            raise bp.PilotStop("WS_SEND_FAILED_KRAKEN", detail=code) from exc
        self._record("kraken", "sent", text.encode(), purpose="subscribe")

    def _receive(self, until):
        until = min(until, self.clock.wall_ms() + int(self._bounded(1.0) * 1000))
        for venue, kind, opcode, payload in self.session.poll(until):
            if kind == "ws_message":
                self.frames += 1
                if self.frames > self.caps["max_frames"]:
                    raise bp.PilotStop("BUDGET_FRAMES_EXHAUSTED", refused_bytes=len(payload))
                if len(payload) > self.caps["max_frame_bytes"]:
                    raise bp.PilotStop("FRAME_TOO_LARGE", refused_bytes=len(payload))
            entry = self._record(venue, kind, payload, opcode=opcode)
            if kind in ("ws_close", "ws_error"):
                raise bp.PilotStop("WS_CLOSED_KRAKEN", kind=kind)  # no reconnection (0 allowed)
            if kind == "ws_message" and opcode == wire.OP_TEXT:
                self._provider(entry, payload)

    def _provider(self, entry, payload):
        try:
            doc = json.loads(payload)
        except ValueError:
            return
        if not isinstance(doc, dict):
            return
        if doc.get("method") == "subscribe":
            res = doc.get("result") if isinstance(doc.get("result"), dict) else {}
            if doc.get("success") is not True or res.get("channel") != "trade" or res.get("symbol") != WS_SYMBOL:
                raise l3.Stop("KRAKEN_SUBSCRIBE_REFUSED")
            if self.ack_wall_ms is None:
                self.ack_wall_ms = entry["recv_wall_ms"]
        elif doc.get("error"):
            raise l3.Stop("KRAKEN_PROVIDER_ERROR")

    def _collect(self):
        self.opened_ms = self.clock.wall_ms()
        end = self.opened_ms + self.capture_ms
        self._open()
        while self.clock.wall_ms() < end:
            self._check_duration()
            self._receive(end)
            self.evidence.sync()
        self.session.close("kraken", timeout_s=bp.CLOSE_TIMEOUT_S)
        self._record("kraken", "closed_by_pilot", b"")

    def cross_check(self):
        """At most three ``Trades`` pages from shortly before the subscription."""
        if self.ack_wall_ms is None:
            return {"pages": 0, "reason": "NO_SUBSCRIPTION"}
        since, pages = str(max(0, self.ack_wall_ms // 1000 - CROSS_CHECK_LOOKBACK_S)), 0
        while self.rest_used["trades"] < REST_BUDGET["trades"]:
            if self._remaining_s() < bp.REST_TIMEOUT_S + bp.REST_MARGIN_S + 5:
                return {"pages": pages, "reason": "DURATION"}
            _, body, failed = self.get("trades", trades_url(since), purpose="cross_check")
            pages += 1
            if failed:
                return {"pages": pages, "reason": "FAILED"}
            try:
                result = strict_json(body)["result"]
                rows, last = result[REST_KEY], result["last"]
            except (ValueError, KeyError, TypeError):
                return {"pages": pages, "reason": "UNREADABLE"}
            if not isinstance(last, str) or not last.isdigit() or not isinstance(rows, list) \
                    or len(rows) < REST_PAGE_ROWS or last == since:
                return {"pages": pages, "reason": "END_OR_LAST_PAGE"}
            since = last
        return {"pages": pages, "reason": "BUDGET"}

    def run(self):
        manifest = self._manifest("WAITING")
        self.evidence.manifest(manifest)

        def body():
            manifest["preflight"] = self.preflight()
            ws_stop = None
            try:
                self._collect()
            except l3.Stop as stop:
                if not stop.code.startswith("WS_"):
                    raise
                ws_stop = stop  # the windows before the cut stay usable; cross-check anyway
            manifest["cross_check"] = self.cross_check()
            e, body_, _ = self.get("time", STATIC_URLS["time"], purpose="clock_end")
            manifest["clock_end"] = {"kraken_offset_ms": self._offset(e, body_, "kraken")}
            if ws_stop is not None:
                raise ws_stop
            return 0
        return self._execute(manifest, body)

    def _execute(self, manifest, body):
        manifest["status"] = "RUNNING"
        self.evidence.manifest(manifest)
        exit_code = 0
        self.t0 = self.clock.mono_ms()
        manifest["watchdog"] = self._arm_watchdog()
        try:
            exit_code = body()
            manifest["status"] = "COMPLETED"
        except l3.Stop as stop:
            self._disarm_watchdog()
            self.stop_code = stop.code
            self.stop_detail = getattr(stop, "detail", None) or None
            manifest["status"] = "STOPPED"
            exit_code = 3 if stop.code.startswith("PREFLIGHT") else 2
            with contextlib.suppress(l3.Stop):
                self.evidence.record("pilot", "stop", stop.code.encode(), final=True,
                                     stop_detail=self.stop_detail)
        finally:
            self._disarm_watchdog()
            try:
                self.session.close("kraken", timeout_s=bp.CLOSE_TIMEOUT_S)
            except (OSError, wire.WireError) as exc:  # best effort, never masks the stop
                with contextlib.suppress(l3.Stop):
                    self.evidence.record("kraken", "close_error", type(exc).__name__.encode(), final=True)
            manifest.update(stop_code=self.stop_code, stop_class=bp.stop_class(self.stop_code),
                            stop_detail=self.stop_detail, exit_code=exit_code,
                            ended_wall_ms=self.clock.wall_ms(),
                            elapsed_ms=self.clock.mono_ms() - self.t0 if self.t0 else None,
                            rest_used=dict(self.rest_used), frames=self.frames,
                            sealed=self.evidence.seal())
            self.evidence.manifest(manifest)
        return exit_code

    def _manifest(self, status):
        return {
            "pilot": PILOT, "pilot_version": PILOT_VERSION, "evidence_kind": self.kind, "status": status,
            "market_type": "SPOT", "instrument": instrument_dict(spot_instrument("BTC", "USDT")),
            "ws": {"url": WS_URL, "channel": "trade", "symbol": WS_SYMBOL, "snapshot": True,
                   "subscribe": json.dumps(SUBSCRIBE, sort_keys=True), "reconnects_allowed": 0},
            "rest": {"static": STATIC_URLS, "trades_pattern": _TRADES_URL.pattern,
                     "cross_check_lookback_s": CROSS_CHECK_LOOKBACK_S},
            "capture_ms": self.capture_ms,
            "clock_anchor": {"wall_ms": self.evidence.anchor_wall, "mono_ms": self.evidence.anchor_mono},
            "clock_tolerance_ms": CLOCK_TOLERANCE_MS,
            "time_bases": {"native": "timestamp RFC3339, NATIVE_UNQUALIFIED",
                           "receipt": "recv_wall_ns host UTC + recv_mono_ns monotonic"},
            "budget": {"max_seconds": self.max_seconds, "watchdog_s": self.watchdog_s,
                       "rest": dict(REST_BUDGET), **self.caps,
                       "storage": {"scope": "frames.bin + events.jsonl + manifest.json",
                                   "reserve_bytes": bp.STORAGE_RESERVE_BYTES,
                                   "manifest_max_bytes": bp.MANIFEST_MAX_BYTES}},
            "stop_rules": {"http": list(STOP_HTTP), "consecutive_rest_failures": l3.MAX_CONSECUTIVE_FAILURES,
                           "ws_closed": True, "subscribe_refused": True, "provider_error": True},
            "hypotheses": HYPOTHESES,
            "code": code_identity(), "host": platform.node(), "python": platform.python_version(),
            "created_wall_ms": self.clock.wall_ms(),
        }


# ---------------------------------------------------------------- real transport (capture GO only)

class KrakenTradeSession(bp.RealSession):
    """One Kraken WebSocket (``bbo_pilot.WsConnection``) and allow-listed REST GETs."""

    def __init__(self, clock):
        self.urls = {"kraken": WS_URL}
        self.conns = {}
        self.clock = clock

    def rest(self, url):
        if not allowed_url(url):
            raise l3.Refused("URL outside the allow-list")
        return l3.UrllibTransport([url])(url)


# ---------------------------------------------------------------- synthetic venue (no network)

def _rfc3339(ns):
    sec, frac = divmod(ns, 1_000_000_000)
    return datetime.fromtimestamp(sec, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + f".{frac // 1000:06d}Z"


class FakeKraken:
    """Deterministic Kraken WS v2 ``trade`` channel and REST answers behind the session interface.

    Faults (offsets in ms after the subscription): ``("id_gap", t)`` drops one
    trade, ``("exponent", t)`` writes one quantity as ``1e-05``, ``("silence", t0, t1)``
    delivers nothing (trades still happen, so ids jump), ``("close", t)`` closes
    the connection, ``("refuse",)`` refuses the subscription.
    """

    def __init__(self, clock, *, seed=11, every_ms=700, first_id=90_000_000, faults=(), latency_ms=40):
        self.clock, self.latency, self.every = clock, latency_ms, every_ms
        self.rng = random.Random(seed)
        self.faults = list(faults)
        self.queue, self.order = [], 0
        self.open_ = self.sub = False
        self.sub_at = None
        self.next_tick = self.next_hb = None
        self.next_id = first_id
        self.trades = []  # (id, ns, price, qty, side) as they happened at the venue

    def _fault(self, name, rel):
        for f in self.faults:
            if f[0] != name:
                continue
            if len(f) == 2 and f[1] <= rel < f[1] + self.every:
                return True
            if len(f) == 3 and f[1] <= rel < f[2]:
                return True
        return False

    def _make_trade(self, at_ms, sub_ns=0):
        tid = self.next_id
        self.next_id += 1
        ns = at_ms * 1_000_000 + sub_ns
        price = f"{62000 + self.rng.randint(0, 400)}.{self.rng.randint(0, 9)}"
        qty = f"0.{self.rng.randint(1, 99999):05d}"
        side = self.rng.choice(("buy", "sell"))
        t = (tid, ns, price, qty, side)
        self.trades.append(t)
        return t

    @staticmethod
    def _item(t, qty=None):
        tid, ns, price, q, side = t
        return ('{"symbol":"BTC/USDT","side":"%s","price":%s,"qty":%s,"ord_type":"limit",'
                '"trade_id":%d,"timestamp":"%s"}' % (side, price, qty or q, tid, _rfc3339(ns)))

    def _frame(self, typ, items):
        return ('{"channel":"trade","type":"%s","data":[%s]}' % (typ, ",".join(items))).encode()

    def _push(self, at, kind, opcode, payload):
        self.order += 1
        heapq.heappush(self.queue, (at, self.order, "kraken", kind, opcode, payload))

    def open(self, venue, timeout_s=None):
        self.clock.now += 50
        self.open_ = True

    def close(self, venue, timeout_s=None):
        self.open_ = self.sub = False
        self.next_tick = self.next_hb = None
        self.queue = []

    def send_text(self, venue, text, timeout_s=None):
        doc = json.loads(text)
        at = self.clock.now + self.latency
        if doc.get("method") != "subscribe":
            return
        if any(f[0] == "refuse" for f in self.faults):
            self._push(at, "ws_message", wire.OP_TEXT,
                       b'{"error":"Currency pair not supported","method":"subscribe","success":false}')
            return
        self.sub, self.sub_at = True, at
        self._push(at, "ws_message", wire.OP_TEXT,
                   b'{"method":"subscribe","result":{"channel":"trade","snapshot":true,'
                   b'"symbol":"BTC/USDT"},"success":true,"req_id":1}')
        snap = [self._make_trade(at - 2_000 * (50 - i), 123_000) for i in range(50)]
        self._push(at + 1, "ws_message", wire.OP_TEXT, self._frame("snapshot", [self._item(t) for t in snap]))
        self.next_tick, self.next_hb = at + self.every, at + 1_000

    def _emit_tick(self, at):
        rel = at - self.sub_at
        n = 1 + self.rng.randint(0, 2)
        batch = [self._make_trade(at - 20, 1_000 * i + 7) for i in range(n)]
        if self._fault("id_gap", rel):
            batch = batch[1:]
        if self._fault("close", rel):
            self._push(at, "ws_close", wire.OP_CLOSE, wire.close_payload(1001))
            self.next_tick = self.next_hb = None
            return
        items = [self._item(t, "1e-05" if (i == 0 and self._fault("exponent", rel)) else None)
                 for i, t in enumerate(batch)]
        if items and not self._fault("silence", rel):
            self._push(at, "ws_message", wire.OP_TEXT, self._frame("update", items))
        self.next_tick = at + self.every

    def poll(self, until_wall_ms):
        while self.sub:
            cands = [t for t in (self.next_tick, self.next_hb) if t is not None]
            nxt = min(cands) if cands else None
            if nxt is None or nxt > until_wall_ms or (self.queue and self.queue[0][0] <= nxt):
                break
            if nxt == self.next_tick:
                self._emit_tick(nxt)
            else:
                if not self._fault("silence", nxt - self.sub_at):
                    self._push(nxt, "ws_message", wire.OP_TEXT, b'{"channel":"heartbeat"}')
                self.next_hb = nxt + 1_000
        if self.queue and self.queue[0][0] <= until_wall_ms:
            at, _, venue, kind, opcode, payload = heapq.heappop(self.queue)
            self.clock.now = max(self.clock.now, at)
            if not self.open_ and kind != "ws_close":
                return []
            return [(venue, kind, opcode, payload)]
        self.clock.now = max(self.clock.now, until_wall_ms)
        return []

    def rest(self, url):
        if not allowed_url(url):
            raise l3.Refused("URL outside the allow-list")
        self.clock.now += 120
        now = self.clock.now
        if url == STATIC_URLS["time"]:
            body = json.dumps({"error": [], "result": {"unixtime": (now - 60) // 1000, "rfc1123": "x"}})
        elif url == STATIC_URLS["assetPairs"]:
            body = json.dumps({"error": [], "result": {REST_KEY: {
                "altname": REST_PAIR, "wsname": "XBT/USDT", "base": BASE_ASSET, "quote": "USDT",
                "status": "online"}}})
        elif url == STATIC_URLS["assets"]:
            body = json.dumps({"error": [], "result": {BASE_ASSET: {"aclass": "currency", "altname": BASE_ALT}}})
        else:
            since = int(_TRADES_URL.fullmatch(url).group(1))
            since_ns = since * 1_000_000_000 if since < 10**12 else since
            rows = [t for t in self.trades if t[1] > since_ns][:REST_PAGE_ROWS]
            last = str(rows[-1][1] if rows else since_ns)
            body = ('{"error":[],"result":{"%s":[%s],"last":"%s"}}' % (REST_KEY, ",".join(
                '["%s","%s",%d.%04d,"%s","l","",%d]' % (p, q, ns // 10**9, (ns % 10**9) // 10**5,
                                                         "b" if s == "buy" else "s", tid)
                for tid, ns, p, q, s in rows), last))
        return 200, {"Content-Type": "application/json"}, body.encode(), None


# ---------------------------------------------------------------- CLI

def dry_run(out, *, faults=(), capture_ms=CAPTURE_MS, caps=None, seed=11):
    clock = FakeNsClock(DRY_RUN_START_MS)
    session = FakeKraken(clock, faults=faults, seed=seed)
    pilot = TradePilot(out, session, clock, evidence_kind="SYNTHETIC", caps=caps, capture_ms=capture_ms,
                       watchdog_s=None)
    pilot.watchdog_s = None  # a synthetic clock must never arm a real timer
    return pilot, pilot.run()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kraken_trade_pilot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dry-run")
    d.add_argument("--out", required=True)
    sub.add_parser("code-sha256")
    r = sub.add_parser("run")
    r.add_argument("--out", required=True)
    r.add_argument("--code-sha256", required=True)
    r.add_argument("--confirm-public-collection", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "code-sha256":
            print(code_identity()["digest"])
            return 0
        if a.cmd == "dry-run":
            pilot, code = dry_run(a.out)
        else:
            if a.confirm_public_collection != CONFIRM_TOKEN:
                raise l3.Refused(f"public run requires --confirm-public-collection {CONFIRM_TOKEN}")
            if a.code_sha256 != code_identity()["digest"]:
                raise l3.Refused("--code-sha256 does not match this checkout")
            clock = NsClock()
            pilot = TradePilot(a.out, KrakenTradeSession(clock), clock)
            code = pilot.run()
        print(json.dumps({"exit_code": code, "stop_code": pilot.stop_code, "frames": pilot.frames,
                          "out": os.fspath(a.out)}, indent=2, sort_keys=True))
        return code
    except l3.Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
