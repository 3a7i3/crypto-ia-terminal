"""Replay only saved #542 evidence; never a capture or publication command.

Run from reviewed source with PYTHONPATH set and -B. Stdout is temporal
diagnostics only, never prices, sizes or response bodies. No files are written.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import socket
import stat


def no_network(*args, **kwargs):
    raise RuntimeError("OFFLINE_REVIEW_NETWORK_REFUSED")


# Installed before importing the reviewed producer/reader. No fallback.
class OfflineSocket(socket.socket):
    def __new__(cls, *args, **kwargs):
        return no_network(*args, **kwargs)


socket.socket = OfflineSocket
socket.create_connection = no_network
socket.getaddrinfo = no_network
socket.gethostbyname = no_network
socket.gethostbyname_ex = no_network

from observability.market_venues.public_us import (  # noqa: E402
    USPlan,
    USSpec,
    decode_book,
    qualify_metadata,
    verify_capture,
)
from observability.market_venues.pilot.capture import Capture, Instant, Response  # noqa: E402
from observability.market_venues.models import ENDPOINTS  # noqa: E402
from observability.market_venues.schema import validate_publication  # noqa: E402
from observability.operator_api.venue_comparison_reader import VenueComparisonReader  # noqa: E402

SOURCE_SHA = "1e82b9750202e62f687b2e0404e62ea84a1a1b52"
RESULT_SHA = "20a5b97800ac44f5e37d3e8a422598a7321b3ddd41e2f5609aa874b2d7faa00a"


def stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def ms(delta):
    return (
        Decimal((delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds)
        / 1000
    )


def read(path):
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_size > 512000:
        raise ValueError("REGULAR_BOUNDED_EVIDENCE_REQUIRED")
    return path.read_bytes()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def review(root):
    raw_result = read(root / "RESULT.json")
    if digest(raw_result) != RESULT_SHA:
        raise ValueError("RESULT_ANCHOR_CHANGED")
    result = json.loads(raw_result)
    if result["source_sha"] != SOURCE_SHA:
        raise ValueError("SOURCE_ANCHOR_CHANGED")
    evidence = result["evidence"]
    if len(evidence) != 65:
        raise ValueError("UNEXPECTED_EVIDENCE_POPULATION")

    def verified(name):
        # Exact indexed path only; no input-driven path traversal.
        if name not in evidence or Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("UNINDEXED_EVIDENCE")
        data = read(root / name)
        if (
            len(data) != evidence[name]["bytes"]
            or digest(data) != evidence[name]["sha256"]
        ):
            raise ValueError("EVIDENCE_CHANGED:" + name)
        return data

    for name in evidence:
        verified(name)
    prefix = "market-venue-pilot-runs/public542-real-once/"
    run = root / prefix
    verified_capture = verify_capture(run)
    plan_doc = json.loads(verified(prefix + "plan.json"))
    plan = USPlan(**plan_doc["plan"]["parameters"]).validate()
    captures, intervals, cache = {}, [], []
    first_utc = first_mono = None
    drift_ns = []
    for ordinal in range(1, 16):
        intent = json.loads(verified(prefix + f"attempt-{ordinal:04d}.intent.json"))
        receipt = json.loads(verified(prefix + f"attempt-{ordinal:04d}.receipt.json"))
        spec = USSpec(
            receipt["request"]["venue"],
            receipt["request"]["purpose"],
            receipt["request"]["base"],
        )
        if (
            spec.document() != receipt["request"]
            or intent["request"] != receipt["request"]
        ):
            raise ValueError("REQUEST_CONTEXT_CHANGED")
        response = Response(
            receipt["http_status"],
            verified(prefix + receipt["raw_file"]),
            receipt["response_headers"],
            receipt["error"],
            receipt["body_complete"],
        )
        before = Instant(
            int(intent["requested_utc_ns"]), int(intent["requested_monotonic_ns"])
        )
        after = Instant(
            int(receipt["received_utc_ns"]), int(receipt["received_monotonic_ns"])
        )
        capture = Capture(spec, response, before, after)
        captures[ordinal] = capture
        if first_utc is None:
            first_utc, first_mono = before.utc_ns, before.monotonic_ns
        for instant in (before, after):
            drift_ns.append(
                abs((instant.utc_ns - first_utc) - (instant.monotonic_ns - first_mono))
            )
        intervals.append(
            {
                "ordinal": ordinal,
                "venue": spec.venue,
                "purpose": spec.purpose,
                "round_trip_ms": str(
                    Decimal(after.monotonic_ns - before.monotonic_ns) / 1000000
                ),
                "wall_monotonic_difference_ms": str(
                    Decimal(
                        abs(
                            (after.utc_ns - before.utc_ns)
                            - (after.monotonic_ns - before.monotonic_ns)
                        )
                    )
                    / 1000000
                ),
            }
        )
        cache.append(
            {
                "ordinal": ordinal,
                "venue": spec.venue,
                "purpose": spec.purpose,
                "date": response.headers.get("date"),
                "age": response.headers.get("age"),
                "cache_control": response.headers.get("cache-control"),
            }
        )
    qualifications = []
    for ordinal, bases in ((1, ("BTC",)), (2, ("ETH",)), (3, ("BTC", "ETH"))):
        for base in bases:
            reason = qualify_metadata(captures[ordinal], base, plan)
            qualifications.append(
                {"venue": captures[ordinal].spec.venue, "base": base, "reason": reason}
            )
            if reason is not None:
                raise ValueError("METADATA_REPLAY_DIFFERS")
    rows, gaps = [], []
    replayed = 0
    for cycle_number in range(1, 4):
        cycle = json.loads(verified(prefix + f"cycle-{cycle_number:04d}.json"))
        as_of = stamp(cycle["as_of_utc"])
        for index, published in enumerate(cycle["sources"]):
            ordinal = 4 + (cycle_number - 1) * 4 + index
            capture = captures[ordinal]
            decoded = decode_book(capture, as_of=as_of, plan=plan)
            if decoded != published:
                raise ValueError("BOOK_REPLAY_DIFFERS")
            replayed += 1
            native = stamp(decoded["native_time_utc"])
            position = (
                "BEFORE_REQUEST"
                if native < capture.before.utc
                else "AFTER_RECEIPT"
                if native > capture.after.utc
                else "WITHIN_REQUEST"
            )
            rows.append(
                {
                    "cycle": cycle_number,
                    "ordinal": ordinal,
                    "venue": decoded["venue"],
                    "base": decoded["base_asset_id"],
                    "status": decoded["status"],
                    "native_age_ms": decoded["native_age_ms"],
                    "age_status": decoded["age_status"],
                    "native_time_field": decoded["native_time_field"],
                    "native_time": decoded["native_time"],
                    "native_time_utc": decoded["native_time_utc"],
                    "age_as_of_utc": decoded["age_as_of_utc"],
                    "native_position_vs_request": position,
                    "economic_metrics": decoded["economic_metrics"],
                }
            )
        for index, base in ((0, "BTC"), (2, "ETH")):
            left, right = cycle["sources"][index : index + 2]
            first = 4 + (cycle_number - 1) * 4 + index
            a, b = captures[first], captures[first + 1]
            gaps.append(
                {
                    "cycle": cycle_number,
                    "base": base,
                    "absolute_native_timestamp_difference_ms": str(
                        abs(
                            ms(
                                stamp(left["native_time_utc"])
                                - stamp(right["native_time_utc"])
                            )
                        )
                    ),
                    "separation_between_attempt_windows_ms": str(
                        Decimal(b.before.monotonic_ns - a.after.monotonic_ns) / 1000000
                    ),
                    "physical_simultaneity": "NOT_PROVEN",
                }
            )
    rejection = {}
    for name in (
        "run-result.json",
        "cycle-0001.json",
        "cycle-0002.json",
        "cycle-0003.json",
    ):
        data = json.loads(verified(prefix + name))
        valid = validate_publication(data)
        reader = VenueComparisonReader(
            path=run / name, now_fn=lambda: 1793510646
        ).read()
        if valid or reader.ok or reader.error_code != "VENUE_COMPARISON_INVALID_SCHEMA":
            raise ValueError("UNEXPECTED_ACTIVE_FORMAT_ADMISSION")
        rejection[name] = reader.error_code
    for name in evidence:
        verified(name)  # Inputs unchanged after the replay.
    admission = json.loads(verified("ADMISSION_REAL_ONCE.json"))
    now = datetime.now(timezone.utc)
    summary = {
        "review": 543,
        "capture_source_sha": SOURCE_SHA,
        "input_result_sha256": RESULT_SHA,
        "reviewed_at_utc": now.isoformat(),
        "network_calls_by_review": 0,
        "original_indexed_files_unchanged": 65,
        "verification": verified_capture,
        "native_book_rows_replayed_exactly": replayed,
        "metadata_requalification": qualifications,
        "temporal_rows": rows,
        "numeric_native_timestamp_gaps": gaps,
        "request_durations": intervals,
        "saved_cache_headers": cache,
        "age_header_missing": sum(c["age"] is None for c in cache),
        "cache_control_values": dict(
            Counter(c["cache_control"] or "NOT_SUPPLIED" for c in cache)
        ),
        "max_cumulative_wall_monotonic_difference_ms": str(
            Decimal(max(drift_ns)) / 1000000
        ),
        "observer_preflight_ntp": admission["ntp"],
        "observer_preflight_chrony": admission["chrony"],
        "observer_preflight_at_utc": admission["observed_at_utc"],
        "clock_probe_requests": sum(
            c.spec.purpose == "time" for c in captures.values()
        ),
        "active_schema_rejection_offline": rejection,
        "missing_active_venue_ids": [
            v for v in ("coinbase_advanced", "bitstamp") if v not in ENDPOINTS
        ],
        "samples_historical_now": all(
            ms(now - stamp(r["native_time_utc"])) > plan.max_age_ms for r in rows
        ),
        "verdict": "NOT_ADMITTED_FOR_APP_OR_ECONOMIC_COMPARISON",
        "app_publication": False,
        "new_capture_authorized": False,
        "economic_metrics": None,
    }
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_root", type=Path)
    args = parser.parse_args()
    print(json.dumps(review(args.evidence_root), indent=2, sort_keys=True))
