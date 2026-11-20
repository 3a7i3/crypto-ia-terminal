"""Bounded public last-trade pilot (L3): BTC/USDT then ATOM/USDT Spot, MEXC + Kraken.

Only public GET requests to an allow-list of URLs. No key, account, order,
service, systemd unit or app wiring. Every request counts against a fixed
budget (metadata and clocks included). Raw responses are kept with their
context so that the measures can be replayed offline with the L1 code.

Usage (from a checkout of the exact commit):
    python3 -m observability.radar_composite.pilot run --pair BTC --out DIR
    python3 -m observability.radar_composite.pilot replay DIR
    python3 -m observability.radar_composite.pilot dry-run --pair BTC --out DIR

Exit codes: 0 completed, 2 stopped by a stop condition, 3 preflight refused,
4 usage / evidence error.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .composite import PERIOD_MS, V1_HYPOTHESIS, compute
from .decoders import (
    decode_kraken_trades, decode_mexc_trades, poll_record, strict_json,
)
from .instruments import Binding, instrument_dict, spot_instrument
from .schema import validate_composite

PILOT_VERSION = 1
STEP_MS = 10_000
POLL_LEAD_MS = 1_500          # request sent 1.5 s before each instant
WARMUP_POLLS = 1              # one poll for the instant preceding the window
PREFLIGHT_LEAD_MS = 45_000    # metadata and clocks read 45 s before the window
MAX_POLL_DELAY_MS = 5_000     # a poll later than this is skipped, never bursted
TIMEOUT_S = 4.0
TRADES_LIMIT = 10
MEXC_CLOCK_TOLERANCE_MS = 1_000
KRAKEN_CLOCK_TOLERANCE_MS = 2_000  # Kraken Time has a 1 s resolution
STOP_HTTP = (403, 418, 429)
MAX_CONSECUTIVE_FAILURES = 3
SENSITIVITY_S = (5, 10, 30, 60)
# Pre-registered reading of the primary result (fixed before any observation).
VIABLE_RATIO = 0.80
PARTIAL_RATIO = 0.50

MEXC = "https://api.mexc.com"
KRAKEN = "https://api.kraken.com"
# Documented MEXC rule: each IP-limited endpoint has an independent
# 500-per-10-seconds limit. Weights per endpoint (to confirm verbatim).
MEXC_ENDPOINT_LIMIT_10S = 500
MEXC_WEIGHTS = {"time": 1, "exchangeInfo": 10, "trades": 5}

PAIRS = {
    "BTC": {
        "base": "BTC", "quote": "USDT", "mexc": "BTCUSDT",
        "kraken_pair": "XBTUSDT", "kraken_key": "XBTUSDT", "kraken_base": "XXBT",
        "kraken_alias": "kraken.Assets:XXBT.altname=XBT",
        "windows": 2, "max_requests": 150, "max_seconds": 720,
    },
    "ATOM": {
        "base": "ATOM", "quote": "USDT", "mexc": "ATOMUSDT",
        "kraken_pair": "ATOMUSDT", "kraken_key": "ATOMUSDT", "kraken_base": "ATOM",
        "kraken_alias": None,
        "windows": 3, "max_requests": 220, "max_seconds": 1020,
    },
}
KEPT_HEADERS = ("date", "content-type", "content-length", "retry-after")
CODE_FILES = (
    "composite.py", "coverage.py", "decoders.py", "instruments.py",
    "pilot.py", "schema.py", "m5.py",
)


class Stop(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class Refused(Exception):
    pass


# ---------------------------------------------------------------- endpoints

def urls(pair):
    p = PAIRS[pair]
    q = urllib.parse.urlencode
    return {
        ("mexc", "time"): f"{MEXC}/api/v3/time",
        ("mexc", "exchangeInfo"): f"{MEXC}/api/v3/exchangeInfo?" + q({"symbol": p["mexc"]}),
        ("mexc", "trades"): f"{MEXC}/api/v3/trades?" + q({"symbol": p["mexc"], "limit": TRADES_LIMIT}),
        ("kraken", "time"): f"{KRAKEN}/0/public/Time",
        ("kraken", "assetPairs"): f"{KRAKEN}/0/public/AssetPairs?" + q({"pair": p["kraken_pair"]}),
        ("kraken", "assets"): f"{KRAKEN}/0/public/Assets?" + q({"asset": p["kraken_base"]}),
        ("kraken", "trades"): f"{KRAKEN}/0/public/Trades?" + q({"pair": p["kraken_pair"], "count": TRADES_LIMIT}),
    }


def bindings(pair):
    p = PAIRS[pair]
    ins = spot_instrument(p["base"], p["quote"])
    return ins, {
        "mexc": Binding("mexc", p["mexc"], p["mexc"], ins),
        "kraken": Binding("kraken", p["kraken_pair"], p["kraken_key"], ins, p["kraken_alias"]),
    }


def planned_requests(pair):
    polls = PAIRS[pair]["windows"] * 30 + WARMUP_POLLS
    return 5 + 2 * polls + 2  # preflight + trades + final clocks


# ---------------------------------------------------------------- transport

class UrllibTransport:
    """GET only, allow-listed URLs, no cookie, generic user agent."""

    def __init__(self, allowed):
        self.allowed = set(allowed)

    def __call__(self, url):
        if url not in self.allowed:
            raise Refused("URL outside the allow-list")
        req = urllib.request.Request(url, method="GET", headers={
            "User-Agent": "cat-public-pilot/1", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                return resp.status, dict(resp.headers.items()), resp.read(2_000_000), None
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers.items()), exc.read(200_000), f"HTTP_{exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return None, {}, b"", "TRANSPORT_" + type(exc).__name__.upper()[:40]


class RealClock:
    def wall_ms(self):
        return time.time_ns() // 1_000_000

    def mono_ms(self):
        return time.monotonic_ns() // 1_000_000

    def sleep_until_wall(self, target_ms):
        while True:
            delta = target_ms - self.wall_ms()
            if delta <= 0:
                return
            time.sleep(min(delta / 1000, 1.0))


# ---------------------------------------------------------------- evidence

def code_identity():
    root = Path(__file__).resolve().parent
    files = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in CODE_FILES}
    git_head = None
    repo = root.parent.parent
    head = repo / ".git" / "HEAD"
    try:
        ref = head.read_text().strip()
        if ref.startswith("ref: "):
            git_head = (repo / ".git" / ref[5:]).read_text().strip()
        else:
            git_head = ref
    except OSError:
        git_head = None
    return {"git_head": git_head, "files_sha256": files}


class Evidence:
    """Fresh directory; append-only request log with fsync; raw bodies by sequence."""

    def __init__(self, out):
        self.out = Path(out)
        if self.out.exists() and any(self.out.iterdir()):
            raise Refused("evidence directory must be new or empty")
        (self.out / "raw").mkdir(parents=True, exist_ok=True)
        os.chmod(self.out, 0o750)
        self.log = open(self.out / "requests.jsonl", "a", encoding="utf-8")

    def record(self, entry, body):
        name = f"raw/{entry['seq']:06d}.bin"
        with open(self.out / name, "wb") as fh:
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
        entry = {**entry, "body_file": name, "body_sha256": hashlib.sha256(body).hexdigest(),
                 "body_bytes": len(body)}
        self.log.write(json.dumps(entry, sort_keys=True) + "\n")
        self.log.flush()
        os.fsync(self.log.fileno())
        return entry

    def manifest(self, data):
        tmp = self.out / "manifest.json.tmp"
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, self.out / "manifest.json")

    def close(self):
        self.log.close()


# ---------------------------------------------------------------- runner

class Pilot:
    def __init__(self, pair, out, transport, clock, *, evidence_kind="OBSERVATION",
                 radar_check=None):
        if pair not in PAIRS:
            raise Refused("unknown pair")
        self.pair, self.cfg = pair, PAIRS[pair]
        self.urls = urls(pair)
        self.transport, self.clock = transport, clock
        self.kind = evidence_kind
        self.radar_check = radar_check
        self.evidence = Evidence(out)
        self.seq = 0
        self.failures = 0
        self.t0 = None
        self.stop_code = None
        self.events = []

    # one request, all checks
    def get(self, venue, endpoint, *, purpose):
        if self.seq >= self.cfg["max_requests"]:
            raise Stop("BUDGET_REQUESTS_EXHAUSTED")
        if self.t0 is not None and self.clock.mono_ms() - self.t0 >= self.cfg["max_seconds"] * 1000:
            raise Stop("BUDGET_DURATION_EXHAUSTED")
        url = self.urls[(venue, endpoint)]
        self.seq += 1
        if self.t0 is None:
            self.t0 = self.clock.mono_ms()
        sent = self.clock.wall_ms()
        status, headers, body, error = self.transport(url)
        received = self.clock.wall_ms()
        kept = {k.lower(): v for k, v in headers.items()
                if k.lower() in KEPT_HEADERS or k.lower().startswith("x-mexc-")}
        entry = self.evidence.record({
            "seq": self.seq, "venue": venue, "endpoint": endpoint, "purpose": purpose,
            "url": url, "sent_ms": sent, "received_ms": received, "status": status,
            "error": error, "headers": kept,
        }, body)
        if status in STOP_HTTP:
            raise Stop(f"HTTP_{status}")
        failed = status != 200
        if venue == "kraken" and status == 200:
            try:
                doc = strict_json(body)
                errs = doc.get("error") if isinstance(doc, dict) else None
            except ValueError:
                errs, failed = None, True
            if errs:
                text = " ".join(map(str, errs))
                if any(s in text for s in ("Too many requests", "Rate limit", "Temporary lockout")):
                    raise Stop("KRAKEN_RATE_LIMIT")
                failed = True
        self.failures = self.failures + 1 if failed else 0
        if self.failures >= MAX_CONSECUTIVE_FAILURES:
            raise Stop("THREE_CONSECUTIVE_FAILURES")
        return entry, body, failed

    def preflight(self):
        b = self.cfg
        checks = {}
        if self.radar_check is not None:
            ok, detail = self.radar_check()
            checks["mexc_margin"] = detail
            if not ok:
                raise Stop("MEXC_MARGIN_NOT_ESTABLISHED")
        else:
            checks["mexc_margin"] = "NOT_CHECKED_DRY_RUN"
        e, body, failed = self.get("mexc", "time", purpose="clock")
        offset = self._offset(e, body, "mexc")
        checks["mexc_clock_offset_ms"] = offset
        e, body, failed = self.get("mexc", "exchangeInfo", purpose="identity")
        info = strict_json(body) if not failed else {}
        sym = [s for s in info.get("symbols", []) if s.get("symbol") == b["mexc"]]
        if len(sym) != 1 or sym[0].get("baseAsset") != b["base"] or sym[0].get("quoteAsset") != b["quote"] \
                or sym[0].get("status") != "1" or sym[0].get("isSpotTradingAllowed") is not True:
            raise Stop("PREFLIGHT_MEXC_IDENTITY")
        checks["mexc_identity"] = "LISTED"
        e, body, failed = self.get("kraken", "time", purpose="clock")
        checks["kraken_clock_offset_ms"] = self._offset(e, body, "kraken")
        e, body, failed = self.get("kraken", "assetPairs", purpose="identity")
        res = strict_json(body).get("result", {}) if not failed else {}
        pair = res.get(b["kraken_key"])
        if set(res) != {b["kraken_key"]} or not isinstance(pair, dict) \
                or pair.get("altname") != b["kraken_pair"] or pair.get("base") != b["kraken_base"] \
                or pair.get("status") != "online":
            raise Stop("PREFLIGHT_KRAKEN_IDENTITY")
        e, body, failed = self.get("kraken", "assets", purpose="identity")
        assets = strict_json(body).get("result", {}) if not failed else {}
        altname = assets.get(b["kraken_base"], {}).get("altname")
        expected_alt = b["kraken_pair"][: -len(b["quote"])]
        if altname != expected_alt:
            raise Stop("PREFLIGHT_KRAKEN_ASSET_ALIAS")
        checks["kraken_identity"] = f"{b['kraken_key']} base={b['kraken_base']} altname={altname}"
        if offset is None or abs(offset) > MEXC_CLOCK_TOLERANCE_MS:
            raise Stop("PREFLIGHT_MEXC_CLOCK")
        k = checks["kraken_clock_offset_ms"]
        if k is None or abs(k) > KRAKEN_CLOCK_TOLERANCE_MS:
            raise Stop("PREFLIGHT_KRAKEN_CLOCK")
        return checks

    def _offset(self, entry, body, venue):
        if entry["status"] != 200:
            return None
        try:
            doc = strict_json(body)
            server = doc["serverTime"] if venue == "mexc" else int(doc["result"]["unixtime"]) * 1000
        except (ValueError, KeyError, TypeError):
            return None
        return int(server - (entry["sent_ms"] + entry["received_ms"]) / 2)

    def run(self, start_ms=None):
        now = self.clock.wall_ms()
        if start_ms is None:
            start_ms = -(-(now + PREFLIGHT_LEAD_MS + 15_000) // PERIOD_MS) * PERIOD_MS
        instants = [start_ms + i * STEP_MS for i in range(self.cfg["windows"] * 30)]
        polls = [instants[0] - STEP_MS * k for k in range(WARMUP_POLLS, 0, -1)] + instants
        manifest = self._manifest(start_ms, "WAITING")
        self.evidence.manifest(manifest)
        self.clock.sleep_until_wall(start_ms - PREFLIGHT_LEAD_MS)
        manifest["status"] = "RUNNING"
        self.evidence.manifest(manifest)
        exit_code = 0
        try:
            manifest["preflight"] = self.preflight()
            for instant in polls:
                due = instant - POLL_LEAD_MS
                self.clock.sleep_until_wall(due)
                if self.clock.wall_ms() - due > MAX_POLL_DELAY_MS:
                    self.events.append({"instant_ms": instant, "event": "POLL_SKIPPED_LATE"})
                    continue
                for venue in ("mexc", "kraken"):
                    self.get(venue, "trades", purpose=f"trades@{instant}")
            for venue in ("mexc", "kraken"):
                self.get(venue, "time", purpose="clock_end")
            manifest["status"] = "COMPLETED"
        except Stop as stop:
            self.stop_code = stop.code
            manifest["status"] = "STOPPED"
            exit_code = 2 if not stop.code.startswith("PREFLIGHT") else 3
        finally:
            manifest.update(stop_code=self.stop_code, requests_used=self.seq,
                            ended_wall_ms=self.clock.wall_ms(),
                            elapsed_ms=None if self.t0 is None else self.clock.mono_ms() - self.t0,
                            events=self.events)
            self.evidence.manifest(manifest)
            self.evidence.close()
        return exit_code

    def _manifest(self, start_ms, status):
        ins, binds = bindings(self.pair)
        return {
            "pilot": "CAT-RADAR-KRAKEN-MEXC-01/L3", "pilot_version": PILOT_VERSION,
            "pair": self.pair, "evidence_kind": self.kind, "status": status,
            "instrument": instrument_dict(ins),
            "bindings": {v: b.as_dict() for v, b in binds.items()},
            "window_start_ms": start_ms, "windows": self.cfg["windows"],
            "grid": {"step_ms": STEP_MS, "points_per_window": 30, "poll_lead_ms": POLL_LEAD_MS,
                     "warmup_polls": WARMUP_POLLS, "preflight_lead_ms": PREFLIGHT_LEAD_MS,
                     "max_poll_delay_ms": MAX_POLL_DELAY_MS},
            "budget": {"max_requests": self.cfg["max_requests"], "max_seconds": self.cfg["max_seconds"],
                       "planned_requests": planned_requests(self.pair)},
            "stop_rules": {"http": list(STOP_HTTP), "consecutive_failures": MAX_CONSECUTIVE_FAILURES,
                           "kraken_rate_limit_errors": True, "mexc_margin_required": True},
            "parameters_primary": copy.deepcopy(V1_HYPOTHESIS),
            "pre_registered": {"viable_ratio": VIABLE_RATIO, "partial_ratio": PARTIAL_RATIO,
                               "sensitivity_s": list(SENSITIVITY_S)},
            "endpoints": {f"{v}.{e}": u for (v, e), u in self.urls.items()},
            "code": code_identity(),
            "host": platform.node(), "python": platform.python_version(),
            "created_wall_ms": self.clock.wall_ms(),
        }


# ---------------------------------------------------------------- replay

def _load(out):
    out = Path(out)
    manifest = json.loads((out / "manifest.json").read_text())
    entries = []
    for line in (out / "requests.jsonl").read_text().splitlines():
        entry = json.loads(line)
        body = (out / entry["body_file"]).read_bytes()
        if hashlib.sha256(body).hexdigest() != entry["body_sha256"]:
            raise Refused(f"raw body {entry['seq']} does not match its hash")
        entries.append((entry, body))
    return manifest, entries


def _packet(manifest, trades, polls, start_ms, params):
    b = manifest["bindings"]
    return {
        "version": 2, "kind": manifest["evidence_kind"], "instrument": manifest["instrument"],
        "bindings": [{k: b[v][k] for k in ("venue", "native_symbol", "response_key", "alias_evidence")}
                     for v in ("mexc", "kraken")],
        "reference_venue": "mexc", "start_ms": start_ms, "parameters": params,
        "polls": polls, "trades": trades,
    }


def _params(age_s, skew_s):
    params = copy.deepcopy(V1_HYPOTHESIS)
    params["max_trade_age_ms"] = {"mexc": age_s * 1000, "kraken": age_s * 1000}
    params["max_inter_source_skew_ms"] = skew_s * 1000
    return params


def replay(out):
    """Offline: decode kept bodies with L1, compute each window, summarise."""
    out = Path(out)
    manifest, entries = _load(out)
    _, binds = bindings(manifest["pair"])
    trades, polls, decode_errors = [], [], {}
    attempted = {}
    for entry, body in entries:
        if entry["endpoint"] != "trades":
            continue
        venue = entry["venue"]
        binding = binds[venue]
        reason = None
        if entry["status"] == 200:
            try:
                if venue == "mexc":
                    got = decode_mexc_trades(body, binding=binding, requested_symbol=binding.native_symbol,
                                             received_ms=entry["received_ms"], evidence_kind=manifest["evidence_kind"])
                else:
                    got = decode_kraken_trades(body, binding=binding, requested_pair=binding.native_symbol,
                                               received_ms=entry["received_ms"], evidence_kind=manifest["evidence_kind"])
                trades.extend(got)
            except ValueError as exc:
                reason = "DECODE_ERROR"
                decode_errors[venue] = decode_errors.get(venue, 0) + 1
                decode_errors.setdefault("detail", []).append(f"{entry['seq']}:{exc}")
        else:
            reason = entry["error"] or f"HTTP_{entry['status']}"
        reason = None if reason is None else "".join(c if c.isalnum() else "_" for c in reason.upper())[:60]
        polls.append(poll_record(binding, provider=venue, requested_ms=entry["sent_ms"],
                                 received_ms=entry["received_ms"],
                                 status="OK" if reason is None else "FETCH_ERROR", reason=reason))
        instant = int(entry["purpose"].split("@", 1)[1])
        attempted.setdefault(instant, set()).add(venue)
    # An instant is evaluated when the run completed, or when its poll round was
    # attempted on both venues before a stop. Later instants are planned only.
    if manifest["status"] == "COMPLETED":
        evaluated_instants = None
    else:
        evaluated_instants = {i for i, v in attempted.items() if v == {"mexc", "kraken"}}
    rdir = out / "replay"
    rdir.mkdir(exist_ok=True)
    windows = []
    for w in range(manifest["windows"]):
        start = manifest["window_start_ms"] + w * PERIOD_MS
        pub = compute(_packet(manifest, trades, polls, start, _params(5, 5)))
        if not validate_composite(pub):
            raise Refused("replayed publication fails validation")
        (rdir / f"window_{w}_primary.json").write_text(json.dumps(pub, indent=2) + "\n")
        windows.append(_summarise(w, pub, evaluated_instants))
        sens = {"age_varies_skew_fixed_5s": {}, "skew_varies_age_fixed_60s": {}, "grid": {}}
        for age in SENSITIVITY_S:
            for skew in SENSITIVITY_S:
                p = compute(_packet(manifest, trades, polls, start, _params(age, skew)))
                count = _summarise(w, p, evaluated_instants)["comparable"]
                sens["grid"][f"age{age}s_skew{skew}s"] = count
                if skew == 5:
                    sens["age_varies_skew_fixed_5s"][f"{age}s"] = count
                if age == 60:
                    sens["skew_varies_age_fixed_60s"][f"{skew}s"] = count
        windows[-1]["sensitivity"] = sens
    evaluated = sum(w["evaluated"] for w in windows)
    comparable = sum(w["comparable"] for w in windows)
    ratio = None if evaluated == 0 else comparable / evaluated
    verdict = ("NO_EVALUATED_INSTANT" if ratio is None else
               "COMPOSITE_VIABLE_AT_PRIMARY" if ratio >= VIABLE_RATIO else
               "PARTIAL_AT_PRIMARY" if ratio >= PARTIAL_RATIO else "NOT_VIABLE_AT_PRIMARY")
    summary = {
        "pair": manifest["pair"], "status": manifest["status"], "stop_code": manifest.get("stop_code"),
        "requests_used": manifest.get("requests_used"), "evidence_kind": manifest["evidence_kind"],
        "code": manifest["code"], "windows": windows,
        "totals": {"planned": 30 * len(windows), "evaluated": evaluated, "comparable": comparable,
                   "ratio_over_evaluated": ratio, "verdict_pre_registered": verdict},
        "trades_decoded": {v: sum(t["venue"] == v for t in trades) for v in ("mexc", "kraken")},
        "decode_errors": decode_errors,
    }
    (rdir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def _summarise(w, pub, evaluated_instants):
    cats = {"COMPARABLE": 0, "SOURCE_EXCLUDED": 0, "EVENTS_NOT_SYNCHRONIZED": 0, "NOT_EVALUATED": 0}
    reasons = {"mexc": {}, "kraken": {}}
    for point in pub["points"]:
        if evaluated_instants is not None and point["instant_ms"] not in evaluated_instants:
            cats["NOT_EVALUATED"] += 1
            continue
        if point["status"] == "COMPOSITE":
            cats["COMPARABLE"] += 1
            continue
        cats[point["pair_reason"]] += 1
        for venue, src in point["sources"].items():
            if src["state"] == "EXCLUDED":
                reasons[venue][src["reason"]] = reasons[venue].get(src["reason"], 0) + 1
    return {"window": w, "start_ms": pub["window"]["start_ms"], "planned": 30,
            "evaluated": 30 - cats["NOT_EVALUATED"], "comparable": cats["COMPARABLE"],
            "instants_by_category": cats, "source_reasons": reasons,
            "pair_exclusions": pub["pair_exclusions"]}


# ---------------------------------------------------------------- fixtures

# Synthetic activity profiles: mean seconds between trades (active vs sparse).
DRY_RUN_PROFILES = {
    "BTC": {"mexc_rate_s": 0.5, "kraken_rate_s": 2.0},
    "ATOM": {"mexc_rate_s": 5.0, "kraken_rate_s": 200.0},
}


class FakeClock:
    def __init__(self, wall_ms):
        self.now = wall_ms

    def wall_ms(self):
        return self.now

    def mono_ms(self):
        return self.now

    def sleep_until_wall(self, target_ms):
        self.now = max(self.now, target_ms)


class FakeExchanges:
    """Deterministic synthetic venues answering the allow-listed URLs (no network)."""

    def __init__(self, pair, clock, *, seed=1, mexc_rate_s=0.5, kraken_rate_s=2.0,
                 latency_ms=120, script=None):
        self.pair, self.clock, self.cfg = pair, clock, PAIRS[pair]
        self.urls = {u: k for k, u in urls(pair).items()}
        self.rng = random.Random(seed)
        self.rates = {"mexc": mexc_rate_s, "kraken": kraken_rate_s}
        self.latency = latency_ms
        self.script = dict(script or {})  # seq -> (status, body) override
        self.calls = 0

    def _trades(self, venue):
        now = self.clock.now
        rate = self.rates[venue]
        rng = random.Random(f"{venue}:{now // 1000}")
        out = []
        t = now - rng.randint(50, int(rate * 1000))
        for i in range(TRADES_LIMIT):
            # Price and id are pure functions of the trade time: a trade seen in
            # two responses is the same trade (no conflicting duplicate).
            out.append((t, f"{62000 + (t // 1000) % 50}.{t % 100:02d}", t))
            t -= max(1, int(rng.expovariate(1 / (rate * 1000))))
        return out

    def __call__(self, url):
        self.calls += 1
        self.clock.now += self.latency
        if self.calls in self.script:
            status, body = self.script[self.calls]
            return status, {}, body, None if status == 200 else (f"HTTP_{status}" if status else "TRANSPORT_TIMEOUT")
        venue, endpoint = self.urls[url]
        c, now = self.cfg, self.clock.now
        if (venue, endpoint) == ("mexc", "time"):
            body = {"serverTime": now - self.latency // 2}
        elif (venue, endpoint) == ("mexc", "exchangeInfo"):
            body = {"timezone": "CST", "serverTime": now, "symbols": [{
                "symbol": c["mexc"], "baseAsset": c["base"], "quoteAsset": c["quote"],
                "status": "1", "isSpotTradingAllowed": True}]}
        elif (venue, endpoint) == ("kraken", "time"):
            body = {"error": [], "result": {"unixtime": (now - self.latency // 2) // 1000, "rfc1123": "x"}}
        elif (venue, endpoint) == ("kraken", "assetPairs"):
            body = {"error": [], "result": {c["kraken_key"]: {
                "altname": c["kraken_pair"], "wsname": "x", "base": c["kraken_base"],
                "quote": "USDT", "status": "online"}}}
        elif (venue, endpoint) == ("kraken", "assets"):
            body = {"error": [], "result": {c["kraken_base"]: {
                "aclass": "currency", "altname": c["kraken_pair"][: -len(c["quote"])], "status": "enabled"}}}
        elif venue == "mexc":
            body = [{"id": None, "price": p, "qty": "0.001", "quoteQty": "1", "time": t,
                     "isBuyerMaker": bool(i % 2), "isBestMatch": True}
                    for i, (t, p, _) in enumerate(self._trades("mexc"))]
        else:
            rows = [[p, "0.001", float(f"{t / 1000:.4f}"), "b", "l", "", tid]
                    for t, p, tid in self._trades("kraken")]
            body = {"error": [], "result": {c["kraken_key"]: rows, "last": str(now * 1_000_000)}}
        return 200, {"Content-Type": "application/json"}, json.dumps(body).encode(), None


# ---------------------------------------------------------------- radar margin check

def radar_margin_check(collector_path, expected_sha256):
    """MEXC margin proof for the shared IP, read-only.

    MEXC documents an independent 500-per-10-seconds limit per IP-limited
    endpoint. The pilot is the only caller of /api/v3/trades if the deployed
    Radar collector is the audited file (sha256) and never calls that endpoint.
    Shared endpoints (time, exchangeInfo) receive 3 pilot calls in total.
    """
    def check():
        try:
            data = Path(collector_path).read_bytes()
        except OSError:
            return False, "RADAR_COLLECTOR_UNREADABLE"
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected_sha256:
            return False, f"RADAR_COLLECTOR_CHANGED:{digest}"
        if b"/api/v3/trades" in data:
            return False, "RADAR_USES_TRADES_ENDPOINT"
        return True, f"RADAR_COLLECTOR_AUDITED:{digest}:NO_TRADES_ENDPOINT"
    return check


# ---------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(prog="pilot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "dry-run"):
        s = sub.add_parser(name)
        s.add_argument("--pair", choices=sorted(PAIRS), required=True)
        s.add_argument("--out", required=True)
        if name == "run":
            s.add_argument("--radar-collector", required=True)
            s.add_argument("--radar-collector-sha256", required=True)
    r = sub.add_parser("replay")
    r.add_argument("out")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "replay":
            print(json.dumps(replay(a.out)["totals"], indent=2))
            return 0
        if a.cmd == "dry-run":
            clock = FakeClock(1_795_128_000_000 - 120_000)
            pilot = Pilot(a.pair, a.out, FakeExchanges(a.pair, clock, **DRY_RUN_PROFILES[a.pair]),
                          clock, evidence_kind="SYNTHETIC")
        else:
            transport = UrllibTransport(urls(a.pair).values())
            pilot = Pilot(a.pair, a.out, transport, RealClock(),
                          radar_check=radar_margin_check(a.radar_collector, a.radar_collector_sha256))
        code = pilot.run()
        summary = replay(a.out)
        print(json.dumps({"exit_code": code, "stop_code": pilot.stop_code, "requests": pilot.seq,
                          "totals": summary["totals"]}, indent=2))
        return code
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
