"""Standalone public capture for #542. No API/frontend wiring or live CLI."""

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
import argparse
import hashlib
import http.client
import json
from pathlib import Path
import re
import ssl
import time
import uuid

from .decoders import number, strict_json
from .models import iso
from .pilot.capture import Capture, Response, SystemClock
from .pilot.plan import canonical
from .pilot.store import RunStore, StorageBudgetExceeded
from .pilot.transport import request_deadline

DECISION = "https://github.com/3a7i3/crypto-ia-terminal/issues/542"
HOSTS = {"coinbase_advanced": "api.coinbase.com", "bitstamp": "www.bitstamp.net"}
NATIVES = {
    "coinbase_advanced": {"BTC": "BTC-USD", "ETH": "ETH-USD"},
    "bitstamp": {"BTC": "btcusd", "ETH": "ethusd"},
}
SAFE_HEADERS = {"content-type", "date", "age", "cache-control", "retry-after"}
SEMANTICS = "UNRESOLVED_BOOK_TIMESTAMP_SEMANTICS"


@dataclass(frozen=True)
class USSpec:
    venue: str
    purpose: str
    base: str | None = None

    def validate(self):
        if self.venue not in HOSTS or self.purpose not in ("metadata", "book"):
            raise ValueError("REQUEST_NOT_ALLOWLISTED")
        if self.venue == "bitstamp" and self.purpose == "metadata":
            if self.base is not None:
                raise ValueError("SHARED_MARKET_ROSTER_REQUIRED")
        elif self.base not in ("BTC", "ETH"):
            raise ValueError("REQUEST_NOT_ALLOWLISTED")
        return self

    @property
    def native_symbol(self):
        self.validate()
        return None if self.base is None else NATIVES[self.venue][self.base]

    @property
    def host(self):
        self.validate()
        return HOSTS[self.venue]

    @property
    def target(self):
        self.validate()
        if self.venue == "coinbase_advanced":
            return (
                "/api/v3/brokerage/market/products/" + self.native_symbol
                if self.purpose == "metadata"
                else "/api/v3/brokerage/market/product_book?product_id="
                + self.native_symbol
                + "&limit=1"
            )
        return (
            "/api/v2/markets/?entity=US_INC"
            if self.purpose == "metadata"
            else "/api/v2/order_book/" + self.native_symbol + "/?group=1"
        )

    def document(self):
        return {
            "method": "GET",
            "venue": self.venue,
            "purpose": self.purpose,
            "base": self.base,
            "native_symbol": self.native_symbol,
            "host": self.host,
            "target": self.target,
        }


def bindings():
    return [
        {
            "venue": v,
            "native_symbol": NATIVES[v][b],
            "base_asset_id": b,
            "quote_asset_id": "USD",
            "market_kind": "SPOT",
            "mapping_sha256": hashlib.sha256(
                canonical(
                    {
                        "venue": v,
                        "native_symbol": NATIVES[v][b],
                        "base": b,
                        "quote": "USD",
                        "market_kind": "SPOT",
                    }
                )
            ).hexdigest(),
        }
        for b in ("BTC", "ETH")
        for v in HOSTS
    ]


def metadata_specs():
    return (
        USSpec("coinbase_advanced", "metadata", "BTC"),
        USSpec("coinbase_advanced", "metadata", "ETH"),
        USSpec("bitstamp", "metadata"),
    )


@dataclass(frozen=True)
class USPlan:
    cycles: int = 3
    interval_ms: int = 5000
    duration_ms: int = 30000
    max_response_bytes: int = 512000
    max_run_bytes: int = 16777216
    request_timeout_ms: int = 3000
    max_age_ms: int = 5000
    max_rtt_ms: int = 1000
    max_clock_jump_ms: int = 50

    def validate(self):
        for name, low, high in [
            ("cycles", 1, 3),
            ("interval_ms", 5000, 10000),
            ("duration_ms", 1, 30000),
            ("max_response_bytes", 1024, 512000),
            ("max_run_bytes", 16384, 16777216),
            ("request_timeout_ms", 1, 3000),
            ("max_age_ms", 1, 5000),
            ("max_rtt_ms", 1, 1000),
            ("max_clock_jump_ms", 0, 50),
        ]:
            x = getattr(self, name)
            if type(x) is not int or not low <= x <= high:
                raise ValueError("INVALID_LIMIT:" + name)
        return self

    def document(self):
        self.validate()
        return {
            "schema_version": "1.0.0",
            "product": "PublicUSCapture",
            "mission": 542,
            "authority": "OBSERVATIONAL_TELEMETRY",
            "activation_authority_granted": False,
            "parameters": asdict(self),
            "maximum_requests": 3 + 4 * self.cycles,
            "bindings": bindings(),
            "endpoints": [
                s.document()
                for s in (
                    *metadata_specs(),
                    *(USSpec(v, "book", b) for b in ("BTC", "ETH") for v in HOSTS),
                )
            ],
            "app_publication": False,
            "execution_authority": False,
            "economic_metrics": None,
            "temporal_semantics": SEMANTICS,
            "exchange_clock_qualification": "NOT_PROVEN",
        }


def response_problem(capture):
    r = capture.response
    if r.error:
        return r.error
    if r.status != 200:
        return (
            "ACCESS_OR_RATE_REFUSED"
            if r.status in (401, 403, 429)
            or (r.status is not None and 300 <= r.status < 400)
            else "HTTP_UNAVAILABLE"
        )
    if not r.complete or not isinstance(r.body, bytes):
        return "INCOMPLETE_RESPONSE"
    if (
        r.headers.get("content-type", "").split(";")[0].strip().lower()
        != "application/json"
    ):
        return "NON_JSON_RESPONSE"
    try:
        d = strict_json(r.body)
    except (ValueError, RecursionError):
        return "INVALID_JSON_RESPONSE"
    if isinstance(d, dict) and any(
        k in d for k in ("error", "errors", "response_code")
    ):
        return "NATIVE_API_REFUSED"
    return None


class PublicUSHTTPS:
    evidence_kind = "OBSERVATION"

    def __init__(self, *, network_enabled=False, decision_reference=None):
        self.enabled = network_enabled is True
        if self.enabled and decision_reference != DECISION:
            raise ValueError("EXPLICIT_DECISION_REFERENCE_REQUIRED")

    def fetch(self, spec, *, timeout_ms, max_bytes):
        if not self.enabled:
            raise RuntimeError("NETWORK_DISABLED")
        if type(spec) is not USSpec:
            raise ValueError("REQUEST_NOT_ALLOWLISTED")
        spec.validate()
        if (
            type(timeout_ms) is not int
            or not 1 <= timeout_ms <= 3000
            or type(max_bytes) is not int
            or not 1024 <= max_bytes <= 512000
        ):
            raise ValueError("INVALID_TRANSPORT_LIMIT")
        connection = None
        try:
            with request_deadline(timeout_ms / 1000):
                connection = http.client.HTTPSConnection(
                    spec.host,
                    443,
                    timeout=timeout_ms / 1000,
                    context=ssl.create_default_context(),
                )
                connection.request(
                    "GET",
                    spec.target,
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                        "User-Agent": "Crypto-AI-Terminal-Passive-Capture/542",
                    },
                )
                reply = connection.getresponse()
                headers = {
                    k.lower(): v[:256]
                    for k, v in reply.getheaders()
                    if k.lower() in SAFE_HEADERS
                }
                if (
                    reply.getheader("Content-Encoding", "identity").lower()
                    != "identity"
                ):
                    return Response(
                        reply.status, None, headers, "CONTENT_ENCODING_REFUSED", False
                    )
                body = reply.read(max_bytes + 1)
                return Response(
                    reply.status,
                    body[:max_bytes],
                    headers,
                    None if len(body) <= max_bytes else "RESPONSE_TOO_LARGE",
                    len(body) <= max_bytes,
                )
        except TimeoutError:
            return Response(None, None, {}, "REQUEST_TIMEOUT", False)
        except (OSError, http.client.HTTPException):
            return Response(None, None, {}, "TRANSPORT_UNAVAILABLE", False)
        finally:
            if connection is not None:
                connection.close()


def qualify_metadata(capture, base, plan):
    problem = response_problem(capture) or capture.timing_problem(plan)
    if problem:
        return problem
    try:
        d = strict_json(capture.response.body)
        if capture.spec.venue == "coinbase_advanced":
            expected = (NATIVES["coinbase_advanced"][base], base, "USD", "SPOT")
            if (
                d["product_id"],
                d["base_currency_id"],
                d["quote_currency_id"],
                d["product_type"],
            ) != expected:
                return "METADATA_IDENTITY_MISMATCH"
            if d.get("status") != "online":
                return "METADATA_NOT_OPEN"
            if any(
                d[k] is not False
                for k in (
                    "is_disabled",
                    "trading_disabled",
                    "cancel_only",
                    "auction_mode",
                )
            ):
                return "METADATA_NOT_OPEN"
            number(d["base_increment"])
            number(d["quote_increment"])
        else:
            if not isinstance(d, list):
                return "INVALID_METADATA"
            found = [
                r
                for r in d
                if isinstance(r, dict)
                and r.get("market_symbol") == NATIVES["bitstamp"][base]
            ]
            if len(found) != 1:
                return "METADATA_POPULATION_MISMATCH"
            row = found[0]
            if (
                row["base_currency"],
                row["counter_currency"],
                row["market_type"],
                row["trading"],
            ) != (base, "USD", "SPOT", "Enabled"):
                return "METADATA_IDENTITY_MISMATCH"
            if any(
                type(row[k]) is not int or not 0 <= row[k] <= 18
                for k in ("base_decimals", "counter_decimals")
            ):
                return "INVALID_METADATA_PRECISION"
        return None
    except (ValueError, KeyError, TypeError, RecursionError):
        return "INVALID_METADATA"


def decode_book(capture, *, as_of, plan):
    spec = capture.spec
    row = {
        "venue": spec.venue,
        "native_symbol": spec.native_symbol,
        "base_asset_id": spec.base,
        "quote_asset_id": "USD",
        "market_kind": "SPOT",
        "status": "NOT_AVAILABLE",
        "reason": None,
        "bid": None,
        "ask": None,
        "bid_size_base": None,
        "ask_size_base": None,
        "native_time": None,
        "native_time_field": None,
        "native_time_utc": None,
        "native_age_ms": None,
        "age_status": "UNRESOLVED",
        "age_as_of_utc": iso(as_of),
        "received_at_utc": iso(capture.after.utc),
        "payload_sha256": capture.payload_sha256,
        "temporal_semantics": SEMANTICS,
        "exchange_clock_qualification": "NOT_PROVEN",
        "economic_metrics": None,
    }
    problem = response_problem(capture) or capture.timing_problem(plan)
    if problem:
        row["reason"] = problem
        return row
    try:
        d = strict_json(capture.response.body)
        if spec.venue == "coinbase_advanced":
            book = d["pricebook"]
            if book["product_id"] != spec.native_symbol:
                raise ValueError("BOOK_IDENTITY_MISMATCH")
            bids = [(x["price"], x["size"]) for x in book["bids"]]
            asks = [(x["price"], x["size"]) for x in book["asks"]]
            if len(bids) != 1 or len(asks) != 1:
                raise ValueError("AMBIGUOUS_BOOK_POPULATION")
            native = book.get("time")
            field = "pricebook.time"
            if not isinstance(native, str) or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z", native
            ):
                raise ValueError("INVALID_NATIVE_TIME")
            timestamp = datetime.fromisoformat(native.replace("Z", "+00:00"))
            identity = "NATIVE_PRODUCT_ECHO_AND_PREVIOUS_METADATA"
        else:
            bids, asks = d["bids"], d["asks"]
            if (
                not isinstance(bids, list)
                or not isinstance(asks, list)
                or not 1 <= len(bids) <= 10000
                or not 1 <= len(asks) <= 10000
            ):
                raise ValueError("INVALID_BOOK_POPULATION")
            native = d.get("microtimestamp")
            seconds = d.get("timestamp")
            field = "microtimestamp"
            if (
                not isinstance(native, str)
                or not re.fullmatch(r"[0-9]{16,19}", native)
                or not isinstance(seconds, str)
                or not seconds.isdigit()
                or int(native) // 1000000 != int(seconds)
            ):
                raise ValueError("INVALID_NATIVE_TIME")
            from .pilot.capture import Instant

            timestamp = Instant(int(native) * 1000, 0).utc
            identity = (
                "EXACT_REQUEST_CONTEXT_AND_PREVIOUS_US_INC_METADATA_NO_NATIVE_ECHO"
            )
        for side, descending in ((bids, True), (asks, False)):
            previous = None
            for entry in side:
                if len(entry) != 2:
                    raise ValueError("INVALID_LEVEL")
                price, size = (number(x) for x in entry)
                if previous is not None and (
                    (descending and price >= previous)
                    or (not descending and price <= previous)
                ):
                    raise ValueError("UNSORTED_OR_DUPLICATE_BOOK")
                previous = price
        bid, ask = number(bids[0][0]), number(asks[0][0])
        if bid >= ask:
            raise ValueError("CROSSED_OR_LOCKED_BOOK")
        delta = as_of - timestamp
        age = (
            Decimal((delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds)
            / 1000
        )
        row.update(
            status="OBSERVED",
            reason="TEMPORAL_QUALIFICATION_PENDING",
            bid=bids[0][0],
            ask=asks[0][0],
            bid_size_base=bids[0][1],
            ask_size_base=asks[0][1],
            native_time=native,
            native_time_field=field,
            native_time_utc=iso(timestamp),
            native_age_ms=str(age),
            age_status="FUTURE"
            if age < 0
            else "STALE"
            if age > plan.max_age_ms
            else "WITHIN_BUDGET",
            identity_evidence=identity,
        )
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError):
        row["reason"] = "INVALID_NATIVE_BOOK"
    return row


def run_capture(
    transport,
    parent,
    *,
    source_sha,
    plan=None,
    clock=None,
    sleeper=time.sleep,
    run_id=None,
):
    plan = (plan or USPlan()).validate()
    if not isinstance(source_sha, str) or not re.fullmatch(r"[a-f0-9]{40}", source_sha):
        raise ValueError("EXACT_SOURCE_SHA_REQUIRED")
    kind = transport.evidence_kind
    if kind not in ("SYNTHETIC", "OBSERVATION"):
        raise ValueError("EXPLICIT_EVIDENCE_KIND_REQUIRED")
    clock = clock or SystemClock()
    run_id = run_id or "public542-" + uuid.uuid4().hex
    store = RunStore(parent, run_id, max_bytes=plan.max_run_bytes)
    started = clock.sample()
    attempts = cycles = 0
    stop = None
    result = {
        "schema_version": "1.0.0",
        "product": "PublicUSCapture",
        "source_sha": source_sha,
        "run_id": run_id,
        "evidence_kind": kind,
        "status": "INCOMPLETE",
        "started_at_utc": iso(started.utc),
        "app_publication": False,
        "execution_authority": False,
        "temporal_semantics": SEMANTICS,
        "economic_metrics": None,
    }

    def take(spec):
        nonlocal attempts, stop
        before = clock.sample()
        remaining = (
            plan.duration_ms - (before.monotonic_ns - started.monotonic_ns) // 1000000
        )
        if remaining < 1:
            raise TimeoutError("DURATION_LIMIT")
        if attempts >= 3 + 4 * plan.cycles:
            raise RuntimeError("REQUEST_BUDGET")
        ordinal = attempts + 1
        intent = store.intent(ordinal, spec, before, run_id, kind)
        attempts = ordinal
        response = transport.fetch(
            spec,
            timeout_ms=min(remaining, plan.request_timeout_ms),
            max_bytes=plan.max_response_bytes,
        )
        after = clock.sample()
        if not isinstance(response, Response) or (
            response.body is not None
            and (
                not isinstance(response.body, bytes)
                or len(response.body) > plan.max_response_bytes
            )
        ):
            raise ValueError("INVALID_TRANSPORT_RESPONSE")
        capture = Capture(spec, response, before, after)
        store.capture(ordinal, capture, intent)
        if after.monotonic_ns - started.monotonic_ns > plan.duration_ms * 1000000:
            raise TimeoutError("DURATION_LIMIT")
        if response_problem(capture):
            stop = response_problem(capture)
        return capture

    try:
        store.json(
            "plan.json",
            {
                "plan": plan.document(),
                "source_sha": source_sha,
                "run_id": run_id,
                "evidence_kind": kind,
            },
        )
        metadata = {}
        for spec in metadata_specs():
            if stop:
                continue
            captured = take(spec)
            for base in ("BTC", "ETH") if spec.venue == "bitstamp" else (spec.base,):
                metadata[(spec.venue, base)] = qualify_metadata(captured, base, plan)
        qualification = [
            {
                "venue": b["venue"],
                "native_symbol": b["native_symbol"],
                "reason": metadata.get(
                    (b["venue"], b["base_asset_id"]), "SOURCE_NOT_ATTEMPTED"
                ),
            }
            for b in bindings()
        ]
        store.json("metadata-qualification.json", {"sources": qualification})
        if any(x["reason"] is not None for x in qualification):
            stop = stop or "METADATA_NOT_QUALIFIED"
        for cycle in range(1, plan.cycles + 1):
            if stop:
                break
            beginning = clock.sample()
            captures = []
            for b in bindings():
                spec = USSpec(b["venue"], "book", b["base_asset_id"])
                if stop:
                    captures.append((spec, None))
                    continue
                c = take(spec)
                captures.append((spec, c))
            finish = clock.sample()
            rows = [
                decode_book(c, as_of=finish.utc, plan=plan)
                if c is not None
                else {
                    "venue": spec.venue,
                    "native_symbol": spec.native_symbol,
                    "status": "NOT_AVAILABLE",
                    "reason": "SOURCE_NOT_ATTEMPTED",
                }
                for spec, c in captures
            ]
            mono = finish.monotonic_ns - started.monotonic_ns
            wall = finish.utc_ns - started.utc_ns
            if (
                mono < 0
                or wall < 0
                or abs(mono - wall) > plan.max_clock_jump_ms * 1000000
            ):
                stop = "CLOCK_JUMP"
                for row in rows:
                    row.update(
                        status="NOT_AVAILABLE",
                        reason="CLOCK_JUMP",
                        age_status="UNRESOLVED",
                    )
            store.json(
                f"cycle-{cycle:04d}.json",
                {
                    "cycle": cycle,
                    "evidence_kind": kind,
                    "as_of_utc": iso(finish.utc),
                    "sources": rows,
                    "stopped_reason": stop,
                    "app_publication": False,
                    "economic_metrics": None,
                },
            )
            cycles += 1
            if stop:
                break
            if cycle < plan.cycles:
                delay = (
                    plan.interval_ms / 1000
                    - (finish.monotonic_ns - beginning.monotonic_ns) / 1000000000
                )
                if delay <= 0:
                    stop = "CYCLE_OVERRUN"
                    break
                remaining = (
                    plan.duration_ms * 1000000
                    - (finish.monotonic_ns - started.monotonic_ns)
                ) / 1000000000
                if remaining <= 0:
                    stop = "DURATION_LIMIT"
                    break
                sleeper(min(delay, remaining))
        result["status"] = "COMPLETED" if stop is None else "STOPPED"
    except StorageBudgetExceeded:
        stop = "STORAGE_BUDGET_EXHAUSTED"
    except TimeoutError:
        stop = "DURATION_LIMIT"
    except (ValueError, RuntimeError, OSError):
        stop = "RUN_REFUSED"
        raise
    finally:
        result.update(
            stopped_reason=stop
            or (
                "INTERRUPTED_OR_UNEXPECTED_FAILURE"
                if result["status"] == "INCOMPLETE"
                else None
            ),
            requests_attempted=attempts,
            cycles_captured=cycles,
            finished_at_utc=iso(clock.sample().utc),
            bytes_before_final_receipt=store.used,
        )
        try:
            store.json("run-result.json", result, final=True)
        finally:
            store.close()
    return result


class USFake:
    evidence_kind = "SYNTHETIC"

    def __init__(self, clock):
        self.clock = clock
        self.calls = []

    def fetch(self, spec, **_):
        self.calls.append(spec)
        self.clock.advance(20)
        ms = self.clock.wall // 1000000
        if spec.purpose == "metadata":
            if spec.venue == "coinbase_advanced":
                d = {
                    "product_id": spec.native_symbol,
                    "base_currency_id": spec.base,
                    "quote_currency_id": "USD",
                    "product_type": "SPOT",
                    "status": "online",
                    "is_disabled": False,
                    "trading_disabled": False,
                    "cancel_only": False,
                    "auction_mode": False,
                    "base_increment": "0.00000001",
                    "quote_increment": "0.01",
                }
            else:
                d = [
                    {
                        "market_symbol": NATIVES["bitstamp"][b],
                        "base_currency": b,
                        "counter_currency": "USD",
                        "market_type": "SPOT",
                        "trading": "Enabled",
                        "base_decimals": 8,
                        "counter_decimals": 2,
                    }
                    for b in ("BTC", "ETH")
                ]
        elif spec.venue == "coinbase_advanced":
            d = {
                "pricebook": {
                    "product_id": spec.native_symbol,
                    "bids": [{"price": "100", "size": "2"}],
                    "asks": [{"price": "100.1", "size": "3"}],
                    "time": iso(self.clock.sample().utc),
                }
            }
        else:
            d = {
                "bids": [["100.2", "2"]],
                "asks": [["100.3", "3"]],
                "timestamp": str(ms // 1000),
                "microtimestamp": str(ms * 1000),
            }
        return Response(200, canonical(d), {"content-type": "application/json"})


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_mutually_exclusive_group(required=True)
    modes.add_argument("--plan", action="store_true")
    modes.add_argument("--simulate", action="store_true")
    modes.add_argument("--verify-run", type=Path)
    p.add_argument("--out", type=Path)
    a = p.parse_args(argv)
    if a.verify_run is not None:
        print(json.dumps(verify_capture(a.verify_run), indent=2))
        return
    if a.plan:
        print(json.dumps(USPlan().document(), indent=2))
        return
    if a.out is None:
        p.error("--out must be an existing private market-venue-pilot-runs parent")
    from .pilot.synthetic import SyntheticClock

    clock = SyntheticClock()
    print(
        json.dumps(
            run_capture(
                USFake(clock),
                a.out,
                source_sha="0" * 40,
                clock=clock,
                sleeper=clock.sleep,
            ),
            indent=2,
        )
    )


def verify_capture(path):
    """Offline chain/roster validation; never an origin or scientific certificate."""
    import os
    import stat
    from .pilot.store import open_directory

    path = Path(path)
    parent = open_directory(path.parent)
    try:
        fd = os.open(
            path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
    finally:
        os.close(parent)
    try:
        if (
            os.fstat(fd).st_uid != os.getuid()
            or stat.S_IMODE(os.fstat(fd).st_mode) != 0o700
        ):
            raise ValueError("RUN_DIRECTORY_CUSTODY")
        names = set(os.listdir(fd))

        def read(name):
            if name not in names or not re.fullmatch(
                r"[a-z0-9][a-z0-9._-]{0,95}", name
            ):
                raise ValueError("MISSING_EVIDENCE")
            f = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                st = os.fstat(f)
                if (
                    not stat.S_ISREG(st.st_mode)
                    or st.st_uid != os.getuid()
                    or stat.S_IMODE(st.st_mode) != 0o400
                    or st.st_size > 512000
                ):
                    raise ValueError("EVIDENCE_CUSTODY")
                return os.read(f, 512001)
            finally:
                os.close(f)

        header = strict_json(read("plan.json"))
        plan = USPlan(**header["plan"]["parameters"]).validate()
        if (
            header["plan"] != plan.document()
            or header["run_id"] != path.name
            or header["evidence_kind"] not in ("SYNTHETIC", "OBSERVATION")
        ):
            raise ValueError("PLAN_CHANGED")
        result = strict_json(read("run-result.json"))
        if (
            result["source_sha"] != header["source_sha"]
            or result["run_id"] != path.name
            or result["evidence_kind"] != header["evidence_kind"]
            or result["execution_authority"] is not False
            or result["status"] not in ("COMPLETED", "STOPPED", "INCOMPLETE")
            or result["app_publication"] is not False
            or result["economic_metrics"] is not None
        ):
            raise ValueError("RUN_HEADER_CHANGED")
        intents = sorted(
            n for n in names if re.fullmatch(r"attempt-[0-9]{4}\.intent\.json", n)
        )
        receipts = sorted(
            n for n in names if re.fullmatch(r"attempt-[0-9]{4}\.receipt\.json", n)
        )
        if (
            intents
            != [f"attempt-{i:04d}.intent.json" for i in range(1, len(intents) + 1)]
            or len(intents) > 3 + 4 * plan.cycles
            or len(intents) != result["requests_attempted"]
        ):
            raise ValueError("ATTEMPT_SEQUENCE_CHANGED")
        planned = [s.document() for s in metadata_specs()] + [
            USSpec(b["venue"], "book", b["base_asset_id"]).document()
            for _ in range(plan.cycles)
            for b in bindings()
        ]
        books = set()
        pending = []
        for i, name in enumerate(intents, 1):
            raw = read(name)
            intent = strict_json(raw)
            if (
                intent["ordinal"] != i
                or intent["request"] != planned[i - 1]
                or intent["evidence_kind"] != header["evidence_kind"]
            ):
                raise ValueError("INTENT_CHANGED")
            receipt_name = f"attempt-{i:04d}.receipt.json"
            if receipt_name not in names:
                pending.append(i)
                continue
            r = strict_json(read(receipt_name))
            if (
                r["ordinal"] != i
                or r["request"] != intent["request"]
                or r["intent_sha256"] != hashlib.sha256(raw).hexdigest()
            ):
                raise ValueError("RECEIPT_CHANGED")
            if r["raw_file"] is not None:
                if r["raw_file"] != f"response-{i:04d}.bin":
                    raise ValueError("RAW_REFERENCE_CHANGED")
                body = read(r["raw_file"])
                if (
                    hashlib.sha256(body).hexdigest() != r["raw_sha256"]
                    or len(body) != r["raw_bytes"]
                ):
                    raise ValueError("RAW_HASH_CHANGED")
                if r["request"]["purpose"] == "book":
                    books.add(
                        (
                            r["request"]["venue"],
                            r["request"]["native_symbol"],
                            r["raw_sha256"],
                            r["received_at_utc"],
                        )
                    )
            elif r["raw_sha256"] is not None or r["raw_bytes"] is not None:
                raise ValueError("MISSING_RAW_MISREPRESENTED")
        if len(receipts) != len(intents) - len(pending) or (
            pending and result["status"] != "INCOMPLETE"
        ):
            raise ValueError("PENDING_CAPTURE_HIDDEN")
        cycles = sorted(n for n in names if re.fullmatch(r"cycle-[0-9]{4}\.json", n))
        if len(cycles) != result["cycles_captured"] or cycles != [
            f"cycle-{i:04d}.json" for i in range(1, len(cycles) + 1)
        ]:
            raise ValueError("CYCLE_SEQUENCE_CHANGED")
        expected = [(b["venue"], b["native_symbol"]) for b in bindings()]
        for name in cycles:
            doc = strict_json(read(name))
            if (
                [(r["venue"], r["native_symbol"]) for r in doc["sources"]] != expected
                or doc["evidence_kind"] != header["evidence_kind"]
                or doc["economic_metrics"] is not None
                or doc["app_publication"] is not False
            ):
                raise ValueError("CYCLE_ROSTER_CHANGED")
            for r in doc["sources"]:
                if (
                    r.get("payload_sha256") is not None
                    and (
                        r["venue"],
                        r["native_symbol"],
                        r["payload_sha256"],
                        r["received_at_utc"],
                    )
                    not in books
                ):
                    raise ValueError("CAPTURE_LINK_CHANGED")
                if r.get("economic_metrics") is not None:
                    raise ValueError("UNQUALIFIED_ECONOMIC_METRIC")
        if result["status"] == "COMPLETED" and (
            pending
            or len(cycles) != plan.cycles
            or len(intents) != 3 + 4 * plan.cycles
            or result["stopped_reason"] is not None
        ):
            raise ValueError("FALSE_COMPLETE_RUN")
        return {
            "status": "LOCAL_COHERENCE_PASS",
            "evidence_kind": header["evidence_kind"],
            "intents": len(intents),
            "receipts": len(receipts),
            "pending_ordinals": pending,
            "cycles": len(cycles),
            "run_status": result["status"],
            "origin_certified": False,
            "scientific_certified": False,
        }
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
