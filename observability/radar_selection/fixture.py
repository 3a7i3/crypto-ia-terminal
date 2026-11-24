"""Bounded, strict loading of a ``radar-fixture/1.0.0`` document.

Structural problems refuse the whole input with a stable code (malformed or
excessive input is never half-read). Semantic problems inside well-formed data
(missing timestamp, crossed book, contradictory identity...) are *data*: they
are kept and qualified market by market by the evaluation.
"""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal

from . import contract as c

CATALOGUE_DOCUMENTS = ("mexc_spot_exchange_info", "mexc_contract_detail", "kraken_asset_pairs",
                       "kraken_assets", "kraken_futures_instruments")
SCANNER_MARKETS = ("MEXC_SPOT", "MEXC_PERPETUAL", "KRAKEN_SPOT", "KRAKEN_PERPETUAL")
TOP_KEYS = {"fixture_schema", "dataset_id", "description", "evidence_kind", "evaluation_time_ms",
            "policy", "catalogues", "source_access", "previous_universe", "observations"}
POLICY_KEYS = {"venues", "market_types", "quotes", "asset_classes", "deny"}
OBS_KEYS = {"venue", "market_type", "native_symbol", "declared_base", "declared_quote",
            "evidence_ref", "price_kind", "window", "samples", "activity", "l2", "cost"}
WINDOW_KEYS = {"start_ms", "step_ms", "points"}
SAMPLE_KEYS = {"t_ms", "price", "bid", "ask"}
ACTIVITY_KEYS = {"kind", "value", "evidence_ref"}
L2_KEYS = {"status", "evidence_ref", "depth_levels", "depth_quote_10bps"}
COST_KEYS = {"basis", "provenance", "network_kib_s", "cpu_pct", "memory_mib", "storage_mib_h",
             "connections", "rate_limit_note"}
PREVIOUS_KEYS = {"market_id", "native_symbol", "contract_type", "settlement_asset"}
_DEC = re.compile(r"[0-9]{1,30}(\.[0-9]{1,30})?", re.ASCII)
_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}", re.ASCII)
_ID = re.compile(r"[A-Za-z0-9:/_.?~\-]{1,80}", re.ASCII)
_TEXT = 240
MAX_MS = 2**53 - 1


class RadarRefusal(ValueError):
    """Stable refusal code (message = ``CODE`` or ``CODE:path``)."""

    @property
    def code(self) -> str:
        return str(self).split(":", 1)[0]


def _refuse(code: str, path: str = "") -> None:
    raise RadarRefusal(f"{code}:{path}" if path else code)


def strict_loads(raw: bytes, limit: int):
    """Bounded UTF-8 JSON: duplicate keys, floats and NaN/Infinity are refused."""
    if not isinstance(raw, (bytes, bytearray)):
        _refuse("INPUT_NOT_BYTES")
    if len(raw) == 0:
        _refuse("INPUT_EMPTY")
    if len(raw) > limit:
        _refuse("INPUT_TOO_LARGE", f"{len(raw)}>{limit}")

    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                _refuse("DUPLICATE_KEY", key)
            out[key] = value
        return out

    def no_float(text):
        _refuse("FLOAT_NOT_ALLOWED", text[:20])

    def no_constant(text):
        _refuse("NONFINITE_NUMBER", text)

    try:
        return json.loads(bytes(raw).decode("utf-8"), object_pairs_hook=pairs,
                          parse_float=no_float, parse_constant=no_constant)
    except RadarRefusal:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        _refuse("INPUT_MALFORMED", type(exc).__name__)


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _int(v, path, lo=0, hi=MAX_MS):
    if type(v) is not int or not lo <= v <= hi:
        _refuse("INTEGER_EXPECTED", path)
    return v


def _opt_int(v, path, lo=0, hi=MAX_MS):
    return None if v is None else _int(v, path, lo, hi)


def _dec(v, path, nullable=True):
    if v is None and nullable:
        return None
    if not isinstance(v, str) or not _DEC.fullmatch(v):
        _refuse("DECIMAL_STRING_EXPECTED", path)
    return v


def _text(v, path, nullable=True):
    if v is None and nullable:
        return None
    if not isinstance(v, str) or not 0 < len(v) <= _TEXT or not v.isprintable():
        _refuse("TEXT_EXPECTED", path)
    return v


def _keys(obj, keys, path):
    if not isinstance(obj, dict):
        _refuse("OBJECT_EXPECTED", path)
    if set(obj) != keys:
        _refuse("KEYS_MISMATCH", path)


def _str_list(v, path, allowed=None):
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v) or len(v) > 200:
        _refuse("STRING_LIST_EXPECTED", path)
    if allowed is not None and any(x not in allowed for x in v):
        _refuse("VALUE_NOT_ALLOWED", path)
    if len(set(v)) != len(v):
        _refuse("DUPLICATE_VALUE", path)
    return v


def _check_catalogue_body(value, path, depth=0):
    """Catalogue bodies keep the official public shapes; only JSON scalars without floats."""
    if depth > 8:
        _refuse("CATALOGUE_TOO_DEEP", path)
    if isinstance(value, dict):
        for k, v in value.items():
            _check_catalogue_body(v, path, depth + 1)
    elif isinstance(value, list):
        for v in value:
            _check_catalogue_body(v, path, depth + 1)
    elif not (value is None or isinstance(value, (str, bool, int))):
        _refuse("CATALOGUE_VALUE", path)


def _observation(o, i, budgets):
    path = f"observations[{i}]"
    _keys(o, OBS_KEYS, path)
    if len(canonical(o)) > budgets.max_observation_bytes:
        _refuse("OBSERVATION_TOO_LARGE", path)
    if o["venue"] not in c.VENUES:
        _refuse("VALUE_NOT_ALLOWED", path + ".venue")
    if o["market_type"] not in c.MARKET_TYPES:
        _refuse("VALUE_NOT_ALLOWED", path + ".market_type")
    _text(o["native_symbol"], path + ".native_symbol", nullable=False)
    for k in ("declared_base", "declared_quote"):
        _text(o[k], f"{path}.{k}")
    _text(o["evidence_ref"], path + ".evidence_ref", nullable=False)
    if o["price_kind"] not in c.PRICE_KINDS:
        _refuse("VALUE_NOT_ALLOWED", path + ".price_kind")
    w = o["window"]
    _keys(w, WINDOW_KEYS, path + ".window")
    _int(w["start_ms"], path + ".window.start_ms", 1)
    _int(w["step_ms"], path + ".window.step_ms", 1, 86_400_000)
    _int(w["points"], path + ".window.points", 2, budgets.max_samples_per_observation)
    samples = o["samples"]
    if not isinstance(samples, list) or len(samples) > budgets.max_samples_per_observation:
        _refuse("SAMPLES_BOUND", path + ".samples")
    for j, s in enumerate(samples):
        sp = f"{path}.samples[{j}]"
        _keys(s, SAMPLE_KEYS, sp)
        _opt_int(s["t_ms"], sp + ".t_ms")
        for k in ("price", "bid", "ask"):
            _dec(s[k], f"{sp}.{k}")
    a = o["activity"]
    if a is not None:
        _keys(a, ACTIVITY_KEYS, path + ".activity")
        _text(a["kind"], path + ".activity.kind", nullable=False)
        _opt_int(a["value"], path + ".activity.value")
        _text(a["evidence_ref"], path + ".activity.evidence_ref")
    l2 = o["l2"]
    if l2 is not None:
        _keys(l2, L2_KEYS, path + ".l2")
        if l2["status"] not in c.L2_STATUSES:
            _refuse("VALUE_NOT_ALLOWED", path + ".l2.status")
        _text(l2["evidence_ref"], path + ".l2.evidence_ref")
        _opt_int(l2["depth_levels"], path + ".l2.depth_levels", 1, 10_000)
        d = l2["depth_quote_10bps"]
        if d is not None:
            _keys(d, {"bid", "ask"}, path + ".l2.depth_quote_10bps")
            _dec(d["bid"], path + ".l2.depth_quote_10bps.bid")
            _dec(d["ask"], path + ".l2.depth_quote_10bps.ask")
    cost = o["cost"]
    if cost is not None:
        _keys(cost, COST_KEYS, path + ".cost")
        if cost["basis"] not in c.COST_BASES:
            _refuse("VALUE_NOT_ALLOWED", path + ".cost.basis")
        _text(cost["provenance"], path + ".cost.provenance", nullable=False)
        for k in ("network_kib_s", "cpu_pct", "memory_mib", "storage_mib_h"):
            _dec(cost[k], f"{path}.cost.{k}")
        _opt_int(cost["connections"], path + ".cost.connections", 0, 1000)
        _text(cost["rate_limit_note"], path + ".cost.rate_limit_note")


def load_fixture(raw: bytes, budgets: c.Budgets = c.TEST_BUDGETS) -> dict:
    """Validate a fixture and return it with its digest. Pure, no I/O."""
    doc = strict_loads(raw, budgets.max_input_bytes)
    _keys(doc, TOP_KEYS, "$")
    if doc["fixture_schema"] != c.FIXTURE_SCHEMA:
        _refuse("FIXTURE_SCHEMA", str(doc["fixture_schema"])[:40])
    if doc["evidence_kind"] not in c.EVIDENCE_KINDS:
        _refuse("EVIDENCE_KIND_NOT_ALLOWED_IN_R0", str(doc["evidence_kind"])[:40])
    if not isinstance(doc["dataset_id"], str) or not _ID.fullmatch(doc["dataset_id"]):
        _refuse("DATASET_ID", "$.dataset_id")
    _text(doc["description"], "$.description", nullable=False)
    _int(doc["evaluation_time_ms"], "$.evaluation_time_ms", 1)
    p = doc["policy"]
    _keys(p, POLICY_KEYS, "$.policy")
    _str_list(p["venues"], "$.policy.venues", c.VENUES)
    _str_list(p["market_types"], "$.policy.market_types", c.MARKET_TYPES)
    _str_list(p["quotes"], "$.policy.quotes")
    _str_list(p["asset_classes"], "$.policy.asset_classes", ("CRYPTO", "STABLECOIN", "FIAT"))
    _str_list(p["deny"], "$.policy.deny")
    cats = doc["catalogues"]
    _keys(cats, set(CATALOGUE_DOCUMENTS), "$.catalogues")
    for name in CATALOGUE_DOCUMENTS:
        entry = cats[name]
        _keys(entry, {"received_ms", "error", "body"}, f"$.catalogues.{name}")
        _opt_int(entry["received_ms"], f"$.catalogues.{name}.received_ms", 1)
        if entry["error"] is not None and (not isinstance(entry["error"], str) or not _CODE.fullmatch(entry["error"])):
            _refuse("ERROR_CODE", f"$.catalogues.{name}.error")
        if (entry["body"] is None) == (entry["error"] is None):
            _refuse("BODY_XOR_ERROR", f"$.catalogues.{name}")
        _check_catalogue_body(entry["body"], f"$.catalogues.{name}.body")
    access = doc["source_access"]
    if not isinstance(access, dict) or not set(access) <= set(SCANNER_MARKETS):
        _refuse("SOURCE_ACCESS", "$.source_access")
    for m, a in access.items():
        _keys(a, {"state", "reason"}, f"$.source_access.{m}")
        if a["state"] not in c.SOURCE_ACCESS[:3]:
            _refuse("VALUE_NOT_ALLOWED", f"$.source_access.{m}.state")
        if a["reason"] is not None and not _CODE.fullmatch(str(a["reason"])):
            _refuse("ERROR_CODE", f"$.source_access.{m}.reason")
    prev = doc["previous_universe"]
    if prev is not None:
        if not isinstance(prev, list) or len(prev) > c.MAX_FIXTURE_RECORDS:
            _refuse("PREVIOUS_UNIVERSE", "$.previous_universe")
        for i, e in enumerate(prev):
            _keys(e, PREVIOUS_KEYS, f"$.previous_universe[{i}]")
            if not isinstance(e["market_id"], str) or not _ID.fullmatch(e["market_id"]):
                _refuse("MARKET_ID", f"$.previous_universe[{i}].market_id")
            for k in ("native_symbol", "contract_type", "settlement_asset"):
                _text(e[k], f"$.previous_universe[{i}].{k}")
    obs = doc["observations"]
    if not isinstance(obs, list) or len(obs) > c.MAX_FIXTURE_RECORDS:
        _refuse("OBSERVATIONS_BOUND", "$.observations")
    for i, o in enumerate(obs):
        _observation(o, i, budgets)
    return {"doc": doc, "sha256": sha256_hex(bytes(raw)), "bytes": len(raw)}


def catalogue_documents(doc: dict) -> dict:
    """Fixture catalogues -> the ``parse_all`` input of scanner_universe (raw bytes)."""
    out = {}
    for name in CATALOGUE_DOCUMENTS:
        e = doc["catalogues"][name]
        raw = None if e["body"] is None else canonical(e["body"])
        out[name] = {"raw": raw, "received_ms": e["received_ms"], "error": e["error"]}
    return out


def decimal(v: str | None) -> Decimal | None:
    return None if v is None else Decimal(v)
