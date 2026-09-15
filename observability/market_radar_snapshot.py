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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from scripts import radar_bot

SCHEMA_VERSION = "1.0.0"
DEFAULT_WINDOW_HOURS = 24
DEFAULT_MIN_CONFIDENCE = 65.0
DEFAULT_WATCHLIST_MIN_CONFIDENCE = 50.0
DEFAULT_TOP_N = 20
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


def _latest_packet_timestamp(packets: Iterable[Mapping[str, Any]]) -> Optional[str]:
    """Return the newest genuine packet ``created_at`` string if available.

    The producer does not fabricate/normalize a timestamp from file mtime or
    generation time. ISO-like strings sort chronologically for the formats
    emitted by DecisionPacket; if a malformed/non-string value is present it
    is ignored rather than repaired.
    """

    values = [p.get("created_at") for p in packets]
    strings = [v for v in values if isinstance(v, str) and v.strip()]
    return max(strings) if strings else None


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


def build_market_snapshot(
    *,
    window_hours: int = DEFAULT_WINDOW_HOURS,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    watchlist_min_confidence: float = DEFAULT_WATCHLIST_MIN_CONFIDENCE,
    top_n: int = DEFAULT_TOP_N,
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

    packets: List[Mapping[str, Any]] = list(radar_bot.load_recent_packets(window_hours))
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
        "schema_version": SCHEMA_VERSION,
        "product": "CryptoRadar",
        "domain": "market",
        "authority": "OBSERVATIONAL_TELEMETRY",
        "mode": "OBSERVATION",
        "generated_at_utc": _utc_now_iso(now_fn),
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


def run_loop(path: Path, interval_s: float) -> None:
    if interval_s <= 0:
        raise ValueError("interval_s must be > 0")
    while True:
        publish_once(path)
        time.sleep(interval_s)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Publish read-only CryptoRadar MARKET snapshot")
    parser.add_argument("--once", action="store_true", help="publish once and exit")
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_S)
    args = parser.parse_args(argv)

    if args.once:
        return 0 if publish_once(args.path) else 1
    run_loop(args.path, args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_PATH",
    "SCHEMA_VERSION",
    "build_market_snapshot",
    "write_market_snapshot",
    "publish_once",
    "run_loop",
]
