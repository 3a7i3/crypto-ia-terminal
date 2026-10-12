"""Laboratory-only bounded ingestion of supplied bytes; no acquisition or IO.

This module never constructs native evidence, admits an epoch or claims fsync.
One instance represents one declared stream/producer boot, not a whole campaign.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

from research_data.stress_d1_evidence_contract import (
    EvidenceIntegrityError,
    finite_json_float,
    native_id,
    require,
    utc_time,
)

IDENTITY = (
    "stream_id",
    "producer_id",
    "producer_version",
    "process_boot_id",
    "paper_epoch_id",
    "code_sha",
    "config_sha256",
    "capture_campaign_id",
)
FIELDS = set(IDENTITY) | {
    "schema_version",
    "producer_sequence",
    "event_id",
    "event_time_utc",
    "monotonic_ns",
    "clock_domain",
    "clock_quality",
    "payload",
}


def _unique(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


@dataclass(frozen=True)
class CaptureLimits:
    max_events: int
    max_bytes: int
    max_event_bytes: int

    def __post_init__(self) -> None:
        require(
            all(
                type(v) is int and v > 0
                for v in (self.max_events, self.max_bytes, self.max_event_bytes)
            ),
            "INVALID_CAPTURE_LIMITS",
        )
        require(self.max_event_bytes <= self.max_bytes, "INVALID_CAPTURE_LIMITS")


@dataclass(frozen=True)
class SealedCapture:
    """Exact accepted raw bytes and canonical manifest bytes, both immutable."""

    events: tuple[bytes, ...]
    manifest_bytes: bytes
    manifest_sha256: str


class BoundedCapture:
    """No env, paths, disk, sockets, native IDs or syscall evidence generated.

    Identity is caller-declared, never authenticated. Accepted bytes and ID set
    are bounded; sequence gap totals/refusal counters are constant-sized. Sealing
    allocates a bounded manifest, not a measured RSS or host capacity guarantee.
    No eviction: saturation retains previous records and marks incomplete.
    """

    def __init__(self, *, identity: dict[str, str], limits: CaptureLimits) -> None:
        require(
            type(identity) is dict and set(identity) == set(IDENTITY),
            "INVALID_STREAM_IDENTITY",
        )
        self._identity = {
            k: native_id(identity[k], "INVALID_STREAM_IDENTITY") for k in IDENTITY
        }
        require(
            len(self._identity["code_sha"]) == 40
            and all(c in "0123456789abcdef" for c in self._identity["code_sha"]),
            "INVALID_CODE_SHA",
        )
        require(
            len(self._identity["config_sha256"]) == 64
            and all(c in "0123456789abcdef" for c in self._identity["config_sha256"]),
            "INVALID_CONFIG_HASH",
        )
        require(isinstance(limits, CaptureLimits), "INVALID_CAPTURE_LIMITS")
        # Identity strings also have a configured byte bound.
        require(
            sum(len(v.encode("utf-8")) for v in self._identity.values())
            <= limits.max_event_bytes,
            "IDENTITY_TOO_LARGE",
        )
        self._limits = limits
        self._events: list[bytes] = []
        self._ids: set[str] = set()
        self._bytes = 0
        self._last_sequence = 0
        self._last_monotonic: int | None = None
        self._clock_domain: str | None = None
        self._gap_count = 0
        self._refusals: Counter[str] = Counter()
        self._sealed: SealedCapture | None = None

    def append(self, raw: bytes) -> bool:
        """Malformed bytes raise; valid capacity refusals return False.

        Every refusal before seal is visible. No IDs are kept for refused records,
        so duplicate detection is only for retained records; out-of-order sequence
        is always rejected across all valid observed records, including refusals.
        """
        require(self._sealed is None, "CAPTURE_SEALED")
        try:
            require(type(raw) is bytes, "IMMUTABLE_BYTES_REQUIRED")
            require(len(raw) <= self._limits.max_event_bytes, "EVENT_TOO_LARGE")
            try:
                event = json.loads(
                    raw.decode("utf-8"),
                    object_pairs_hook=_unique,
                    parse_float=finite_json_float,
                    parse_constant=lambda _: require(False, "NONFINITE_JSON"),
                )
            except (
                UnicodeError,
                json.JSONDecodeError,
                RecursionError,
                ValueError,
            ) as exc:
                # EvidenceIntegrityError is a ValueError: preserve its diagnostic.
                if isinstance(exc, EvidenceIntegrityError):
                    raise
                raise EvidenceIntegrityError("INVALID_EVENT_JSON") from exc
            require(
                type(event) is dict and set(event) == FIELDS, "INVALID_EVENT_FIELDS"
            )
            require(
                event["schema_version"] == "FUTURE_NATIVE_EVENT_V1", "INVALID_SCHEMA"
            )
            require(
                all(event[k] == v for k, v in self._identity.items()),
                "IDENTITY_MISMATCH",
            )
            event_id = native_id(event["event_id"], "INVALID_EVENT_ID")
            require(event_id not in self._ids, "DUPLICATE_EVENT_ID")
            seq = event["producer_sequence"]
            require(
                type(seq) is int and seq > self._last_sequence,
                "SEQUENCE_NOT_INCREASING",
            )
            mono = event["monotonic_ns"]
            require(
                type(mono) is int
                and mono >= 0
                and (self._last_monotonic is None or mono >= self._last_monotonic),
                "MONOTONIC_TIME_REVERSED",
            )
            domain = native_id(event["clock_domain"], "INVALID_CLOCK_DOMAIN")
            require(
                self._clock_domain is None or domain == self._clock_domain,
                "CLOCK_DOMAIN_MISMATCH",
            )
            require(
                event["clock_quality"] in ("DECLARED", "UNKNOWN"),
                "INVALID_CLOCK_QUALITY",
            )
            utc_time(event["event_time_utc"])
            require(type(event["payload"]) is dict, "INVALID_NATIVE_PAYLOAD")
        except EvidenceIntegrityError:
            self._refusals["INVALID_EVENT"] += 1
            raise
        self._gap_count += seq - self._last_sequence - 1
        self._last_sequence, self._last_monotonic, self._clock_domain = (
            seq,
            mono,
            domain,
        )
        if len(self._events) >= self._limits.max_events:
            self._refusals["EVENT_COUNT_LIMIT"] += 1
            return False
        if self._bytes + len(raw) > self._limits.max_bytes:
            self._refusals["BYTE_LIMIT"] += 1
            return False
        self._events.append(raw)
        self._ids.add(event_id)
        self._bytes += len(raw)
        return True

    def seal(self) -> SealedCapture:
        """Idempotent local freeze; never certifies queue drainage or custody."""
        if self._sealed is None:
            doc = {
                "schema_version": "FUTURE_CAPTURE_CORE_MANIFEST_V1",
                "identity": self._identity,
                "limits": {
                    "max_events": self._limits.max_events,
                    "max_bytes": self._limits.max_bytes,
                    "max_event_bytes": self._limits.max_event_bytes,
                },
                "accepted_events": len(self._events),
                "accepted_bytes": self._bytes,
                "observed_last_sequence": self._last_sequence,
                "declared_sequence_gap_count": self._gap_count,
                "refusals": dict(sorted(self._refusals.items())),
                "event_sha256": [hashlib.sha256(e).hexdigest() for e in self._events],
                "capture_status": "INCOMPLETE"
                if self._gap_count or self._refusals
                else "SUPPLIED_BYTES_RETAINED_NOT_CERTIFIED",
                "producer_completeness": "NOT_PROVEN",
                "custody": "NOT_VERIFIED",
                "native_epoch_binding": "NOT_PROVEN",
                "queue_quiescence": "NOT_PROVEN",
                "actual_persistence_proof": "NOT_OBSERVED",
                "per_packet_durability": "NOT_PROVEN",
                "future_capture_activation": "DENIED",
                "paper_stress_runtime_go": "DENIED",
            }
            raw = json.dumps(
                doc,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
            self._sealed = SealedCapture(
                tuple(self._events), raw, hashlib.sha256(raw).hexdigest()
            )
        return self._sealed
