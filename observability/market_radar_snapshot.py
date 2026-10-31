"""Read-only CryptoRadar -> Operator Web MARKET snapshot publisher.

WEB-01-MARKET contract:
- reuses the existing CryptoRadar ranking functions;
- reads existing DecisionPacket evidence through ``scripts.radar_bot``;
- writes one small atomic JSON presentation artifact;
- never imports or calls advisor/risk/execution/PPL authority;
- never calls Telegram or an exchange.

Run once::

    python -m observability.market_radar_snapshot --once

Run continuously (default 30 s cadence)::

    python -m observability.market_radar_snapshot
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from scripts import radar_bot

SCHEMA_VERSION = "1.0.0"
CATALOGUE_SCHEMA_VERSION = "1.1.0"
DEFAULT_WINDOW_HOURS = 24
DEFAULT_MIN_CONFIDENCE = 65.0
DEFAULT_WATCHLIST_MIN_CONFIDENCE = 50.0
DEFAULT_TOP_N = 50
DEFAULT_INTERVAL_S = 30.0
DEFAULT_PATH = Path(
    os.getenv("RADAR_MARKET_SNAPSHOT_PATH", "databases/cryptoradar_market_snapshot.json")
)

_ALLOWED_ROW_KEYS = {
    "symbol",
    "avg_confidence",
    "max_confidence",
    "n_signals",
    "dominant_side",
    "dominance_pct",
    "regime",
}

_FORBIDDEN_EXECUTION_KEYS = {
    "entry",
    "entry_price",
    "sl",
    "stop_loss",
    "tp",
    "take_profit",
    "r_multiple",
    "trade_allowed",
    "is_actionable",
    "order",
    "position",
}


def _utc_now_iso(now_fn=time.time) -> str:
    return (
        datetime.fromtimestamp(float(now_fn()), tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _normalize_packet_timestamp_utc(value: Any) -> Optional[tuple[datetime, str]]:
    """Normalize one DecisionPacket ``created_at`` value at the MARKET boundary.

    Runtime proof for WEB-OBS-TIME-01 established that the canonical producer
    emits UTC wall-clock values through ``datetime.utcnow()`` and serializes
    them without timezone metadata. A timezone-naive value is therefore
    labelled UTC without changing its wall-clock fields. Explicit offsets are
    converted to UTC. Malformed values remain unresolved and are never
    repaired from generation time or filesystem metadata.
    """

    if not isinstance(value, str) or not value.strip():
        return None

    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        normalized = parsed.replace(tzinfo=timezone.utc)
    else:
        normalized = parsed.astimezone(timezone.utc)

    return normalized, normalized.isoformat().replace("+00:00", "Z")


def _latest_packet_timestamp(packets: Iterable[Mapping[str, Any]]) -> Optional[str]:
    """Return the newest genuine packet ``created_at`` normalized to UTC.

    Comparison is performed on parsed instants rather than raw strings so
    explicit offsets cannot distort ordering. Malformed values are ignored;
    no fallback timestamp is fabricated.
    """

    latest: Optional[tuple[datetime, str]] = None
    for packet in packets:
        normalized = _normalize_packet_timestamp_utc(packet.get("created_at"))
        if normalized is None:
            continue
        if latest is None or normalized[0] > latest[0]:
            latest = normalized
    return latest[1] if latest is not None else None


def _market_regime(all_stats: Iterable[Mapping[str, Any]]) -> Optional[str]:
    regimes = [s.get("regime") for s in all_stats]
    cleaned = [r for r in regimes if isinstance(r, str) and r.strip()]
    if not cleaned:
        return None
    counts = Counter(cleaned)
    # Deterministic tie break: highest count, then lexicographic regime name.
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _safe_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Project an existing CryptoRadar symbol-stat row onto the strict
    MARKET presentation whitelist. Execution-shaped fields can never pass
    through even if the upstream function later grows additional keys.
    """

    projected = {key: row.get(key) for key in _ALLOWED_ROW_KEYS}
    forbidden = _FORBIDDEN_EXECUTION_KEYS.intersection(projected)
    if forbidden:  # defensive; impossible with the whitelist above
        raise ValueError(f"execution-shaped MARKET keys detected: {sorted(forbidden)}")
    return projected


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _validate_projected_row(row: Mapping[str, Any]) -> None:
    if set(row) != _ALLOWED_ROW_KEYS:
        raise ValueError("MARKET opportunity row does not match strict whitelist")
    if not isinstance(row["symbol"], str) or not row["symbol"].strip():
        raise ValueError("MARKET opportunity symbol must be non-empty")
    _finite_number(row["avg_confidence"], "avg_confidence")
    _finite_number(row["max_confidence"], "max_confidence")
    if isinstance(row["n_signals"], bool) or not isinstance(row["n_signals"], int):
        raise ValueError("n_signals must be an integer")
    if row["n_signals"] < 0:
        raise ValueError("n_signals must be non-negative")
    if row["dominant_side"] not in {"LONG", "SHORT", "MIXED"}:
        raise ValueError("dominant_side outside CryptoRadar vocabulary")
    dominance = _finite_number(row["dominance_pct"], "dominance_pct")
    if not 0.0 <= dominance <= 100.0:
        raise ValueError("dominance_pct outside [0,100]")
    if not isinstance(row["regime"], str):
        raise ValueError("regime must be a string")


def _catalogue_window(packets, window_hours, now_fn):
    """Bound the opt-in catalogue by genuine UTC instants; keep exclusions visible."""
    if isinstance(window_hours, bool) or not isinstance(window_hours, int):
        raise ValueError("catalogue window_hours must be an integer")
    end = datetime.fromtimestamp(float(now_fn()), tz=timezone.utc)
    start = end - timedelta(hours=window_hours)
    included = []
    outside = future = unresolved = 0
    for packet in packets:
        if not isinstance(packet, Mapping):
            raise ValueError("catalogue input must contain packet objects")
        normalized = _normalize_packet_timestamp_utc(packet.get("created_at"))
        if normalized is None:
            unresolved += 1
        elif normalized[0] < start:
            outside += 1
        elif normalized[0] > end:
            future += 1
        else:
            if not isinstance(packet.get("symbol"), str) or not packet["symbol"].strip():
                raise ValueError("catalogue packet symbol must be non-empty")
            if _finite_number(packet.get("confidence"), "packet confidence") < 0:
                raise ValueError("catalogue confidence must be non-negative")
            included.append(packet)
    return included, {
        "start_at_utc": start.isoformat().replace("+00:00", "Z"),
        "end_at_utc": end.isoformat().replace("+00:00", "Z"),
        "input_packets": len(packets),
        "included_packets": len(included),
        "outside_window_packets": outside,
        "future_packets": future,
        "unresolved_timestamp_packets": unresolved,
    }


def build_market_snapshot(
    *,
    window_hours: int = DEFAULT_WINDOW_HOURS,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    watchlist_min_confidence: float = DEFAULT_WATCHLIST_MIN_CONFIDENCE,
    top_n: int = DEFAULT_TOP_N,
    include_catalogue: bool = False,
    source_packets: Optional[Iterable[Mapping[str, Any]]] = None,
    now_fn=time.time,
) -> Dict[str, Any]:
    """Build one deterministic read-only MARKET presentation document.

    Ranking semantics deliberately reuse CryptoRadar's existing
    ``load_recent_packets`` + ``compute_symbol_stats`` implementation. This
    module adds only a strict presentation projection and provenance envelope.
    """

    if window_hours <= 0:
        raise ValueError("window_hours must be > 0")
    if top_n <= 0:
        raise ValueError("top_n must be > 0")
    min_confidence = _finite_number(min_confidence, "min_confidence")
    watchlist_min_confidence = _finite_number(
        watchlist_min_confidence, "watchlist_min_confidence"
    )
    if watchlist_min_confidence > min_confidence:
        raise ValueError("watchlist_min_confidence must be <= min_confidence")

    # Explicit immutable inputs support offline catalogue preparation without
    # changing the runtime loader, its dates or process-global state.
    packets: List[Mapping[str, Any]] = list(
        radar_bot.load_recent_packets(window_hours) if source_packets is None else source_packets
    )
    coverage = None
    if include_catalogue:
        packets, coverage = _catalogue_window(packets, window_hours, now_fn)
    all_stats = list(radar_bot.compute_symbol_stats(packets, min_conf=0))
    qualifying = list(radar_bot.compute_symbol_stats(packets, min_conf=min_confidence))

    # ``compute_symbol_stats`` applies the threshold to individual packets,
    # matching the existing CryptoRadar scanner. Count the resulting symbol
    # rows before the top-N display truncation.
    actionable_count = len(qualifying)

    # Watchlist is a presentation-only count based on the aggregate confidence
    # already calculated by CryptoRadar, explicitly below the actionability
    # display threshold. It is never an execution gate.
    watchlist_count = sum(
        1
        for row in all_stats
        if watchlist_min_confidence <= float(row.get("avg_confidence", 0.0)) < min_confidence
    )

    top_rows = [_safe_row(row) for row in qualifying[:top_n]]
    for row in top_rows:
        _validate_projected_row(row)

    snapshot: Dict[str, Any] = {
        "schema_version": CATALOGUE_SCHEMA_VERSION if include_catalogue else SCHEMA_VERSION,
        "product": "CryptoRadar",
        "domain": "market",
        "authority": "OBSERVATIONAL_TELEMETRY",
        "mode": "OBSERVATION",
        "generated_at_utc": coverage["end_at_utc"] if coverage is not None else _utc_now_iso(now_fn),
        "source_updated_at_utc": _latest_packet_timestamp(packets),
        "window_hours": int(window_hours),
        "min_confidence": float(min_confidence),
        "packets_observed": len(packets),
        "market_regime": _market_regime(all_stats),
        "universe_size": len(all_stats),
        "actionable_count": actionable_count,
        "watchlist_count": watchlist_count,
        "top_opportunities": top_rows,
    }

    if include_catalogue:
        catalogue_rows = [_safe_row(row) for row in all_stats]
        qualified_rows = [_safe_row(row) for row in qualifying]
        for row in catalogue_rows + qualified_rows:
            _validate_projected_row(row)
        snapshot["catalogue"] = {
            "population": "ALL_OBSERVED_PACKETS",
            "rows": catalogue_rows,
            "qualified_rows": qualified_rows,
            "coverage": coverage,
        }

    # Explicit no-execution/no-secret guard over the serialized document.
    lowered = json.dumps(snapshot, sort_keys=True).lower()
    for key in _FORBIDDEN_EXECUTION_KEYS:
        if f'"{key}"' in lowered:
            raise ValueError(f"forbidden execution key leaked into MARKET payload: {key}")
    for secret_key in ("token", "password", "secret", "api_key", "apikey"):
        if f'"{secret_key}"' in lowered:
            raise ValueError(f"secret-shaped key leaked into MARKET payload: {secret_key}")

    return snapshot


def write_market_snapshot(
    path: Path = DEFAULT_PATH,
    *,
    now_fn=time.time,
    window_hours: int = DEFAULT_WINDOW_HOURS,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    top_n: int = DEFAULT_TOP_N,
    include_catalogue: bool = False,
) -> Dict[str, Any]:
    """Build and atomically publish one MARKET snapshot.

    ``os.replace`` guarantees that readers never observe a partially-written
    JSON document on the same filesystem.
    """

    path = Path(path)
    snapshot = build_market_snapshot(
        window_hours=window_hours,
        min_confidence=min_confidence,
        top_n=top_n,
        include_catalogue=include_catalogue,
        now_fn=now_fn,
    )
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)
    return snapshot


def publish_once(path: Path = DEFAULT_PATH, **kwargs: Any) -> bool:
    """Fail-passive wrapper for service/CLI use."""

    try:
        write_market_snapshot(path, **kwargs)
        return True
    except Exception as exc:  # observability must never become authority
        print(f"[MarketRadarSnapshot] publish failed: {exc}", file=sys.stderr, flush=True)
        return False


def run_loop(path: Path, interval_s: float, **publish_kwargs: Any) -> None:
    if interval_s <= 0:
        raise ValueError("interval_s must be > 0")
    while True:
        publish_once(path, **publish_kwargs)
        time.sleep(interval_s)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Publish read-only CryptoRadar MARKET snapshot")
    parser.add_argument("--once", action="store_true", help="publish once and exit")
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_S)
    parser.add_argument("--catalogue", action="store_true", help="opt in to complete v1.1 catalogue and bounded UTC window")
    parser.add_argument("--window-hours", type=int, default=DEFAULT_WINDOW_HOURS)
    args = parser.parse_args(argv)
    if not args.catalogue and args.window_hours != DEFAULT_WINDOW_HOURS:
        parser.error("--window-hours requires --catalogue for a bounded UTC window")
    kwargs = {"include_catalogue": args.catalogue, "window_hours": args.window_hours}

    if args.once:
        return 0 if publish_once(args.path, **kwargs) else 1
    run_loop(args.path, args.interval, **kwargs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_PATH",
    "SCHEMA_VERSION",
    "CATALOGUE_SCHEMA_VERSION",
    "build_market_snapshot",
    "write_market_snapshot",
    "publish_once",
    "run_loop",
]
