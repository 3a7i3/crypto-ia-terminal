"""Passive bounded metadata capture. Never opens a DecisionPacket file."""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from observability.storage_contract import MAX_ENTRIES, METRICS, PATTERN, validate_storage_snapshot


class CaptureError(ValueError):
    pass


def _inventory(fd):
    entries, rows = 0, []
    # fd anchors every stat to the opened root, including during a rename.
    with os.scandir(fd) as directory:
        for entry in directory:
            entries += 1
            if entries > MAX_ENTRIES:
                raise CaptureError("OUTPUT_LIMIT")
            if not fnmatch.fnmatchcase(entry.name, PATTERN):
                continue
            info = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise CaptureError("INVALID_PATH")
            rows.append((entry.name, info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns))
    return entries, sorted(rows)


def _directory_signature(info):
    return info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns


def build_storage_snapshot(*, generated_at_utc, source_directory=None):
    doc = {"schema_version": "1.0.0", "product": "StorageSnapshot", "domain": "storage",
           "authority": "FILESYSTEM_METADATA_OBSERVATION", "mode": "READ_ONLY",
           "generated_at_utc": generated_at_utc, "observed_at_utc": generated_at_utc,
           "category": "DECISION_PACKET_LOGS", "scope": "DIRECT_CHILDREN_PATTERN", "pattern": PATTERN,
           "source_status": "NOT_CONFIGURED", **dict.fromkeys(METRICS)}
    if not validate_storage_snapshot(doc):
        raise ValueError("INVALID_GENERATION_TIME")
    if source_directory is not None:
        descriptor = None
        try:
            descriptor = os.open(source_directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK)
            before = os.fstat(descriptor)
            entries, rows = _inventory(descriptor)
            again = _inventory(descriptor)
            after = os.fstat(descriptor)
            current = os.stat(source_directory, follow_symlinks=False)
            if (entries, rows) != again or _directory_signature(before) != _directory_signature(after) or _directory_signature(current) != _directory_signature(after):
                raise CaptureError("SOURCE_CHANGED")
            latest = None if not rows else datetime.fromtimestamp(max(row[4] for row in rows) / 1e9, timezone.utc).isoformat().replace("+00:00", "Z")
            doc.update(source_status="PRESENT", entries_observed=entries, matched_file_count=len(rows),
                       total_bytes=sum(row[3] for row in rows), latest_file_modified_at_utc=latest,
                       inventory_sha256=hashlib.sha256(json.dumps(rows, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest())
            if not validate_storage_snapshot(doc):
                raise CaptureError("INVALID_METADATA")
        except CaptureError as error:
            doc["source_status"] = str(error)
        except FileNotFoundError:
            doc["source_status"] = "MISSING" if descriptor is None else "SOURCE_CHANGED"
        except NotADirectoryError:
            doc["source_status"] = "INVALID_PATH"
        except OSError:
            doc["source_status"] = "READ_ERROR"
        except (OverflowError, ValueError, TypeError):
            doc["source_status"] = "INVALID_METADATA"
        finally:
            if descriptor is not None:
                os.close(descriptor)
        if doc["source_status"] != "PRESENT":
            doc.update(dict.fromkeys(METRICS))
    if not validate_storage_snapshot(doc):
        raise ValueError("INVALID_STORAGE_SNAPSHOT")
    return doc


def publish_storage_snapshot(path, **kwargs):
    path = Path(path)
    root = kwargs.get("source_directory")
    if root is not None and path.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError("OUTPUT_WITHIN_SOURCE")
    doc = build_storage_snapshot(**kwargs)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".storage-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as output:
            json.dump(doc, output, allow_nan=False, sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return doc


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-directory", type=Path)
    parser.add_argument("--generated-at-utc", required=True)
    args = vars(parser.parse_args())
    publish_storage_snapshot(args.pop("out"), **args)
