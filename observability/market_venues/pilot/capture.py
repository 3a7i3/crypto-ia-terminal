"""Time evidence and pure metadata/probe qualification."""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import time
from observability.market_venues.decoders import strict_json, number


@dataclass(frozen=True)
class Instant:
    utc_ns: int
    monotonic_ns: int

    @property
    def utc(self):
        seconds, nanos = divmod(self.utc_ns, 1000000000)
        return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
            seconds=seconds, microseconds=nanos // 1000
        )


class SystemClock:
    def sample(self):
        return Instant(time.time_ns(), time.monotonic_ns())


@dataclass(frozen=True)
class Response:
    status: int | None
    body: bytes | None
    headers: dict
    error: str | None = None
    complete: bool = True


@dataclass(frozen=True)
class Capture:
    spec: object
    response: Response
    before: Instant
    after: Instant

    def timing_problem(self, plan):
        elapsed = self.after.monotonic_ns - self.before.monotonic_ns
        wall = self.after.utc_ns - self.before.utc_ns
        if (
            elapsed < 0
            or wall < 0
            or abs(elapsed - wall) > plan.max_clock_jump_ms * 1000000
        ):
            return "CLOCK_JUMP"
        if elapsed > plan.max_rtt_ms * 1000000:
            return "ROUND_TRIP_TOO_LONG"
        return None

    def response_problem(self):
        if self.response.error:
            return self.response.error
        if (
            self.response.status in (401, 403, 429)
            or self.response.status is not None
            and 300 <= self.response.status < 400
        ):
            return "ACCESS_OR_RATE_LIMIT_REFUSED"
        if self.response.status != 200:
            return "HTTP_UNAVAILABLE"
        if not self.response.complete or not isinstance(self.response.body, bytes):
            return "INCOMPLETE_RESPONSE"
        if (
            self.response.headers.get("content-type", "").split(";")[0].strip().lower()
            != "application/json"
        ):
            return "NON_JSON_RESPONSE"
        return None

    @property
    def payload_sha256(self):
        if self.response.body is None:
            return None
        import hashlib

        return hashlib.sha256(self.response.body).hexdigest()


def metadata_problem(capture, binding, plan):
    problem = capture.response_problem() or capture.timing_problem(plan)
    if problem:
        return problem
    try:
        doc = strict_json(capture.response.body)
        base = binding.instrument.base_asset_id
        if binding.venue == "bybit":
            if (
                type(doc["retCode"]) is not int
                or doc["retCode"] != 0
                or doc["result"]["category"] != "spot"
            ):
                return "METADATA_PRODUCT_MISMATCH"
            rows = doc["result"]["list"]
            if not isinstance(rows, list) or len(rows) != 1:
                return "METADATA_POPULATION_MISMATCH"
            row = rows[0]
            if (row["symbol"], row["baseCoin"], row["quoteCoin"], row["status"]) != (
                binding.native_symbol,
                base,
                "USDT",
                "Trading",
            ):
                return "METADATA_IDENTITY_OR_STATUS_MISMATCH"
            number(row["priceFilter"]["tickSize"])
            number(row["lotSizeFilter"]["basePrecision"])
        else:
            if (
                doc["code"] != "0"
                or not isinstance(doc["data"], list)
                or len(doc["data"]) != 1
            ):
                return "METADATA_POPULATION_MISMATCH"
            row = doc["data"][0]
            if (
                row["instId"],
                row["instType"],
                row["baseCcy"],
                row["quoteCcy"],
                row["state"],
            ) != (binding.native_symbol, "SPOT", base, "USDT", "live"):
                return "METADATA_IDENTITY_OR_STATUS_MISMATCH"
            number(row["tickSz"])
            number(row["lotSz"])
    except (KeyError, TypeError, ValueError, IndexError, RecursionError):
        return "INVALID_METADATA"
    return None


def probe_result(capture, plan):
    reason = capture.response_problem() or capture.timing_problem(plan)
    if reason:
        return {"status": "NOT_AVAILABLE", "reason": reason}
    try:
        doc = strict_json(capture.response.body)
        if capture.spec.venue == "bybit":
            if type(doc["retCode"]) is not int or doc["retCode"] != 0:
                raise ValueError()
            raw = doc["result"]["timeNano"]
            if not isinstance(raw, str) or not raw.isdigit() or len(raw) > 20:
                raise ValueError()
            server_ns = int(raw)
            seconds = doc["result"]["timeSecond"]
            if (
                not isinstance(seconds, str)
                or not seconds.isdigit()
                or int(seconds) != server_ns // 1000000000
            ):
                raise ValueError()
            resolution = 1
        else:
            if doc["code"] != "0" or len(doc["data"]) != 1:
                raise ValueError()
            raw = doc["data"][0]["ts"]
            if not isinstance(raw, str) or not raw.isdigit() or len(raw) > 16:
                raise ValueError()
            server_ns = int(raw) * 1000000
            resolution = 1000000
        lower = server_ns - capture.after.utc_ns
        upper = server_ns + resolution - capture.before.utc_ns
        allowed = plan.max_clock_offset_ms * 1000000
        status = (
            "AVAILABLE" if -allowed <= lower <= upper <= allowed else "NOT_AVAILABLE"
        )
        return {
            "status": status,
            "reason": None if status == "AVAILABLE" else "CLOCK_OFFSET_BOUND_EXCEEDED",
            "offset_lower_ms": str(Decimal(lower) / 1000000),
            "offset_upper_ms": str(Decimal(upper) / 1000000),
            "round_trip_ms": str(
                Decimal(capture.after.monotonic_ns - capture.before.monotonic_ns)
                / 1000000
            ),
            "assumption": "SERVER_TIMESTAMP_WITHIN_REQUEST_INTERVAL_NOT_PHYSICAL_CLOCK_CERTIFICATION",
        }
    except (KeyError, TypeError, ValueError, IndexError, RecursionError):
        return {"status": "NOT_AVAILABLE", "reason": "INVALID_TIME_PROBE"}
