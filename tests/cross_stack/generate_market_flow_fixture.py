"""CryptoRadar Flux (lot 3A): REAL offline chain -> corpus for the TypeScript contract.

    synthetic_session -> artifact.replay -> temporary file -> MarketFlowReader
        -> FastAPI TestClient GET -> raw bytes -> frontend reader / validator / client

Nothing is written by hand as a "positive" answer: every native case below is
produced by the real replay and served by the real reader and route. Groups:

* ``native``              replay outputs, really served (HTTP 200).
* ``derived_variant``     contract variants derived from a native artifact (HISTORICAL, book
                          freshness classifications). Labelled as variants: they are NOT native
                          replay outputs and NOT historical evidence. Python verdicts recorded.
* ``artifact_corruption`` corrupted artifact bytes/files really pushed through reader + route
                          (HTTP 503 with the native ``error_code``).
* ``response_mutation``   mutations of a real HTTP 200 body (raw bytes) that the frontend must
                          refuse, or equivalent spellings it must accept; Python verdicts recorded.
* ``http_error``          native 503 / 404 bodies.

Mutation corpora (``mutations/*.json``) are compact specs applied by both stacks to a native
artifact; every spec carries the verdict of the Python oracle (``validate_artifact``).

Fixture hashes are test controls, not admission of real data. Every path is temporary and
synthetic; no network, no VPS, no provider. The reader API global is restored after every use.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import tempfile
import unicodedata
from pathlib import Path

from fastapi.testclient import TestClient

from observability.market_flow import CALC_VERSION, CONTRACT_VERSION, contract, l2
from observability.market_flow import fixtures as fx
from observability.market_flow import trades as tr
from observability.market_flow.artifact import TOP_KEYS, canonical, replay, validate_artifact
from observability.operator_api import app as api
from observability.operator_api.market_flow_reader import MAX_BYTES

URL = "/api/operator/v1/market-flow"
S = fx.S
SERVING_TAIL = re.compile(rb',"serving":\{"freshness_classification":"NOT_ASSESSED_[A-Z]+"\}\}\Z')
CORPUS_DIR = "F_flux_corpus"

# Values substituted at every node of a native artifact by the mutation corpus.
SET_VALUES = [None, True, False, 0, 1, -1, 2**53 - 1, 2**53, "", "x", "0", "-1", "00", "1.5", "1e5", "NaN",
              "٣", " 1", "1\n", [], {}, ["0", "0"]]


# --------------------------------------------------------------------------- helpers

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dumps(obj) -> str:
    """Deterministic, ASCII-only JSON (lone surrogates survive as \\udXXX escapes)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def serve(raw: bytes, workdir: Path, name: str):
    """File bytes -> real reader -> real route. Returns (status, raw response bytes)."""
    path = workdir / (name + ".json")
    path.write_bytes(raw)
    previous = api._market_flow_reader
    try:
        api.configure_market_flow_reader(str(path))
        with TestClient(api.app) as client:
            response = client.get(URL)
        return response.status_code, response.content
    finally:
        api._market_flow_reader = previous  # restore the exact previous reader object


def parse_strict(raw: bytes):
    """The Python side of the strict reading (the reader's own hooks)."""
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError("duplicate field")
            out[k] = v
        return out

    def constant(_):
        raise ValueError("nonfinite")

    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)


def oracle(doc):
    """Verdict of the Python oracle for one artifact value."""
    try:
        validate_artifact(doc)
        return {"valid": True, "error": None}
    except Exception as exc:  # any failure of the oracle is a refusal (the reader refuses the same)
        return {"valid": False, "error": "%s:%s" % (type(exc).__name__, exc)}


def publication_verdict(raw: bytes):
    """Python verdict for a whole HTTP 200 body: strict parse, closed keys, serving, oracle."""
    try:
        doc = parse_strict(raw)
    except (ValueError, UnicodeError, RecursionError) as exc:
        return {"valid": False, "error": "PARSE:%s" % type(exc).__name__}
    if not isinstance(doc, dict) or set(doc) != TOP_KEYS | {"serving"}:
        return {"valid": False, "error": "PUBLICATION_KEYS"}
    serving = doc["serving"]
    if not isinstance(serving, dict) or set(serving) != {"freshness_classification"}:
        return {"valid": False, "error": "SERVING_KEYS"}
    artifact = {k: v for k, v in doc.items() if k != "serving"}
    verdict = oracle(artifact)
    if verdict["valid"] and serving["freshness_classification"] != "NOT_ASSESSED_" + str(artifact["state_label"]):
        return {"valid": False, "error": "SERVING_STATE_MISMATCH"}
    return verdict


def flow_json(flow):
    return {"venue": flow.venue, "instrument": flow.instrument, "base": flow.base, "quote": flow.quote,
            "market_kind": flow.market_kind, "id_domain": flow.id_domain,
            "side_convention": {"attested": flow.side.attested, "evidence_ref": flow.side.evidence_ref}}


def config_json(cfg):
    out = {k: v for k, v in cfg.items() if k != "trade_flow"}
    out["trade_flow"] = flow_json(cfg["trade_flow"])
    out["coverage"] = [list(c) for c in cfg["coverage"]]
    return json.loads(dumps(out))


def shift(events, cfg, delta):
    """Move every instant by the same amount (the real replay then produces the result)."""
    events, cfg = copy.deepcopy(events), dict(cfg)
    for ev in events:
        if ev["kind"] == "trade":
            ev["received_ns"] += delta
            if isinstance(ev["record"].get("event_ns"), int):
                ev["record"]["event_ns"] += delta
        else:
            for clock in ("mono", "utc"):
                ev["receipt"][clock] = [t + delta for t in ev["receipt"][clock]]
    for k in ("as_of_receipt_ns", "anchor_ns"):
        cfg[k] += delta
    cfg["coverage"] = [(lo + delta, hi + delta) for lo, hi in cfg["coverage"]]
    cfg["heatmap"] = dict(cfg["heatmap"], t0_ns=cfg["heatmap"]["t0_ns"] + delta)
    return events, cfg


def to_eth(events, cfg, evidence_ref, session_map):
    events, cfg = copy.deepcopy(events), dict(cfg)
    for ev in events:
        if ev["kind"] == "trade":
            ev["record"]["instrument"] = "ETH-USD"
            ev["session_id"] = session_map.get(ev["session_id"], ev["session_id"])
        elif ev["kind"] == "l2":
            for e in ev["message"]["events"]:
                e["product_id"] = "ETH-USD"
    old = cfg["trade_flow"]
    side = tr.SideConvention(mapping=old.side.mapping, attested=False, evidence_ref=evidence_ref)
    cfg["trade_flow"] = tr.TradeFlow("coinbase_advanced", "ETH-USD", "ETH", "USD", "SPOT", old.id_domain, side)
    cfg["product"] = "ETH-USD"
    return events, cfg


def with_event_times(events):
    """Level event_time (dated and placeholder epoch) and a native envelope timestamp."""
    events = copy.deepcopy(events)
    first = events[0]["message"]
    first["timestamp"] = "2026-01-02T03:04:05.123456789Z"
    for u in first["events"][0]["updates"]:
        if u["side"] == "bid" and u["price_level"] == "1000":
            u["event_time"] = "2026-01-02T03:04:05.123456789Z"
        if u["side"] == "offer" and u["price_level"] == "1001":
            u["event_time"] = "1970-01-01T00:00:00Z"
    return events


def cases_spec():
    """(id, description, events, config) - every one is replayed by the real builder."""
    base_ev, base_cfg = fx.synthetic_session()
    a = fx.ANCHOR
    out = [("native_base", "the repository synthetic session, unchanged", base_ev, base_cfg)]

    ev, cfg = shift(base_ev, base_cfg, 2**60 + 12_345)
    out.append(("native_ns_above_2_53", "same session shifted by 2**60+12345 ns: instants beyond 2**53", ev, cfg))

    ev, cfg = shift(base_ev, base_cfg, 9 * 10**28)
    out.append(("native_ns_30_digits", "same session shifted to 30-digit nanosecond texts", ev, cfg))

    ev, cfg = to_eth(base_ev, base_cfg, "SYNTHETIC-é-\U0001F600-CONVENTION-NOT-ATTESTED",
                     {"s1": "séssion-\U0001F600-1", "s2": "séssion-\U0001F600-2"})
    out.append(("native_eth_unicode_text", "ETH-USD with non-BMP and accented text in evidence_ref and session ids", ev, cfg))

    ev = copy.deepcopy(base_ev)
    # Arrives after the straddling message but began earlier: read order is not guessed, it is not read.
    ev.insert(8, fx._l2(9, a + 12 * S, fx._upd([("bid", "1000.1", "1")])))
    cfg = dict(base_cfg, as_of_receipt_ns=a + 20 * S + 5)
    out.append(("native_as_of_straddle", "as_of inside an l2 receipt: book UNRESOLVED, later l2 events not read", ev, cfg))

    cfg = dict(base_cfg, as_of_receipt_ns=a + 160 * S)
    out.append(("native_book_invalid_gap", "as_of after a sequence gap, before the resync snapshot: book INVALID", base_ev, cfg))

    cfg = dict(base_cfg, as_of_receipt_ns=a + S // 2)
    out.append(("native_no_snapshot", "as_of before any l2 message: NO_SNAPSHOT, no freshness", base_ev, cfg))

    ev = copy.deepcopy(base_ev)
    ev.insert(8, {"kind": "l2", "message": {"sequence_num": 2, "events": []}, "receipt": fx._rcv(a + 25 * S)})
    out.append(("native_malformed_message", "an l2 envelope without channel: MALFORMED_MESSAGE:CHANNEL_MISSING", ev, base_cfg))

    out.append(("native_event_times", "dated level event_time, placeholder epoch and a native envelope timestamp",
                with_event_times(base_ev), dict(base_cfg, as_of_receipt_ns=a + 10 * S)))

    cfg = dict(base_cfg, silence_budget_ns=5 * S)
    out.append(("native_silence_exceeded", "a tight silence budget: heatmap BOOK_* columns and silence statuses", base_ev, cfg))

    cfg = dict(base_cfg, depth_levels_limit=1)
    out.append(("native_depth_limited", "depth limited to one level per side: cover bounds present", base_ev, cfg))

    ev = [e for e in base_ev if e["kind"] != "trade"]
    out.append(("native_no_trades", "book only: covered bars without a trade", ev, base_cfg))
    return out


def derive_variants(native):
    """Contract variants derived from native_base, each labelled as such."""
    out = []

    def variant(name, description, mutate):
        doc = copy.deepcopy(native)
        mutate(doc)
        out.append((name, description, doc))

    def historical(d):
        d["evidence_kind"] = d["state_label"] = "HISTORICAL"

    variant("variant_historical", "evidence_kind/state_label HISTORICAL (a contract variant, not historical evidence)", historical)

    def age(status, overall, interval, unresolved=()):
        def mutate(d):
            f = d["book"]["freshness"]
            f.update(state_age_status=status, state_age_ns=interval, freshness=overall, unresolved=list(unresolved))
        return mutate

    variant("variant_future_timestamp", "state age FUTURE (negative): FUTURE_TIMESTAMP, never promoted",
            age("FUTURE", "FUTURE_TIMESTAMP", ["-5", "-3"]))
    variant("variant_stale_age", "state age STALE: STALE", age("STALE", "STALE", ["500", "600"]))
    variant("variant_future_not_excluded", "FUTURE_NOT_EXCLUDED", age("FUTURE_NOT_EXCLUDED", "FUTURE_NOT_EXCLUDED", ["-5", "5"]))
    variant("variant_stale_not_excluded", "STALE_NOT_EXCLUDED", age("STALE_NOT_EXCLUDED", "STALE_NOT_EXCLUDED", ["1", "900"]))
    variant("variant_qualified_within_assumptions", "age present, nothing unresolved: QUALIFIED_WITHIN_ASSUMPTIONS",
            age("WITHIN_ASSUMPTIONS", "QUALIFIED_WITHIN_ASSUMPTIONS", ["1", "2"]))
    variant("variant_qualified_with_unresolved", "INCONSISTENT: qualified while a reason is still unresolved",
            age("WITHIN_ASSUMPTIONS", "QUALIFIED_WITHIN_ASSUMPTIONS", ["1", "2"], ["SEND_TIME_NOT_SUPPLIED"]))
    variant("variant_qualified_without_age", "INCONSISTENT: qualified with an absent age",
            lambda d: d["book"]["freshness"].update(freshness="QUALIFIED_WITHIN_ASSUMPTIONS"))
    variant("variant_age_status_without_value", "INCONSISTENT: status WITHIN_ASSUMPTIONS with no age value",
            lambda d: d["book"]["freshness"].update(state_age_status="WITHIN_ASSUMPTIONS", freshness="QUALIFIED_WITHIN_ASSUMPTIONS", unresolved=[]))
    variant("variant_live_unqualified_claim_future", "INCONSISTENT: FUTURE age labelled LIVE_UNQUALIFIED",
            lambda d: d["book"]["freshness"].update(state_age_status="FUTURE", state_age_ns=["-2", "-1"]))
    variant("variant_placeholder_with_time", "INCONSISTENT: placeholder epoch with a numeric time behind it",
            lambda d: d["book"]["bbo"]["bid"].update(level_event_time_state="PLACEHOLDER_EPOCH_NOT_A_DATE", level_event_time_ns="1"))
    variant("variant_placeholder_without_time", "placeholder epoch without any time value",
            lambda d: d["book"]["bbo"]["bid"].update(level_event_time_state="PLACEHOLDER_EPOCH_NOT_A_DATE", level_event_time_ns=None))
    variant("variant_invalid_reason_unknown", "INCONSISTENT: an INVALID book with a reason the decoder never emits",
            lambda d: d["book"].update(state=["INVALID", "MADE_UP_REASON"]))
    def heat_status(status):
        def mutate(d):
            col = d["heatmap"]["columns"][1]
            d["heatmap"]["columns"][1] = {"bucket": col["bucket"], "status": status, "sample_receipt_ns": col["sample_receipt_ns"]}
        return mutate

    variant("variant_open_heatmap_status", "an open BOOK_* family status the oracle admits by pattern", heat_status("BOOK_SOMETHING_ELSE"))
    variant("variant_closed_heatmap_status", "an unknown non-BOOK heatmap status", heat_status("MADE_UP"))
    return out


# --------------------------------------------------------------------------- mutation corpus

def _walk(node, path=()):
    yield path, node
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, path + (i,))


def _resolve(doc, path):
    for step in path:
        doc = doc[step]
    return doc


def apply_mutation(doc, spec):
    """Apply one spec to a deep copy of ``doc`` (same semantics in the TypeScript test)."""
    doc = copy.deepcopy(doc)
    path, op = spec["path"], spec["op"]
    if not path and op == "set":
        return copy.deepcopy(spec["value"])
    parent = _resolve(doc, path[:-1]) if path else None
    if op == "set":
        parent[path[-1]] = copy.deepcopy(spec["value"])
    elif op == "delete":
        del parent[path[-1]]
    else:
        target = _resolve(doc, path)
        if op == "add_key":
            target[spec["key"]] = 0
        elif op == "append":
            target.append(copy.deepcopy(spec["value"]))
        elif op == "pop":
            target.pop()
        else:
            raise AssertionError(op)
    return doc


def mutation_specs(doc):
    specs = []
    for path, node in _walk(doc):
        path = list(path)
        for value in SET_VALUES:
            if value != node or type(value) is not type(node):
                specs.append({"path": path, "op": "set", "value": value})
        if path and isinstance(path[-1], str):
            specs.append({"path": path, "op": "delete"})
        if path and isinstance(path[-1], int) and isinstance(_resolve(doc, path[:-1]), list):
            pass
        if isinstance(node, dict):
            specs.append({"path": path, "op": "add_key", "key": "extra"})
        if isinstance(node, list):
            specs.append({"path": path, "op": "append", "value": "0"})
            if node:
                specs.append({"path": path, "op": "pop"})
    return specs


def unicode_specs():
    """Boundary code points around every non-printable range (Python 3.11 / Unicode 14), plus lengths."""
    target = ["flow", "side_convention", "evidence_ref"]
    points = set()
    for lo, hi in nonprintable_ranges():
        for cp in (lo - 1, lo, hi, hi + 1):
            if 0 <= cp <= 0x10FFFF:
                points.add(cp)
    specs = [{"path": target, "op": "set", "value": "a%sb" % chr(cp)} for cp in sorted(points)]
    for n in (511, 512, 513):
        specs.append({"path": target, "op": "set", "value": "a" * n})
        specs.append({"path": target, "op": "set", "value": "\U0001F600" * n})
        specs.append({"path": target, "op": "set", "value": "é\U0001F600" * (n // 2) + "z" * (n % 2)})
    return specs


def nonprintable_ranges():
    ranges, start = [], None
    for cp in range(0x110000):
        bad = not chr(cp).isprintable()
        if bad and start is None:
            start = cp
        elif not bad and start is not None:
            ranges.append([start, cp - 1])
            start = None
    if start is not None:
        ranges.append([start, 0x10FFFF])
    return ranges


def build_mutation_file(base_id, artifact, specs):
    rows = []
    errors_not_value = 0
    for n, spec in enumerate(specs):
        verdict = oracle(apply_mutation(artifact, spec))
        if not verdict["valid"] and not verdict["error"].startswith("ValueError"):
            errors_not_value += 1
        rows.append(dict(spec, id="%s-%05d" % (base_id, n), python=verdict))
    return rows, errors_not_value


# --------------------------------------------------------------------------- raw / response cases

def body_text(body: bytes) -> str:
    return body.decode("utf-8")


def raw_cases(body: bytes, unicode_body: bytes):
    """(id, description, intended 'accept'/'refuse', mutated bytes)."""
    t = body_text(body)
    cases = []

    def add(name, description, intended, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        cases.append((name, description, intended, data))

    def sub(old, new, count=1):
        assert t.count(old) >= 1, old
        return t.replace(old, new, count)

    add("raw_float_counter", "counter spelt 19.0", "refuse", sub('"event_count":19', '"event_count":19.0'))
    add("raw_exponent_counter", "counter spelt 19e0", "refuse", sub('"event_count":19', '"event_count":19e0'))
    add("raw_fraction_exponent_counter", "counter spelt 1.9e1", "refuse", sub('"event_count":19', '"event_count":1.9e1'))
    add("raw_unsafe_counter", "counter 9007199254740993", "refuse", sub('"event_count":19', '"event_count":9007199254740993'))
    add("raw_negative_counter", "counter -1", "refuse", sub('"event_count":19', '"event_count":-1'))
    add("raw_bool_counter", "counter true", "refuse", sub('"event_count":19', '"event_count":true'))
    add("raw_ns_as_number", "as_of_receipt_ns as a JSON number", "refuse", re.sub(r'"as_of_receipt_ns":"(\d+)"', r'"as_of_receipt_ns":\1', t, count=1))
    add("raw_duplicate_top_key", "product key twice", "refuse", t.replace("{", '{"product":"MarketFlowArtifact",', 1))
    add("raw_duplicate_escaped_key", "product key twice, once escaped", "refuse", t.replace("{", '{"pr\\u006fduct":"MarketFlowArtifact",', 1))
    add("raw_duplicate_nested_key", "inputs.event_count twice", "refuse", sub('"inputs":{', '"inputs":{"event_count":19,'))
    add("raw_nan", "NaN where a counter is", "refuse", sub('"event_count":19', '"event_count":NaN'))
    add("raw_infinity", "Infinity where a counter is", "refuse", sub('"event_count":19', '"event_count":Infinity'))
    add("raw_negative_infinity", "-Infinity where a counter is", "refuse", sub('"event_count":19', '"event_count":-Infinity'))
    add("raw_leading_zero", "counter spelt 019", "refuse", sub('"event_count":19', '"event_count":019'))
    add("raw_trailing_comma", "trailing comma in inputs", "refuse", sub('"event_count":19', '"event_count":19,') )
    add("raw_trailing_garbage", "text after the document", "refuse", t + "x")
    add("raw_second_document", "two documents", "refuse", t + t)
    add("raw_empty", "empty body", "refuse", b"")
    add("raw_truncated", "document cut in half", "refuse", t[: len(t) // 2])
    add("raw_bom", "UTF-8 byte-order mark in front", "refuse", b"\xef\xbb\xbf" + t.encode("utf-8"))
    add("raw_invalid_utf8", "byte 0xFF inside a string", "refuse", t.encode("utf-8").replace(b'"SYNTHETIC"', b'"SYN\xffTHETIC"', 1))
    add("raw_overlong_utf8", "overlong 0xC0 0xAF inside a string", "refuse", t.encode("utf-8").replace(b'"SYNTHETIC"', b'"SYN\xc0\xafTHETIC"', 1))
    add("raw_utf8_encoded_surrogate", "UTF-8 encoded lone surrogate", "refuse", t.encode("utf-8").replace(b'"SYNTHETIC"', b'"SYN\xed\xa0\x80THETIC"', 1))
    add("raw_lone_surrogate_escape", "\\ud800 escape in a text field (not printable)", "refuse",
        sub('"evidence_ref":"', '"evidence_ref":"\\ud800'))
    add("raw_control_char", "raw TAB inside a string", "refuse", sub('"evidence_ref":"', '"evidence_ref":"\t'))
    add("raw_depth_bomb", "100 nested arrays in assumptions", "refuse", sub('"assumptions":[', '"assumptions":[' + "[" * 100 + "]" * 100 + ","))
    add("raw_single_quotes", "single-quoted key", "refuse", t.replace('"product"', "'product'", 1))
    add("raw_serving_missing", "no serving member", "refuse", SERVING_TAIL.sub(b"}", body).decode("utf-8"))
    add("raw_serving_wrong_class", "serving says HISTORICAL for a SYNTHETIC artifact", "refuse",
        t.replace("NOT_ASSESSED_SYNTHETIC", "NOT_ASSESSED_HISTORICAL"))
    add("raw_serving_extra_key", "unknown key inside serving", "refuse",
        t.replace('"freshness_classification":"NOT_ASSESSED_SYNTHETIC"', '"freshness_classification":"NOT_ASSESSED_SYNTHETIC","fresh":true'))
    add("raw_serving_not_object", "serving as a string", "refuse", SERVING_TAIL.sub(b',"serving":"NOT_ASSESSED_SYNTHETIC"}', body).decode("utf-8"))
    add("raw_unknown_top_key", "an unknown key next to serving", "refuse", SERVING_TAIL.sub(b',"extra":1,"serving":{"freshness_classification":"NOT_ASSESSED_SYNTHETIC"}}', body).decode("utf-8"))

    # Equivalent spellings: both stacks must accept them.
    doc = json.loads(t)
    add("raw_pretty_printed", "indented, same members", "accept", json.dumps(doc, indent=2, sort_keys=True))
    add("raw_key_order_reversed", "top-level members in reverse order", "accept",
        json.dumps(dict(reversed(list(doc.items()))), separators=(",", ":")))
    add("raw_escaped_ascii_key", "an ASCII key spelt with a unicode escape", "accept", t.replace('"product"', '"pr\\u006fduct"', 1))
    add("raw_negative_zero_counter", "counter 0 spelt -0 (an integer for Python too)", "accept",
        sub('"events_straddling_as_of_not_read":0', '"events_straddling_as_of_not_read":-0'))
    add("raw_whitespace_around", "JSON whitespace around the document", "accept", " \n\t\r" + t + "\r\n ")
    ub = unicode_body.decode("utf-8")
    add("raw_surrogate_pair_escape", "non-BMP text spelt with a surrogate-pair escape instead of UTF-8", "accept",
        ub.replace("\U0001F600", "\\ud83d\\ude00"))
    add("raw_ascii_escaped_unicode", "all non-ASCII text escaped (ensure_ascii spelling)", "accept",
        json.dumps(json.loads(ub), separators=(",", ":"), ensure_ascii=True))
    return cases


def artifact_corruptions(artifact_bytes: bytes):
    """Corrupted artifact FILES the real reader must refuse (or the accepted equivalents)."""
    t = artifact_bytes.decode("utf-8")
    doc = json.loads(t)
    out = []

    def add(name, description, data):
        out.append((name, description, data.encode("utf-8") if isinstance(data, str) else data))

    def js(d):
        return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def edit(fn):
        d = copy.deepcopy(doc)
        fn(d)
        return js(d)

    add("file_synthetic_false", "synthetic=false", edit(lambda d: d.update(synthetic=False)))
    add("file_live_evidence_kind", "evidence_kind LIVE (no live provenance exists)", edit(lambda d: d.update(evidence_kind="LIVE", state_label="LIVE")))
    add("file_extra_root_key", "unknown root key", edit(lambda d: d.update(extra=1)))
    add("file_nested_extra_key", "unknown key inside inputs", edit(lambda d: d["inputs"].update(extra=1)))
    add("file_missing_bars", "bars missing", edit(lambda d: d.pop("bars")))
    add("file_score_set", "score present", edit(lambda d: d.update(score="9")))
    add("file_quote_usdt", "bar quote USDT inside a USD flow", edit(lambda d: d["bars"][0].update(quote="USDT")))
    add("file_other_venue", "another venue label", edit(lambda d: d["flow"].update(venue="binance")))
    add("file_perp_market", "perpetual market kind", edit(lambda d: d["flow"].update(market_kind="PERP")))
    add("file_bar_geometry", "bar start moved", edit(lambda d: d["bars"][1].update(start_ns="1")))
    add("file_ns_number", "anchor_ns as a JSON number", re.sub(r'"anchor_ns":"(\d+)"', r'"anchor_ns":\1', js(doc), count=1))
    add("file_float_counter", "counter 19.0 (float)", js(doc).replace('"event_count":19', '"event_count":19.0'))
    add("file_duplicate_key", "duplicate product key", js(doc).replace("{", '{"product":"MarketFlowArtifact",', 1))
    add("file_nan_constant", "NaN constant", js(doc).replace('"event_count":19', '"event_count":NaN'))
    add("file_bom", "UTF-8 BOM", b"\xef\xbb\xbf" + js(doc).encode("utf-8"))
    add("file_invalid_utf8", "invalid UTF-8 byte", js(doc).encode("utf-8").replace(b'"SYNTHETIC"', b'"SYN\xffTHETIC"', 1))
    add("file_not_json", "plain text", "not json")
    add("file_json_array", "a JSON array instead of an object", "[]")
    add("file_oversize", "file larger than the reader bound", " " * (MAX_BYTES + 1))
    return out


# --------------------------------------------------------------------------- main

def oracle_description():
    return {
        "python_version": "%d.%d.%d" % sys.version_info[:3],
        "unicode_version": unicodedata.unidata_version,
        "contract_version": CONTRACT_VERSION,
        "calc_version": CALC_VERSION,
        "venue": l2.COINBASE_L2_FLOW.venue,
        "channel": l2.COINBASE_L2_FLOW.channel,
        "instruments": {k: list(v) for k, v in l2.INSTRUMENTS.items()},
        "top_keys": sorted(TOP_KEYS),
        "bar_statuses": list(contract.BAR_STATUSES),
        "book_states": list(contract.BOOK_STATES),
        "l2_refusals": list(contract.L2_REFUSALS),
        "invalid_reasons": list(contract.INVALID_REASONS),
        "silence_statuses": list(contract.SILENCE_STATUSES),
        "age_statuses": list(contract.AGE_STATUSES),
        "freshness": list(contract.FRESHNESS),
        "send_states": list(contract.SEND_STATES),
        "level_time_states": list(contract.LEVEL_TIME_STATES),
        "limits": {"MAX_BARS": contract.MAX_BARS, "MAX_COLUMNS": contract.MAX_COLUMNS, "MAX_ROWS": contract.MAX_ROWS,
                   "MAX_ITEMS": contract.MAX_ITEMS, "MAX_LIST": contract.MAX_LIST, "MAX_TEXT": contract.MAX_TEXT,
                   "READER_MAX_BYTES": MAX_BYTES},
        "nonprintable_ranges": nonprintable_ranges(),
    }


def write_body(directory: Path, name: str, data: bytes):
    (directory / name).write_bytes(data)
    return {"file": name, "sha256": sha256(data), "bytes": len(data)}


def generate_market_flow_fixture(out_dir):
    out_dir = Path(out_dir)
    root = out_dir / CORPUS_DIR
    for sub in ("bodies", "mutations", "artifacts"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    reader_before = api._market_flow_reader
    cases, natives = [], {}
    problems = []

    with tempfile.TemporaryDirectory(prefix="market-flow-3a-") as tmp:
        work = Path(tmp)

        # ---- native: real replay -> file -> reader -> route
        for name, description, events, cfg in cases_spec():
            events_before, cfg_before = copy.deepcopy(events), copy.deepcopy(cfg)
            artifact = replay(events, cfg)
            again = replay(events, cfg)
            assert canonical(artifact) == canonical(again), "replay must be deterministic: " + name
            assert events == events_before and cfg == cfg_before, "replay must not mutate its inputs: " + name
            file_bytes = dumps(artifact).encode("ascii")
            status, response = serve(file_bytes, work, name)
            assert status == 200, (name, status, response[:200])
            published = json.loads(response)
            serving = published.pop("serving")
            assert serving == {"freshness_classification": "NOT_ASSESSED_" + artifact["state_label"]}
            assert published == artifact, "the reader must serve the artifact unchanged: " + name
            natives[name] = artifact
            cases.append({
                "id": name, "group": "native", "description": description,
                "provenance": "synthetic_session -> artifact.replay -> temp file -> MarketFlowReader -> TestClient GET",
                "events_sha256": artifact["inputs"]["events_sha256"],
                "artifact_sha256": sha256(canonical(artifact)),
                "input_events": json.loads(dumps(events)), "config": config_json(cfg),
                "http_status": status, "body": write_body(root / "bodies", name + ".body", response),
                "python": {"valid": True, "error": None}, "expect": "success",
            })

        base = natives["native_base"]
        base_file = dumps(base).encode("ascii")
        _, base_body = serve(base_file, work, "base_for_raw")
        _, unicode_body = serve(dumps(natives["native_eth_unicode_text"]).encode("ascii"), work, "unicode_for_raw")

        # ---- no future leak: later events must not change anything but the counter
        ev, cfg = fx.synthetic_session()
        extra = ev + [fx._trade(99, cfg["as_of_receipt_ns"] + 50 * S, cfg["as_of_receipt_ns"] + 49 * S, "tfuture", "B", "1001", "999"),
                      fx._l2(50, cfg["as_of_receipt_ns"] + 60 * S, fx._upd([("bid", "1000.25", "88")]))]
        leaked = replay(extra, cfg)
        for key in ("events_after_as_of_not_read",):
            leaked["inputs"].pop(key)
        unleaked = copy.deepcopy(base)
        unleaked["inputs"].pop("events_after_as_of_not_read")
        if leaked != unleaked:
            problems.append("future events changed the artifact beyond the not-read counter")

        # ---- derived variants: Python verdict, then real reader/route
        for name, description, doc in derive_variants(base):
            verdict = oracle(doc)
            status, response = serve(dumps(doc).encode("ascii"), work, name)
            if (status == 200) != verdict["valid"]:
                problems.append("reader disagrees with the oracle for " + name)
            cases.append({
                "id": name, "group": "derived_variant", "description": description,
                "provenance": "derived from native_base by editing contract fields; NOT a native replay output, NOT historical evidence",
                "artifact_sha256": sha256(canonical(doc)), "http_status": status,
                "artifact": write_body(root / "artifacts", name + ".json", dumps(doc).encode("ascii")),
                "body": write_body(root / "bodies", name + ".body", response),
                "python": verdict, "expect": "success" if verdict["valid"] else "refuse",
            })

        # ---- corrupted artifact files through the real reader
        for name, description, data in artifact_corruptions(base_file):
            status, response = serve(data, work, name)
            if status != 503:
                problems.append("corrupted file was served: " + name)
            cases.append({
                "id": name, "group": "artifact_corruption", "description": description,
                "provenance": "native_base file corrupted, then real reader + route",
                "http_status": status, "body": write_body(root / "bodies", name + ".body", response),
                "artifact": write_body(root / "artifacts", name + ".json", data),
                "error_code": json.loads(response).get("error_code"),
                "python": {"valid": False, "error": json.loads(response).get("error_code")},
                "expect": "api_error",
            })

        # ---- native 503 / 404 bodies
        previous = api._market_flow_reader
        try:
            api.configure_market_flow_reader(None)
            with TestClient(api.app) as client:
                response = client.get(URL)
                missing_route = client.get(URL + "-not-published")
        finally:
            api._market_flow_reader = previous
        for name, description, status, data in (
            ("http_not_configured", "no path configured (default state)", response.status_code, response.content),
            ("http_route_missing", "FastAPI default 404 body of a release without the route", missing_route.status_code, missing_route.content),
        ):
            cases.append({
                "id": name, "group": "http_error", "description": description,
                "provenance": "FastAPI TestClient GET", "http_status": status,
                "body": write_body(root / "bodies", name + ".body", data),
                "error_code": (json.loads(data).get("error_code") if status == 503 else None),
                "python": {"valid": False, "error": "HTTP_%d" % status}, "expect": "api_error",
            })

        # ---- raw mutations of a real 200 body
        for name, description, intended, data in raw_cases(base_body, unicode_body):
            verdict = publication_verdict(data)
            if verdict["valid"] != (intended == "accept"):
                problems.append("Python verdict differs from the intended one for %s: %s" % (name, verdict))
            cases.append({
                "id": name, "group": "response_mutation", "description": description,
                "provenance": "bytes of a real HTTP 200 body, then edited as text/bytes",
                "http_status": 200, "body": write_body(root / "bodies", name + ".body", data),
                "python": verdict, "expect": "success" if verdict["valid"] else "refuse",
            })

        # ---- mutation corpora
        bases = {
            "base": natives["native_base"],
            "ns30": natives["native_ns_30_digits"],
            "eth": natives["native_eth_unicode_text"],
            "straddle": natives["native_as_of_straddle"],
            "events": natives["native_event_times"],
            "silence": natives["native_silence_exceeded"],
        }
        mutation_files, nonvalue = {}, 0
        for base_id, artifact in bases.items():
            rows, other = build_mutation_file(base_id, artifact, mutation_specs(artifact))
            nonvalue += other
            mutation_files[base_id] = rows
            (root / "mutations" / (base_id + ".json")).write_text(dumps({"base": "native_" + {
                "base": "base", "ns30": "ns_30_digits", "eth": "eth_unicode_text", "straddle": "as_of_straddle",
                "events": "event_times", "silence": "silence_exceeded"}[base_id], "cases": rows}), encoding="ascii")
        rows, other = build_mutation_file("unicode", base, unicode_specs())
        nonvalue += other
        mutation_files["unicode"] = rows
        (root / "mutations" / "unicode.json").write_text(dumps({"base": "native_base", "cases": rows}), encoding="ascii")

        # ---- sample of mutations through the REAL reader: it must agree with the oracle
        agree = 0
        for base_id in ("base", "events"):
            artifact = bases[base_id]
            for row in mutation_files[base_id][::37]:
                mutated = apply_mutation(artifact, row)
                status, _ = serve(dumps(mutated).encode("ascii"), work, "sample")
                if (status == 200) != row["python"]["valid"]:
                    problems.append("real reader disagrees with the oracle on " + row["id"])
                agree += 1

    assert api._market_flow_reader is reader_before, "reader global must be restored"
    manifest = {
        "kind": "MarketFlowCorpus", "corpus_version": 1,
        "warning": "Synthetic offline corpus. Hashes are test controls; nothing here is provider output or an admission of real data.",
        "oracle": oracle_description(),
        "required_native_cases": [c["id"] for c in cases if c["group"] == "native"],
        "cases": cases,
        "mutation_files": {k: {"file": "mutations/%s.json" % k, "count": len(v),
                               "valid": sum(1 for r in v if r["python"]["valid"])} for k, v in mutation_files.items()},
        "oracle_non_value_errors": nonvalue,
        "reader_sampled_mutations": agree,
        "generator_problems": problems,
    }
    (root / "manifest.json").write_text(dumps(manifest), encoding="ascii")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    result = generate_market_flow_fixture(parser.parse_args().out)
    if result["generator_problems"]:
        raise SystemExit("corpus problems: " + "; ".join(result["generator_problems"]))
