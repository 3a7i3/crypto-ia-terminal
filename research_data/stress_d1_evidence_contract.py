"""Pure validation of declared D1 Research boundaries, never custody certification."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any


class EvidenceIntegrityError(ValueError):
    """Malformed or contradictory supplied evidence; do not repair it."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise EvidenceIntegrityError(code)


def native_id(value: Any, code: str) -> str:
    require(isinstance(value, str) and bool(value.strip()) and value == value.strip(), code)
    return value


def utc_time(value: Any) -> datetime:
    require(isinstance(value, str), "INVALID_UTC_TIME")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceIntegrityError("INVALID_UTC_TIME") from exc
    require(result.tzinfo is not None and result.utcoffset().total_seconds() == 0,
            "NAIVE_OR_NON_UTC_TIME")
    return result.astimezone(timezone.utc)


def validate_boundary(raw: Any) -> dict[str, str]:
    require(isinstance(raw, Mapping), "BOUNDARY_NOT_AVAILABLE")
    fields = ("paper_epoch_id", "code_sha", "config_sha256", "dataset_id",
              "source_boundary_id", "window_start", "window_end", "capture_cutoff")
    require(set(raw) == set(fields), "BOUNDARY_FIELDS_MISMATCH")
    result = {key: native_id(raw[key], "INVALID_BOUNDARY_ID") for key in fields}
    for key, size in (("code_sha", 40), ("config_sha256", 64)):
        require(re.fullmatch(r"[0-9a-f]{" + str(size) + r"}", result[key]) is not None,
                "INVALID_SOURCE_HASH")
    start, end, cutoff = (utc_time(result[key]) for key in
                          ("window_start", "window_end", "capture_cutoff"))
    require(start < end <= cutoff, "INVALID_BOUNDARY_WINDOW")
    return result


def bound_rows(raw: Any, boundary: Mapping[str, str]) -> list[Mapping[str, Any]]:
    require(isinstance(raw, (list, tuple)), "INVALID_ROW_COLLECTION")
    result = []
    for row in raw:
        require(isinstance(row, Mapping), "INVALID_EVIDENCE_ROW")
        require(validate_boundary(row.get("boundary")) == boundary,
                "NATIVE_BOUNDARY_MISMATCH")
        result.append(row)
    return result


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def finite_json_float(value: str, code: str = "NONFINITE_JSON") -> float:
    """Disallow exponent overflow (e.g. 1e400) even in otherwise unused fields."""
    parsed = float(value)
    require(math.isfinite(parsed), code)
    return parsed


def decode_bundle(raw: bytes, expected_sha256: str, boundary: Mapping[str, str]) -> list:
    """Check explicit bytes against an external hash pin; no file or network access.

    A caller can fabricate both bytes and pin. This check proves consistency only;
    root-owned custody, independent acquisition and signer trust are external gates.
    """
    require(type(raw) is bytes, "EXPLICIT_IMMUTABLE_BYTES_REQUIRED")
    require(isinstance(expected_sha256, str) and
            re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None,
            "INVALID_BUNDLE_HASH")
    require(hashlib.sha256(raw).hexdigest() == expected_sha256, "BUNDLE_HASH_MISMATCH")
    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                         parse_constant=lambda _: require(False, "NONFINITE_JSON"),
                         parse_float=finite_json_float)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceIntegrityError("INVALID_BUNDLE_JSON") from exc
    require(isinstance(doc, dict) and set(doc) == {"boundary", "rows"},
            "INVALID_BUNDLE_ENVELOPE")
    require(validate_boundary(doc["boundary"]) == boundary, "BUNDLE_BOUNDARY_MISMATCH")
    return bound_rows(doc["rows"], boundary)
