"""Standalone governed D1-C launcher: python3 -I -B /approved/path/this.py.

Only two exact, verified Research source files are executed. No package search,
installation, sys.path extension, production import or dataset read here.
The launcher itself must be verified against the independently reviewed HEAD.
"""
from __future__ import annotations

import sys

# Refuse script execution before stdlib imports: without -I the script directory
# could itself shadow stdlib modules. Package import is only a synthetic test seam.
if __name__ == "__main__" and (sys.flags.isolated != 1 or not sys.dont_write_bytecode):
    sys.stdout.write('{"status":"D1_C_INTEGRITY_FAILURE","classification":"NOT_EMITTED",'
                     '"reason_code":"ISOLATED_NO_BYTECODE_EXECUTION_REQUIRED",'
                     '"COUNTERFACTUAL_PERFORMANCE_ELIGIBILITY":"NOT_PROVEN",'
                     '"PAPER_STRESS_RUNTIME_GO":"DENIED",'
                     '"ACTIVE_BURN_IN_IMMUTABILITY_GUARD":"ACTIVE"}\n')
    raise SystemExit(2)

import argparse
import hashlib
import importlib.machinery
import json
import os
import re
import stat
import types
from pathlib import Path

HISTORICAL_SHA256 = "11d3e13e90e04446f6d1fc5bff4840103fa4f23e2865a211e8b5f77771b94494"
CLASSIFIER = "stress_d1_rejection_eligibility.py"
HISTORICAL = "stress_d1_snapshot_audit.py"
MAX_SOURCE = 1024 * 1024
AUTHORIZED_SOURCE_ROOT = Path("/var/lib/crypto-ai-research-audit/readonly_d1_c_source")


class SourceBlocked(ValueError):
    pass


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise SourceBlocked(code)


def _custody(root: Path) -> None:
    _require(root == AUTHORIZED_SOURCE_ROOT,
             "AUTHORIZED_RESEARCH_SOURCE_ROOT_REQUIRED")
    for path in (root, *root.parents):
        mode = path.lstat()
        _require(stat.S_ISDIR(mode.st_mode) and not path.is_symlink() and
                 mode.st_uid == 0 and not mode.st_mode & (stat.S_IWGRP | stat.S_IWOTH),
                 "UNTRUSTED_SOURCE_ANCESTOR")
    _require(not root.stat().st_mode & stat.S_IWUSR, "IMMUTABLE_SOURCE_ROOT_REQUIRED")


def _source(path: Path, digest: str) -> bytes:
    _require(bool(re.fullmatch(r"[0-9a-f]{64}", digest)), "INVALID_SOURCE_SHA256")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        _require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and
                 not before.st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH),
                 "IMMUTABLE_SOURCE_FILE_REQUIRED")
        _require(before.st_size <= MAX_SOURCE, "SOURCE_SIZE_LIMIT")
        raw = stream.read(MAX_SOURCE + 1)
        after = os.fstat(stream.fileno())
        _require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                 (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) and
                 len(raw) == before.st_size, "SOURCE_CHANGED_DURING_READ")
    _require(hashlib.sha256(raw).hexdigest() == digest, "SOURCE_SHA256_MISMATCH")
    return raw


def _module(name: str, path: Path, raw: bytes, dependency=None):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__spec__ = importlib.machinery.ModuleSpec(name, loader=None, origin=str(path))
    if dependency is not None:
        module.d1 = dependency
    # Execute the exact verified bytes, rather than reopening through an import loader.
    exec(compile(raw, str(path), "exec", dont_inherit=True), module.__dict__)
    return module


def _load_sources(root: Path, classifier_sha256: str):
    _custody(root)
    historical_path, classifier_path = root / HISTORICAL, root / CLASSIFIER
    historical_bytes = _source(historical_path, HISTORICAL_SHA256)
    classifier_bytes = _source(classifier_path, classifier_sha256)
    historical = _module("_d1_c_historical", historical_path, historical_bytes)
    classifier = _module("_d1_c_classifier", classifier_path, classifier_bytes, historical)

    def verify():
        _custody(root)
        _require(classifier.d1 is historical, "HISTORICAL_MODULE_SUBSTITUTED")
        for module, path, digest in ((historical, historical_path, HISTORICAL_SHA256),
                                     (classifier, classifier_path, classifier_sha256)):
            _require(module.__file__ == str(path) and module.__spec__ is not None and
                     module.__spec__.origin == str(path), "IMPORTED_MODULE_PATH_MISMATCH")
            _source(path, digest)
        return {"historical_d1_auditor_sha256": HISTORICAL_SHA256,
                "script_sha256": classifier_sha256,
                "source_loading": "VERIFIED_BYTES_EXPLICIT_RESEARCH_PATH",
                "source_root": str(root)}

    classifier._source_verifier = verify
    verify()
    return classifier


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--classifier-sha256", required=True)
    parser.add_argument("--research-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        _require(sys.flags.isolated == 1 and sys.dont_write_bytecode,
                 "ISOLATED_NO_BYTECODE_EXECUTION_REQUIRED")
        classifier = _load_sources(args.source_root, args.classifier_sha256)
        result = classifier.audit(args.research_root)
    except (SourceBlocked, OSError, ValueError, TypeError, AttributeError) as exc:
        result = {"status": "D1_C_INTEGRITY_FAILURE", "classification": "NOT_EMITTED",
                  "reason_code": str(exc) if isinstance(exc, SourceBlocked) else "SOURCE_LOAD_FAILED",
                  "COUNTERFACTUAL_PERFORMANCE_ELIGIBILITY": "NOT_PROVEN",
                  "PAPER_STRESS_RUNTIME_GO": "DENIED", "ACTIVE_BURN_IN_IMMUTABILITY_GUARD": "ACTIVE"}
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    raise SystemExit(0 if result["status"] == "D1_C_REAL_SUBSET_CLASSIFIED" else 2)


if __name__ == "__main__":
    main()
