"""Input contract of a derivatives positioning observation (Plateformes & levier, lot 1).

A collector hands a plain JSON-compatible mapping to ``PositioningStore.ingest``. It
does not need to know how the observation is stored. This module validates the
mapping, normalises exact decimals, and computes two digests:

* ``observation_key`` identifies the observation (what was observed, when);
* ``content_sha256`` identifies what was recorded about it.

Rules (see docs/contracts/MARKET_DERIVATIVES_POSITIONING_01.md):

* every measure is present, either with a value or with an explicit reason;
* the receipt time and the collector run never enter the identity nor the content,
  so a replay received later is a duplicate, not a new observation;
* without a source time, the identity is the payload digest plus an optional
  ``capture_id`` declared by the collector.

Nothing here scores, ranks or interprets a sign.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import re

from observability.market_stress import metrics
from observability.market_stress.models import DERIVATIVE_KINDS, NATIVE_SYMBOL, OI_UNITS, VENUE_ID

CONTRACT_VERSION = "1.0.0"
CONTRACT_TYPES = DERIVATIVE_KINDS
MEASURES = ("mark_price", "index_price", "spot_reference", "open_interest", "funding_rate")
CURRENCY = re.compile(r"[A-Z0-9]{2,15}")
REASON = re.compile(r"[A-Z][A-Z0-9_]{2,63}")
SHA256 = re.compile(r"[a-f0-9]{64}")
TOKEN = re.compile(r"[A-Za-z0-9._:/@-]{1,120}")
SPOT_QUALIFICATIONS = ("QUALIFIED",)
MIN_FUNDING_INTERVAL_S = 60
MAX_FUNDING_INTERVAL_S = 86_400  # same bound as market_stress.metrics.funding
# 2015-01-01 .. 2100-01-01: a timestamp outside is a decoding error, not an observation.
MIN_TIME_MS = 1_420_070_400_000
MAX_TIME_MS = 4_102_444_800_000


class ContractError(ValueError):
    """The observation does not satisfy the input contract. ``code`` is stable."""

    def __init__(self, code, detail=""):
        super().__init__(code if not detail else "%s: %s" % (code, detail))
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class NormalizedObservation:
    observation_key: str
    content_sha256: str
    venue: str
    native_symbol: str
    contract_type: str
    quote_currency: str
    base_currency: str | None
    source_time_ms: int | None
    received_at_ms: int
    capture_id: str | None
    payload_sha256: str | None
    document: dict  # canonical, without received time and collector run


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def parse_utc_ms(value, field):
    """ISO-8601 with an explicit UTC offset, or integer epoch milliseconds."""
    if isinstance(value, bool):
        raise ContractError("INVALID_TIMESTAMP", field)
    if isinstance(value, int):
        ms = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ContractError("INVALID_TIMESTAMP", field) from None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ContractError("TIMESTAMP_WITHOUT_TIMEZONE", field)
        ms = int(parsed.timestamp() * 1000)
    else:
        raise ContractError("INVALID_TIMESTAMP", field)
    if not MIN_TIME_MS <= ms <= MAX_TIME_MS:
        raise ContractError("TIMESTAMP_OUT_OF_RANGE", field)
    return ms


def iso_ms(ms):
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def exact(value, field, *, positive=False, signed=False):
    """Canonical exact decimal string. Floats are refused: they are not exact."""
    if isinstance(value, float):
        raise ContractError("FLOAT_NOT_EXACT", field)
    number = metrics.number(value, positive=positive, signed=signed)
    if number is None:
        raise ContractError("INVALID_DECIMAL", field)
    text = format(number.normalize(), "f")
    return "0" if Decimal(text) == 0 else text


def _token(mapping, field, pattern, code, *, required=True):
    value = mapping.get(field)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ContractError(code, field)
    return value


def _only(mapping, allowed, where):
    extra = sorted(set(mapping) - set(allowed))
    if extra:
        raise ContractError("UNKNOWN_FIELD", "%s.%s" % (where, extra[0]))


def _measure(raw, name):
    """Either {"value": ...} (plus attributes) or {"unavailable": REASON}. Never both, never silent."""
    if not isinstance(raw, dict):
        raise ContractError("MEASURE_MISSING", name)
    if "unavailable" in raw:
        _only(raw, ("unavailable",), name)
        reason = raw["unavailable"]
        if not isinstance(reason, str) or not REASON.fullmatch(reason):
            raise ContractError("INVALID_UNAVAILABLE_REASON", name)
        return {"status": "NOT_AVAILABLE", "reason": reason}
    if "value" not in raw:
        raise ContractError("MEASURE_WITHOUT_VALUE_OR_REASON", name)
    if name in ("mark_price", "index_price"):
        _only(raw, ("value",), name)
        return {"status": "AVAILABLE", "value": exact(raw["value"], name, positive=True)}
    if name == "spot_reference":
        _only(raw, ("value", "qualification", "venue", "native_symbol", "qualification_ref"), name)
        if raw.get("qualification") not in SPOT_QUALIFICATIONS:
            raise ContractError("SPOT_REFERENCE_NOT_QUALIFIED", name)
        return {
            "status": "AVAILABLE", "value": exact(raw["value"], name, positive=True),
            "qualification": raw["qualification"],
            "venue": _token(raw, "venue", VENUE_ID, "INVALID_VENUE_ID"),
            "native_symbol": _token(raw, "native_symbol", NATIVE_SYMBOL, "INVALID_NATIVE_SYMBOL"),
            "qualification_ref": _token(raw, "qualification_ref", TOKEN, "MISSING_QUALIFICATION_REF"),
        }
    if name == "open_interest":
        _only(raw, ("value", "unit", "contract_size_base"), name)
        unit = raw.get("unit")
        if unit not in OI_UNITS:
            raise ContractError("OPEN_INTEREST_UNIT_UNKNOWN", name)
        size = raw.get("contract_size_base")
        if unit == "CONTRACTS":
            if size is None:
                raise ContractError("CONTRACT_SIZE_REQUIRED", name)
            size = exact(size, name + ".contract_size_base", positive=True)
        elif size is not None:
            raise ContractError("CONTRACT_SIZE_ONLY_FOR_CONTRACTS", name)
        return {"status": "AVAILABLE", "value": exact(raw["value"], name), "unit": unit,
                "contract_size_base": size}
    if name == "funding_rate":
        _only(raw, ("value", "interval_s", "interval_attested_by", "next_funding_utc"), name)
        interval = raw.get("interval_s")
        if isinstance(interval, bool) or not isinstance(interval, int) or not (
                MIN_FUNDING_INTERVAL_S <= interval <= MAX_FUNDING_INTERVAL_S):
            raise ContractError("FUNDING_INTERVAL_NOT_ATTESTED", name)
        attested = _token(raw, "interval_attested_by", TOKEN, "FUNDING_INTERVAL_NOT_ATTESTED")
        nxt = raw.get("next_funding_utc")
        return {"status": "AVAILABLE", "value": exact(raw["value"], name, signed=True),
                "interval_s": interval, "interval_attested_by": attested,
                "next_funding_ms": None if nxt is None else parse_utc_ms(nxt, name + ".next_funding_utc")}
    raise ContractError("UNKNOWN_MEASURE", name)  # pragma: no cover


TOP_LEVEL = ("contract_version", "venue", "native_symbol", "contract_type", "quote_currency",
             "base_currency", "source_time_utc", "received_at_utc", "capture_id", "provenance", "measures")
PROVENANCE = ("source", "payload_sha256", "mapping_id", "mapping_sha256", "collector_run_id")


def normalize(raw) -> NormalizedObservation:
    if not isinstance(raw, dict):
        raise ContractError("OBSERVATION_NOT_AN_OBJECT")
    _only(raw, TOP_LEVEL, "observation")
    if raw.get("contract_version") != CONTRACT_VERSION:
        raise ContractError("UNSUPPORTED_CONTRACT_VERSION")
    venue = _token(raw, "venue", VENUE_ID, "INVALID_VENUE_ID")
    native = _token(raw, "native_symbol", NATIVE_SYMBOL, "INVALID_NATIVE_SYMBOL")
    if raw.get("contract_type") not in CONTRACT_TYPES:
        raise ContractError("INVALID_CONTRACT_TYPE")
    contract_type = raw["contract_type"]
    quote = _token(raw, "quote_currency", CURRENCY, "INVALID_QUOTE_CURRENCY")
    base = _token(raw, "base_currency", CURRENCY, "INVALID_BASE_CURRENCY", required=False)
    source_ms = None if raw.get("source_time_utc") is None else parse_utc_ms(raw["source_time_utc"], "source_time_utc")
    if "received_at_utc" not in raw:
        raise ContractError("MISSING_RECEIPT_TIMESTAMP")
    received_ms = parse_utc_ms(raw["received_at_utc"], "received_at_utc")
    capture_id = _token(raw, "capture_id", TOKEN, "INVALID_CAPTURE_ID", required=False)

    prov = raw.get("provenance")
    if not isinstance(prov, dict):
        raise ContractError("MISSING_PROVENANCE")
    _only(prov, PROVENANCE, "provenance")
    source = _token(prov, "source", TOKEN, "MISSING_PROVENANCE_SOURCE")
    payload = _token(prov, "payload_sha256", SHA256, "INVALID_PAYLOAD_SHA256", required=False)
    mapping_id = _token(prov, "mapping_id", TOKEN, "INVALID_MAPPING_ID", required=False)
    mapping_sha = _token(prov, "mapping_sha256", SHA256, "INVALID_MAPPING_SHA256", required=False)
    if (mapping_id is None) != (mapping_sha is None):
        raise ContractError("MAPPING_ID_AND_HASH_GO_TOGETHER")
    run_id = _token(prov, "collector_run_id", TOKEN, "INVALID_COLLECTOR_RUN_ID", required=False)
    if source_ms is None and payload is None:
        # Without a source time, the payload digest is the only stable identity.
        raise ContractError("IDENTITY_UNRESOLVED", "source_time_utc or provenance.payload_sha256 required")

    measures_raw = raw.get("measures")
    if not isinstance(measures_raw, dict):
        raise ContractError("MISSING_MEASURES")
    _only(measures_raw, MEASURES, "measures")
    measures = {name: _measure(measures_raw.get(name), name) for name in MEASURES}

    identity = {"venue": venue, "native_symbol": native, "contract_type": contract_type,
                "quote_currency": quote}
    if source_ms is not None:
        identity["source_time_ms"] = source_ms
    else:
        identity.update(source_time_ms=None, payload_sha256=payload, capture_id=capture_id)
    key = digest(identity)
    document = {
        "contract_version": CONTRACT_VERSION, **identity, "base_currency": base,
        "source_time_ms": source_ms, "capture_id": capture_id,
        "provenance": {"source": source, "payload_sha256": payload,
                       "mapping_id": mapping_id, "mapping_sha256": mapping_sha},
        "measures": measures,
    }
    content = digest(document)
    return NormalizedObservation(key, content, venue, native, contract_type, quote, base, source_ms,
                                 received_ms, capture_id, payload, {**document, "collector_run_id": run_id})

