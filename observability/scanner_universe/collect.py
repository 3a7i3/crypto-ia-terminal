"""Scanner V1 universe producer: one bounded collection of the four official
public catalogues, then the pure computation of ``universe.compute_universe``.

Network calls live here only (never in the API nor in the browser). Five
public GET requests per run, no credential, no exchange write.

Usage (on the host that is allowed to reach the exchanges)::

    python -m observability.scanner_universe.collect --out-dir DIR
    python -m observability.scanner_universe.collect --replay DIR/runs/<run_id>

``--out-dir`` keeps every raw response under ``DIR/runs/<run_id>/`` with a
``manifest.json`` (reception time, HTTP status, sha256) and atomically replaces
``DIR/scanner-universe.json``. ``--replay`` recomputes the publication of a run
from its raw responses at the run's own evaluation time and prints it, so the
same intersection can be checked byte for byte. Collected data stays on the
host disk; nothing is written to Git.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from .catalogues import ENDPOINTS, MAX_RAW_BYTES, parse_all, sha256
from .universe import compute_universe

TIMEOUT_S = 20
USER_AGENT = "cat-scanner-universe/1.0 (public catalogue read)"
PUBLICATION = "scanner-universe.json"


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def fetch(url: str, opener=urllib.request.urlopen) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with opener(request, timeout=TIMEOUT_S) as response:
            status = response.status
            raw = response.read(MAX_RAW_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return {"raw": None, "received_ms": _now_ms(), "error": f"HTTP_{exc.code}", "http_status": exc.code}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        name = type(getattr(exc, "reason", exc)).__name__.upper()
        return {"raw": None, "received_ms": _now_ms(), "error": f"TRANSPORT_{name}"[:80], "http_status": None}
    received = _now_ms()
    if len(raw) > MAX_RAW_BYTES:
        return {"raw": None, "received_ms": received, "error": "RESPONSE_TOO_LARGE", "http_status": status}
    if status != 200:
        return {"raw": None, "received_ms": received, "error": f"HTTP_{status}", "http_status": status}
    return {"raw": raw, "received_ms": received, "error": None, "http_status": status}


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def encode(doc: dict) -> bytes:
    return (json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def run(out_dir: Path, fetcher=fetch, now_fn=_now_ms) -> dict:
    out_dir = Path(out_dir)
    previous = None
    try:
        previous = json.loads((out_dir / PUBLICATION).read_bytes())
    except (OSError, ValueError):
        previous = None
    started = now_fn()
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(started / 1000))
    run_dir = out_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    if previous is not None:
        # Kept so that --replay reproduces the dated reference byte for byte.
        (run_dir / "previous.json").write_bytes(encode(previous))
    documents, manifest = {}, {"run_id": run_id, "started_ms": started, "documents": {}}
    for name, url in ENDPOINTS.items():
        doc = fetcher(url)
        documents[name] = {k: doc[k] for k in ("raw", "received_ms", "error")}
        entry = {"url": url, "received_ms": doc["received_ms"], "error": doc["error"],
                 "http_status": doc.get("http_status"), "sha256": None, "bytes": None}
        if doc["raw"] is not None:
            (run_dir / f"{name}.json").write_bytes(doc["raw"])
            entry.update(sha256=sha256(doc["raw"]), bytes=len(doc["raw"]))
        manifest["documents"][name] = entry
    evaluated = now_fn()
    manifest["evaluated_ms"] = evaluated
    _atomic_write(run_dir / "manifest.json", encode(manifest))
    publication = compute_universe(parse_all(documents), evaluated, previous)
    publication_bytes = encode(publication)
    (run_dir / PUBLICATION).write_bytes(publication_bytes)
    _atomic_write(out_dir / PUBLICATION, publication_bytes)
    return publication


def replay(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    previous_path = run_dir / "previous.json"
    previous = json.loads(previous_path.read_bytes()) if previous_path.exists() else None
    manifest = json.loads((run_dir / "manifest.json").read_bytes())
    documents = {}
    for name, entry in manifest["documents"].items():
        raw = None
        if entry["sha256"] is not None:
            raw = (run_dir / f"{name}.json").read_bytes()
            if sha256(raw) != entry["sha256"]:
                raise ValueError(f"{name}: raw bytes do not match the manifest sha256")
        documents[name] = {"raw": raw, "received_ms": entry["received_ms"], "error": entry["error"]}
    return compute_universe(parse_all(documents), manifest["evaluated_ms"], previous)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--out-dir", type=Path)
    group.add_argument("--replay", type=Path)
    args = parser.parse_args(argv)
    if args.replay:
        sys.stdout.buffer.write(encode(replay(args.replay)))
        return 0
    publication = run(args.out_dir)
    summary = {k: publication[k] for k in ("status", "pair_count", "computed_ms", "universe_sha256", "blocking_sources")}
    summary["admissible"] = {s["market"]: s["admissible"] for s in publication["sources"]}
    print(json.dumps(summary, sort_keys=True))
    return 0 if publication["status"] != "UNVERIFIABLE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
