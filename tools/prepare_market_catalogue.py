"""Prepare an immutable historical MARKET catalogue from explicitly selected files.

Offline only: no runtime loader, exchange, credentials, server or active artifact.
The output directory must be new and outside the recovered dataset/presentation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from observability.market_radar_snapshot import build_market_snapshot
from observability.operator_api.market_reader import validate_market_snapshot

PACKET_FIELDS = ("symbol", "confidence", "side", "regime", "created_at")
VENUE_KEYS = ("exchange", "exchange_id", "venue", "venue_id", "source_exchange")
KNOWN_VENUES = {"mexc", "binance", "bybit", "okx", "kraken", "coinbase", "kucoin", "bitfinex", "hyperliquid"}


def _encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _regular_bytes(path):
    """Read a stable regular file without following a leaf symlink."""
    path = Path(path)
    if path.resolve(strict=True) != path.absolute():
        raise ValueError("symlink input refused")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("input is not a regular file")
        raw = stream.read()
        after = os.fstat(stream.fileno())
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError("input changed during read")
    return raw


def _verified_input(root, relative, manifest, *, packet=True):
    relative = str(relative)
    parts = PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts:
        raise ValueError("input must be a relative dataset path")
    expected_name = r"databases/decision_packets_\d{4}-\d{2}-\d{2}\.jsonl"
    if packet and not re.fullmatch(expected_name, relative):
        raise ValueError("only explicitly named daily DecisionPacket files are allowed")
    if not packet and relative != "databases/cryptoradar_market_snapshot.json":
        raise ValueError("unexpected reference snapshot")
    entry = manifest.get(relative)
    if not isinstance(entry, dict) or not isinstance(entry.get("sha256"), str):
        raise ValueError("input absent from received manifest")
    path = root / relative
    if not path.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
        raise ValueError("input escapes dataset root")
    raw = _regular_bytes(path)
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) != entry.get("size") or digest != entry["sha256"]:
        raise ValueError("input does not match received manifest")
    return raw, {"path": relative, "size": len(raw), "sha256": digest}


def _read_packets(root, names, manifest):
    projected, evidence, seen_ids = [], [], set()
    duplicate_ids = missing_venue = nonempty_lines = 0
    native_claims = Counter()
    for name in names:
        raw, receipt = _verified_input(root, name, manifest)
        count = 0
        for line in raw.decode("utf-8").splitlines():
            if not line.strip():
                continue
            nonempty_lines += 1
            # A malformed line refuses the catalogue; never silently call it complete.
            packet = json.loads(line)
            if not isinstance(packet, dict):
                raise ValueError("DecisionPacket line must be an object")
            count += 1
            packet_id = packet.get("packet_id")
            if isinstance(packet_id, str) and packet_id:
                duplicate_ids += int(packet_id in seen_ids)
                seen_ids.add(packet_id)
            claims = set()
            containers = [packet]
            for key in ("metadata", "provenance", "source"):
                if isinstance(packet.get(key), dict):
                    containers.append(packet[key])
            for container in containers:
                for key in VENUE_KEYS:
                    value = container.get(key)
                    if isinstance(value, str) and value.lower() in KNOWN_VENUES:
                        claims.add(value.lower())
            if not claims:
                missing_venue += 1
            native_claims.update(claims)
            projected.append({key: packet.get(key) for key in PACKET_FIELDS})
        evidence.append({**receipt, "packet_objects": count})
    return projected, evidence, {
        "decoded_packet_objects": len(projected),
        "nonempty_lines": nonempty_lines,
        "invalid_json_lines": 0,
        "duplicate_packet_ids": duplicate_ids,
        "duplicates_removed": False,
        "native_venue_claim_counts": dict(native_claims),
        "packets_without_recognised_native_venue": missing_venue,
        "venue_attestation": "UNRESOLVED",
        "market_type_attestation": "UNRESOLVED",
        "producer_sha_attestation": "NOT_AVAILABLE",
        "signature_verification": "NOT_PERFORMED",
    }


def _exclusive_file(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
        os.fchmod(stream.fileno(), 0o444)
        os.fsync(stream.fileno())


def prepare_catalogue(*, source_root, manifest_path, manifest_sha256, inputs,
                      as_of, output_dir, window_hours=24, reference_snapshot=None):
    source_root, output_dir = Path(source_root), Path(output_dir)
    if not isinstance(as_of, datetime) or as_of.tzinfo is None:
        raise ValueError("as_of must be an explicitly zoned historical instant")
    if len(set(inputs)) != len(inputs) or not inputs:
        raise ValueError("select one or more distinct daily input files")
    manifest_raw = _regular_bytes(manifest_path)
    if hashlib.sha256(manifest_raw).hexdigest() != manifest_sha256:
        raise ValueError("received manifest hash mismatch")
    manifest = json.loads(manifest_raw)
    if not isinstance(manifest, dict):
        raise ValueError("received manifest must map relative paths to hashes")
    parent = output_dir.parent
    if parent.resolve(strict=True) != parent.absolute() or "presentation" in output_dir.parts:
        raise ValueError("output must be outside presentation and symlink paths")
    if output_dir.resolve().is_relative_to(source_root.resolve()):
        raise ValueError("output must be outside the recovered dataset")
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError("output directory must not already exist")

    packets, evidence, provenance = _read_packets(source_root, inputs, manifest)
    clock = as_of.timestamp()
    snapshot = build_market_snapshot(
        source_packets=packets, include_catalogue=True, window_hours=window_hours,
        top_n=20, now_fn=lambda: clock,
    )
    if not validate_market_snapshot(snapshot):
        raise ValueError("candidate rejected by the compatible MARKET reader")

    reference = {"status": "NOT_CHECKED"}
    if reference_snapshot is not None:
        raw, receipt = _verified_input(source_root, reference_snapshot, manifest, packet=False)
        old = json.loads(raw)
        replay = build_market_snapshot(
            source_packets=packets, top_n=20, window_hours=old["window_hours"],
            min_confidence=old["min_confidence"], now_fn=lambda: clock,
        )
        differences = sorted(key for key in set(old) | set(replay) if old.get(key) != replay.get(key))
        reference = {**receipt, "status": "SEMANTIC_MATCH" if not differences else "DIFFERS",
                     "different_fields": differences,
                     "proves_original_producer_sha": False}

    repo = Path(__file__).resolve().parents[1]
    code_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True))
    payload = _encoded(snapshot)
    report = {
        "mission": "MARKET-CATALOGUE-02",
        "disposition": "PREPARED_OFFLINE_NOT_ADMITTED",
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "historical_as_of_utc": snapshot["generated_at_utc"],
        "manifest_sha256": manifest_sha256,
        "source_commit": code_sha,
        "source_worktree_dirty": dirty,
        "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "producer_sha256": hashlib.sha256((repo / "observability/market_radar_snapshot.py").read_bytes()).hexdigest(),
        "reader_sha256": hashlib.sha256((repo / "observability/operator_api/market_reader.py").read_bytes()).hexdigest(),
        "inputs": evidence,
        "input_provenance": provenance,
        "original_v1_0_comparison": reference,
        "candidate": {"file": "cryptoradar_market_snapshot.json",
                      "sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload),
                      "schema_version": snapshot["schema_version"],
                      "universe_size": snapshot["universe_size"],
                      "qualified_symbols": snapshot["actionable_count"],
                      "coverage": snapshot["catalogue"]["coverage"],
                      "btc": next((r for r in snapshot["catalogue"]["rows"] if r["symbol"] == "BTC/USDT"), None),
                      "eth": next((r for r in snapshot["catalogue"]["rows"] if r["symbol"] == "ETH/USDT"), None)},
        "compatible_reader_schema_check": "PASS",
        "active_path_written": False, "exchange_requested": False,
        "service_action": False, "scientific_admission": False,
        "limitations": ["archive-derived observation, not current market",
                        "catalogue of selected decoded packets, not an independent roster",
                        "venue and product not attested; code defaults cannot fill them",
                        "no executable quote, volume or spread can be reconstructed from confidence scores"],
    }
    output_dir.mkdir(mode=0o700, exist_ok=False)
    _exclusive_file(output_dir / "cryptoradar_market_snapshot.json", payload)
    _exclusive_file(output_dir / "CATALOGUE_PREPARATION.json", _encoded(report))
    fd = os.open(output_dir, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    # Verify that read-only inputs still match the same received manifest.
    for name in inputs:
        _verified_input(source_root, name, manifest)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--reference-snapshot")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = prepare_catalogue(
        source_root=args.source_root, manifest_path=args.manifest,
        manifest_sha256=args.manifest_sha256, inputs=args.input,
        as_of=datetime.fromisoformat(args.as_of.replace("Z", "+00:00")),
        window_hours=args.window_hours, reference_snapshot=args.reference_snapshot,
        output_dir=args.output_dir,
    )
    print(json.dumps(result["candidate"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
