"""CH1-01 closed event-perception contract V1: records, quality vocabulary, state mapping.

Source of truth for the rules: ``docs/contracts/MARKET_PERCEPTION_CH1_01.md``.
SOURCE ONLY / NOT WIRED. Nothing here reads a clock, a file or the network, and
nothing replays a journal: the replay, the Flux reader link, the UI and any
collection belong to later lots. The Flux V1 contract and the internal values of
its states (``l2.py`` and ``radar_composite/bbo_book.py``) are left unchanged;
this module only *projects* them, keeping the native code and reason attached.

Checking form is not certifying data: a record that passes says nothing about
whether the market really looked like that.
"""

from decimal import Decimal, InvalidOperation
import json
import re

SCHEMA_VERSION = "1"
MAX_DOCUMENT_BYTES = 4_000_000

VERIFIED, DEGRADED, RESYNCING, INVALID = "VERIFIED", "DEGRADED", "RESYNCING", "INVALID"
UNKNOWN, NOT_AVAILABLE, UNRESOLVED = "UNKNOWN", "NOT_AVAILABLE", "UNRESOLVED"
QUALITY_STATES = frozenset({VERIFIED, DEGRADED, RESYNCING, INVALID, UNKNOWN, NOT_AVAILABLE, UNRESOLVED})
EVIDENCE_KINDS = frozenset({"SYNTHETIC", "HISTORICAL"})
QUALITY_DIMENSIONS = ("book_integrity", "book_freshness", "trade_coverage", "event_time_quality")
AGGRESSOR_SIDES = frozenset({"BUY", "SELL", "UNKNOWN"})
SIDE_BASES = frozenset({"TAKER", "MAKER_INVERTED", "UNKNOWN"})
DEPTH_OPERATIONS = frozenset({"SNAPSHOT", "UPDATE"})

RECORD_KEYS = {
    "RAW_EVENT": frozenset({
        "schema_version", "session_id", "venue", "market_type", "native_symbol", "channel", "kind",
        "receipt_seq", "receive_utc_ns", "receive_mono_ns", "native_time", "native_sequence",
        "offset_bytes", "length_bytes", "payload_sha256",
    }),
    "NORMALIZED_TRADE": frozenset({
        "schema_version", "receipt_seq", "item_index", "trade_id", "price", "quantity",
        "aggressor_side", "side_basis",
    }),
    "DEPTH_UPDATE": frozenset({
        "schema_version", "receipt_seq", "item_index", "operation", "bids", "asks", "checksum",
        "native_sequence",
    }),
    "BOOK_STATE": frozenset({
        "schema_version", "as_of_receipt_seq", "last_book_receipt_seq", "subscribed_depth", "bids",
        "asks", "native_state", "native_reason",
    }),
    "QUALITY_REPORT": frozenset({
        "schema_version", "as_of_receipt_seq", "evidence_kind", *QUALITY_DIMENSIONS,
    }),
}
QUALITY_RESULT_KEYS = frozenset({"state", "reason", "evidence_receipt_seq"})

_A = re.ASCII
_UINT = re.compile(r"(0|[1-9][0-9]{0,29})", _A)  # non-negative integer as a string
_DEC = re.compile(r"[0-9]{1,30}(\.[0-9]{1,30})?", _A)  # finite decimal, no sign, no exponent
_CODE = re.compile(r"[A-Z][A-Z0-9_\-]{0,63}", _A)
_HEX64 = re.compile(r"[0-9a-f]{64}", _A)
_TEXT_MAX = 256
_ASSET = re.compile(r"[A-Z0-9]{1,16}", _A)
_ADMITTED_KRAKEN_MANIFESTS = {
    "BBO-BTC-20261120T070632Z": "9ee3185daaf05faf646686466d6faf18374ba54ade5ae30a1bf883b3f58da910",
}


class PerceptionRefusal(ValueError):
    """Stable refusal reason code (the message is the code, optionally ``CODE:path``)."""


def _refuse(code, path):
    raise PerceptionRefusal(f"{code}:{path}")


def validate_kraken_spot_identity(venue, market_type, symbol, base, quote, *, unit_declarations=()):
    """Return the units established by a coherent Kraken Spot instrument."""
    if (venue != "kraken" or market_type != "SPOT"
            or any(type(asset) is not str or not _ASSET.fullmatch(asset) for asset in (base, quote))
            or base == quote or symbol != f"{base}/{quote}"):
        raise PerceptionRefusal("KRAKEN_SPOT_IDENTITY_MISMATCH")
    expected_units = {"quantity_unit": base, "price_quote_unit": quote, "price_unit": f"{quote}/{base}"}
    for scope, fields in unit_declarations:
        for name, value in fields.items():
            if "unit" not in name.casefold():
                continue
            if name not in expected_units:
                _refuse("KRAKEN_UNIT_FIELD_UNKNOWN", f"{scope}.{name}")
            if type(value) is not str or not re.fullmatch(r"[A-Z0-9]{1,16}(?:/[A-Z0-9]{1,16})?", value, _A):
                _refuse("KRAKEN_UNIT_MALFORMED", f"{scope}.{name}")
            if value != expected_units[name]:
                _refuse("KRAKEN_UNIT_MISMATCH", f"{scope}.{name}")
    return {"quantity_unit": base, "price_quote_unit": quote}


def require_admitted_kraken_manifest(corpus_id, manifest_sha256):
    """Check the documented admission reference independently of CLI arguments."""
    expected = _ADMITTED_KRAKEN_MANIFESTS.get(corpus_id)
    if expected is None or manifest_sha256 != expected:
        raise PerceptionRefusal("HISTORICAL_MANIFEST_NOT_ADMITTED")


# ------------------------------------------------------------------ strict JSON


def strict_loads(raw):
    """Parse one JSON document: duplicate keys, fractional numbers and NaN/Infinity are refused."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_DOCUMENT_BYTES:
        raise PerceptionRefusal("BOUNDED_BYTES_REQUIRED")

    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise PerceptionRefusal("DUPLICATE_KEY")
            out[key] = value
        return out

    def no_constant(_):
        raise PerceptionRefusal("NONFINITE_JSON")

    def no_fraction(_):
        raise PerceptionRefusal("JSON_NUMBER_FRACTION_REFUSED")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=no_constant, parse_float=no_fraction)
    except PerceptionRefusal:
        raise
    except (UnicodeError, ValueError, RecursionError):
        raise PerceptionRefusal("INVALID_JSON") from None


# ------------------------------------------------------------------ field rules


def _closed(doc, keys, path):
    if type(doc) is not dict:
        _refuse("OBJECT_REQUIRED", path)
    missing, unknown = keys - doc.keys(), doc.keys() - keys
    if missing:
        _refuse("MISSING_KEY", f"{path}.{sorted(missing)[0]}")
    if unknown:
        _refuse("UNKNOWN_KEY", f"{path}.{sorted(unknown)[0]}")


def _uint(value, path, *, nullable=False, positive=False):
    if value is None and nullable:
        return None
    if type(value) is not str or not _UINT.fullmatch(value):
        _refuse("UNSIGNED_INTEGER_STRING_REQUIRED", path)
    number = int(value)
    if positive and number == 0:
        _refuse("POSITIVE_REQUIRED", path)
    return number


def _decimal(value, path, *, zero_ok):
    if type(value) is not str or not _DEC.fullmatch(value):
        _refuse("DECIMAL_STRING_REQUIRED", path)
    try:
        number = Decimal(value)
    except InvalidOperation:  # pragma: no cover - the grammar already excludes it
        _refuse("DECIMAL_STRING_REQUIRED", path)
    if number == 0 and not zero_ok:
        _refuse("POSITIVE_REQUIRED", path)
    return number


def _text(value, path, *, nullable=False):
    if value is None and nullable:
        return None
    if type(value) is not str or not value or len(value) > _TEXT_MAX or not value.isprintable():
        _refuse("TEXT_REQUIRED", path)
    return value


def _code(value, path, *, nullable=False):
    if value is None and nullable:
        return None
    if type(value) is not str or not _CODE.fullmatch(value):
        _refuse("CODE_REQUIRED", path)
    return value


def _member(value, allowed, path):
    if type(value) is not str or value not in allowed:
        _refuse("VALUE_NOT_ALLOWED", path)
    return value


def _version(doc, path):
    if doc["schema_version"] != SCHEMA_VERSION:
        _refuse("SCHEMA_VERSION_REFUSED", f"{path}.schema_version")


def _levels(value, path, *, zero_ok):
    """A side: a list of [price, quantity] pairs of decimal strings."""
    if type(value) is not list:
        _refuse("LIST_REQUIRED", path)
    out = []
    for i, level in enumerate(value):
        where = f"{path}[{i}]"
        if type(level) is not list or len(level) != 2:
            _refuse("LEVEL_PAIR_REQUIRED", where)
        out.append((_decimal(level[0], where + "[0]", zero_ok=False),
                    _decimal(level[1], where + "[1]", zero_ok=zero_ok)))
    return out


# ------------------------------------------------------------------ records


def validate_raw_event(doc, path="$"):
    _closed(doc, RECORD_KEYS["RAW_EVENT"], path)
    _version(doc, path)
    for key in ("session_id", "venue", "market_type", "native_symbol", "kind"):
        _text(doc[key], f"{path}.{key}")
    _text(doc["channel"], f"{path}.channel", nullable=True)
    for key in ("receipt_seq", "receive_utc_ns", "receive_mono_ns", "offset_bytes", "length_bytes"):
        _uint(doc[key], f"{path}.{key}")
    _uint(doc["native_sequence"], f"{path}.native_sequence", nullable=True)
    native_time = doc["native_time"]  # original form: a string or an integer, never converted
    if native_time is not None and type(native_time) is not int and type(native_time) is not str:
        _refuse("NATIVE_TIME_ORIGINAL_FORM_REQUIRED", f"{path}.native_time")
    if type(doc["payload_sha256"]) is not str or not _HEX64.fullmatch(doc["payload_sha256"]):
        _refuse("SHA256_HEX_REQUIRED", f"{path}.payload_sha256")
    return doc


def validate_normalized_trade(doc, path="$"):
    _closed(doc, RECORD_KEYS["NORMALIZED_TRADE"], path)
    _version(doc, path)
    _uint(doc["receipt_seq"], f"{path}.receipt_seq")
    _uint(doc["item_index"], f"{path}.item_index")
    _text(doc["trade_id"], f"{path}.trade_id", nullable=True)
    _decimal(doc["price"], f"{path}.price", zero_ok=False)
    _decimal(doc["quantity"], f"{path}.quantity", zero_ok=False)
    side = _member(doc["aggressor_side"], AGGRESSOR_SIDES, f"{path}.aggressor_side")
    basis = _member(doc["side_basis"], SIDE_BASES, f"{path}.side_basis")
    if (side == "UNKNOWN") != (basis == "UNKNOWN"):
        _refuse("AGGRESSOR_BASIS_INCONSISTENT", path)
    return doc


def validate_depth_update(doc, path="$"):
    _closed(doc, RECORD_KEYS["DEPTH_UPDATE"], path)
    _version(doc, path)
    _uint(doc["receipt_seq"], f"{path}.receipt_seq")
    _uint(doc["item_index"], f"{path}.item_index")
    _member(doc["operation"], DEPTH_OPERATIONS, f"{path}.operation")
    _levels(doc["bids"], f"{path}.bids", zero_ok=True)
    _levels(doc["asks"], f"{path}.asks", zero_ok=True)
    _uint(doc["checksum"], f"{path}.checksum", nullable=True)
    _uint(doc["native_sequence"], f"{path}.native_sequence", nullable=True)
    return doc


def validate_book_state(doc, path="$"):
    _closed(doc, RECORD_KEYS["BOOK_STATE"], path)
    _version(doc, path)
    as_of = _uint(doc["as_of_receipt_seq"], f"{path}.as_of_receipt_seq")
    last = _uint(doc["last_book_receipt_seq"], f"{path}.last_book_receipt_seq", nullable=True)
    if last is not None and last > as_of:
        _refuse("RECEIPT_AFTER_AS_OF", f"{path}.last_book_receipt_seq")
    depth = _uint(doc["subscribed_depth"], f"{path}.subscribed_depth", positive=True)
    _code(doc["native_state"], f"{path}.native_state")
    _code(doc["native_reason"], f"{path}.native_reason", nullable=True)
    bids, asks = doc["bids"], doc["asks"]
    if (bids is None) != (asks is None):
        _refuse("BOOK_SIDES_NULL_TOGETHER", path)
    if doc["native_state"] in ("VALID", "UNCHANGED_VERIFIED") and (not bids or not asks or not last):
        _refuse("VERIFIED_BOOK_REQUIRES_SIDES_AND_RECEIPT", path)
    if bids is None:
        return doc
    # A zero size removes a level, so a published book never shows one.
    sides = {"bids": _levels(bids, f"{path}.bids", zero_ok=False),
             "asks": _levels(asks, f"{path}.asks", zero_ok=False)}
    for name, levels in sides.items():
        if len(levels) > depth:
            _refuse("DEPTH_EXCEEDED", f"{path}.{name}")
        prices = [p for p, _ in levels]
        ordered = sorted(set(prices), reverse=(name == "bids"))
        if prices != ordered:
            _refuse("SIDE_NOT_STRICTLY_SORTED", f"{path}.{name}")
    if sides["bids"] and sides["asks"] and sides["bids"][0][0] >= sides["asks"][0][0]:
        _refuse("CROSSED_OR_LOCKED_BOOK", path)
    return doc


def validate_quality_result(doc, path="$", *, as_of=None):
    _closed(doc, QUALITY_RESULT_KEYS, path)
    state = _member(doc["state"], QUALITY_STATES, f"{path}.state")
    reason = _code(doc["reason"], f"{path}.reason", nullable=True)
    if state != VERIFIED and reason is None:
        _refuse("REASON_REQUIRED", f"{path}.reason")
    seq = _uint(doc["evidence_receipt_seq"], f"{path}.evidence_receipt_seq", nullable=True)
    if seq is not None and as_of is not None and seq > as_of:
        _refuse("RECEIPT_AFTER_AS_OF", f"{path}.evidence_receipt_seq")
    return doc


def validate_quality_report(doc, path="$"):
    _closed(doc, RECORD_KEYS["QUALITY_REPORT"], path)
    _version(doc, path)
    as_of = _uint(doc["as_of_receipt_seq"], f"{path}.as_of_receipt_seq")
    _member(doc["evidence_kind"], EVIDENCE_KINDS, f"{path}.evidence_kind")
    for dimension in QUALITY_DIMENSIONS:
        validate_quality_result(doc[dimension], f"{path}.{dimension}", as_of=as_of)
    return doc


VALIDATORS = {
    "RAW_EVENT": validate_raw_event,
    "NORMALIZED_TRADE": validate_normalized_trade,
    "DEPTH_UPDATE": validate_depth_update,
    "BOOK_STATE": validate_book_state,
    "QUALITY_REPORT": validate_quality_report,
}


def validate_record(record_type, doc):
    """Validate one record of a declared type; an undeclared type is refused."""
    if record_type not in VALIDATORS:
        raise PerceptionRefusal("RECORD_TYPE_REFUSED")
    return VALIDATORS[record_type](doc)


# ------------------------------------------------------------------ state mapping

BBO_NATIVE_STATES = frozenset({
    "VALID", "UNCHANGED_VERIFIED", "FRESHNESS_UNKNOWN", "CONTINUITY_LOST", "BOOK_INVALID",
    "NOT_INITIALIZED", "SOURCE_UNAVAILABLE",
})
FLUX_L2_NATIVE_STATES = frozenset({"NO_SNAPSHOT", "INVALID", "LIVE"})
ORIGINS = {"BBO": BBO_NATIVE_STATES, "FLUX_L2": FLUX_L2_NATIVE_STATES}


def quality_result(state, reason=None, evidence_receipt_seq=None):
    doc = {"state": state, "reason": reason, "evidence_receipt_seq": evidence_receipt_seq}
    return validate_quality_result(doc)


def project_native_state(origin, native_state, native_reason=None, *, evidence_receipt_seq=None,
                         resync_engaged=False, snapshot_expected=False,
                         reconstruction_integrity=None):
    """Project one native book state onto the quality dimensions it informs.

    Returns ``{"origin", "native_state", "native_reason", "projections"}``: the native
    code and reason stay attached, and only the dimensions the contract assigns to this
    state appear in ``projections`` (a missing dimension is not asserted either way).

    - ``resync_engaged``: a recovery has explicitly started (CONTINUITY_LOST -> RESYNCING).
    - ``snapshot_expected``: a snapshot is explicitly awaited (NOT_INITIALIZED / NO_SNAPSHOT
      -> RESYNCING instead of NOT_AVAILABLE).
    - ``reconstruction_integrity``: the integrity established, at the bound, by admissible
      reconstruction evidence; consulted for BBO FRESHNESS_UNKNOWN and Flux L2 LIVE only.
      Absent, those states never reach VERIFIED: integrity stays UNKNOWN with a reason.
    """
    if origin not in ORIGINS:
        raise PerceptionRefusal("ORIGIN_REFUSED")
    if native_state not in ORIGINS[origin]:
        raise PerceptionRefusal("NATIVE_STATE_REFUSED")
    if native_reason is not None and (type(native_reason) is not str or not native_reason):
        raise PerceptionRefusal("NATIVE_REASON_REFUSED")
    if reconstruction_integrity is not None and reconstruction_integrity not in QUALITY_STATES:
        raise PerceptionRefusal("RECONSTRUCTION_INTEGRITY_REFUSED")
    if type(resync_engaged) is not bool or type(snapshot_expected) is not bool:
        raise PerceptionRefusal("FLAG_REFUSED")
    if evidence_receipt_seq is not None:
        _uint(evidence_receipt_seq, "evidence_receipt_seq")

    def result(state, reason):
        return quality_result(state, None if state == VERIFIED else reason, evidence_receipt_seq)

    native_code = native_state  # the fallback reason when the native one is absent or free text
    reason = native_reason if native_reason is not None and _CODE.fullmatch(native_reason) else native_code
    awaiting = RESYNCING if snapshot_expected else NOT_AVAILABLE

    def integrity_from_evidence(missing_reason):
        if reconstruction_integrity is None:
            return result(UNKNOWN, missing_reason)
        return result(reconstruction_integrity, reason)

    if origin == "BBO":
        if native_state in ("VALID", "UNCHANGED_VERIFIED"):
            projections = {"book_integrity": result(VERIFIED, None)}
        elif native_state == "FRESHNESS_UNKNOWN":
            projections = {"book_integrity": integrity_from_evidence("RECONSTRUCTION_EVIDENCE_NOT_SUPPLIED"),
                           "book_freshness": result(UNKNOWN, reason)}
        elif native_state == "CONTINUITY_LOST":
            projections = {"book_integrity": result(RESYNCING if resync_engaged else INVALID, reason)}
        elif native_state == "BOOK_INVALID":
            projections = {"book_integrity": result(INVALID, reason)}
        elif native_state == "NOT_INITIALIZED":
            projections = {"book_integrity": result(awaiting, reason)}
        else:  # SOURCE_UNAVAILABLE: carried as the reason on every book dimension it affects
            projections = {"book_integrity": result(NOT_AVAILABLE, reason),
                           "book_freshness": result(NOT_AVAILABLE, reason)}
    else:
        if native_state == "NO_SNAPSHOT":
            projections = {"book_integrity": result(awaiting, reason)}
        elif native_state == "INVALID":
            projections = {"book_integrity": result(INVALID, reason)}
        else:  # LIVE: a candidate only; the native state proves neither freshness nor real time
            projections = {"book_integrity": integrity_from_evidence("RECONSTRUCTION_EVIDENCE_NOT_ADMITTED")}
    return {"origin": origin, "native_state": native_state, "native_reason": native_reason,
            "projections": projections}
