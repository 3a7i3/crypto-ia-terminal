"""One-shot external PPL -> presentation bridge. No service or runtime control."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import stat
import tempfile
import time
import uuid
from pathlib import Path

from observability.burn_in_status_snapshot import BurnInStatusError, build_from_sources
from observability.event_center_snapshot import build_event_center
from observability.operator_api.burn_in_status_reader import BurnInStatusSnapshotReader
from observability.operator_api.event_center_reader import EventCenterReader

MAX_GENERATIONS = 1440
MAX_EPOCH_BYTES = 16 * 1024 * 1024
MAX_CONFIG_BYTES = 1024 * 1024


class BridgeError(ValueError):
    """Closed error code suitable for an operator report."""


def _no_links(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise BridgeError("INVALID_PATH")
    for item in reversed((path, *path.parents)):
        if item.is_symlink():
            raise BridgeError("SYMLINK_PATH")
    return path


def _private_directory(path):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise BridgeError("OUTPUT_NOT_PRIVATE")


def _write(path, doc):
    raw = json.dumps(doc, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    if len(raw) > 4 * 1024 * 1024:
        raise BridgeError("OUTPUT_LIMIT")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(raw).hexdigest()


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def publish(*, source_root, store_root, config_path, epoch, output_root,
            p12_alerts=None, supervision_alerts=None, now_fn=time.time):
    """Build and validate a generation before atomically replacing its pointer.

    API paths end in regular files under current/, a parent directory symlink.
    Separate API requests can span generations; no cross-request transaction is
    claimed. Readers must expose source boundaries rather than infer freshness.
    """
    source = _no_links(source_root)
    store = _no_links(store_root)
    config = _no_links(config_path)
    output = _no_links(output_root)
    alerts = {}
    for name, value in (("p12_alerts", p12_alerts), ("supervision_alerts", supervision_alerts)):
        path = None if value is None else _no_links(value)
        if path is not None and (not path.is_relative_to(source) or path.is_relative_to(output)):
            raise BridgeError("ALERT_SOURCE_OUTSIDE_DECLARED_ROOT")
        alerts[name] = path
    if not store.is_relative_to(source) or not config.is_relative_to(source):
        raise BridgeError("SOURCE_OUTSIDE_DECLARED_ROOT")
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise BridgeError("OUTPUT_OVERLAPS_SOURCE")
    if not source.is_dir() or not store.is_dir():
        raise BridgeError("SOURCE_UNAVAILABLE")
    if not isinstance(epoch, str) or not epoch or len(epoch) > 128:
        raise BridgeError("INVALID_EPOCH")
    # Bound inputs before calling the existing canonical reader/replay.
    epoch_path = _no_links(store / "epochs" / (hashlib.sha256(epoch.encode()).hexdigest() + ".jsonl"))
    for path, limit in ((epoch_path, MAX_EPOCH_BYTES), (config, MAX_CONFIG_BYTES)):
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise BridgeError("SOURCE_LIMIT_OR_TYPE")
    output.mkdir(mode=0o700, exist_ok=True)  # Parent must already exist.
    _private_directory(output)
    generations = output / "generations"
    if generations.is_symlink():
        raise BridgeError("SYMLINK_PATH")
    generations.mkdir(mode=0o700, exist_ok=True)
    _private_directory(generations)
    lock = os.open(output / ".publish.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    stage = None
    pointer_tmp = None
    try:
        lock_info = os.fstat(lock)
        if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_nlink != 1 or lock_info.st_uid != os.geteuid() or stat.S_IMODE(lock_info.st_mode) != 0o600:
            raise BridgeError("INVALID_LOCK")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BridgeError("BUSY") from None
        with os.scandir(generations) as entries:
            if sum(1 for _ in entries) >= MAX_GENERATIONS:
                raise BridgeError("RETENTION_LIMIT")
        current = output / "current"
        if os.path.lexists(current):
            if not current.is_symlink():
                raise BridgeError("INVALID_CURRENT_POINTER")
            target = Path(os.readlink(current))
            if len(target.parts) != 2 or target.parts[0] != "generations" or not target.parts[1].startswith("capture-"):
                raise BridgeError("INVALID_CURRENT_POINTER")
            previous = output / target
            _no_links(previous)
            if not previous.is_dir():
                raise BridgeError("INVALID_CURRENT_POINTER")
        try:
            burn = build_from_sources(store_root=store, paper_epoch_id=epoch,
                                      config_path=config, now_fn=now_fn)
        except BurnInStatusError:
            raise BridgeError("SOURCE_REJECTED") from None
        stage = Path(tempfile.mkdtemp(prefix=".building-", dir=generations))
        burn_path = stage / "burn_in_status_snapshot.json"
        burn_hash = _write(burn_path, burn)
        if not BurnInStatusSnapshotReader(burn_path, now_fn=now_fn).read().ok:
            raise BridgeError("BURN_IN_READER_REJECTED")
        center = build_event_center(generated_at_utc=burn["generated_at_utc"],
                                   ppl_lifecycles=burn_path, **alerts)
        if center["sources"][2]["status"] != "PRESENT":
            raise BridgeError("LIFECYCLE_SOURCE_REJECTED")
        center_path = stage / "event_center_snapshot.json"
        center_hash = _write(center_path, center)
        if not EventCenterReader(center_path, now_fn=now_fn).read().ok:
            raise BridgeError("EVENT_READER_REJECTED")
        generation = "capture-" + uuid.uuid4().hex
        manifest = {"schema": "operator-publication-bridge/0.1", "generation": generation,
                    "paper_epoch_id": epoch, "last_sequence": burn["last_sequence"],
                    "generated_at_utc": burn["generated_at_utc"],
                    "source_updated_at_utc": burn["source_updated_at_utc"],
                    "ppl_stream_sha256": burn["ppl_stream_sha256"],
                    "config_snapshot_hash": burn["config_snapshot_hash"],
                    "files": {"burn_in_status_snapshot.json": burn_hash,
                              "event_center_snapshot.json": center_hash},
                    "alerts": ("NOT_CONFIGURED" if all(path is None for path in alerts.values()) else
                               {item["source_id"]: {**{key: item[key] for key in ("status", "source_sha256", "records_observed", "published_count")}, "coverage": item.get("coverage", "FULL" if item["status"] == "PRESENT" else None)}
                                for item in center["sources"][:2]}), "runtime_deployment": "NOT_ATTESTED",
                    "cross_request_consistency": "NOT_GUARANTEED"}
        _write(stage / "manifest.json", manifest)
        _sync_directory(stage)
        destination = generations / generation
        os.rename(stage, destination)
        stage = None
        _sync_directory(generations)
        pointer_tmp = output / (".current-" + uuid.uuid4().hex)
        os.symlink("generations/" + generation, pointer_tmp)
        os.replace(pointer_tmp, current)
        pointer_tmp = None
        try:
            _sync_directory(output)
        except OSError:
            raise BridgeError("POINTER_SWITCHED_DURABILITY_UNCERTAIN") from None
        return manifest
    finally:
        if stage is not None:
            shutil.rmtree(stage)
        if pointer_tmp is not None:
            pointer_tmp.unlink(missing_ok=True)
        os.close(lock)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source-root", "store-root", "config-path", "output-root"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--epoch", required=True)
    parser.add_argument("--p12-alerts", type=Path)
    parser.add_argument("--supervision-alerts", type=Path)
    args = parser.parse_args(argv)
    try:
        result = publish(**vars(args))
    except BridgeError as error:
        print(json.dumps({"status": "FAILED", "error_code": str(error)}))
        return 1
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        print(json.dumps({"status": "FAILED", "error_code": "SOURCE_OR_PUBLICATION_FAILED"}))
        return 1
    print(json.dumps({"status": "PUBLISHED", "generation": result["generation"],
                      "last_sequence": result["last_sequence"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
