"""Compare a v3 inventory against explicitly selected Git histories.

Pass --scope-ref for each ref in the intended search. ABSENT applies only
within that scope, and only when the entire selected history was readable.
An inventory records files in a process view, not Python's loaded modules.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

OID = re.compile(r"[0-9a-f]{40}")


def git(*args: str) -> str | None:
    try:
        return subprocess.run(
            ("git", "--no-optional-locks", "--no-replace-objects", *args),
            # Strictly local: GIT_NO_LAZY_FETCH stops lazy fetches on Git >= 2.44 (the CLI option is
            # rejected by older Git); an empty GIT_ALLOW_PROTOCOL forbids every transport, which also
            # blocks the lazy fetch of a missing object on Git 2.43. Per call, never global.
            env={**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": ""},
            check=True, timeout=120, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def resolve(ref: str) -> str | None:
    oid = git("rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
    return oid if oid is not None and OID.fullmatch(oid) else None


def inventory_blobs(inventory: dict) -> dict[str, str | None]:
    if inventory.get("inventory_schema") != "cat-prod-inventory/3.0.0":
        raise ValueError("unsupported inventory schema")
    blobs = {}
    for path, row in inventory["files"].items():
        if any(part in ("", ".", "..") for part in path.split("/")) or not re.fullmatch(r"[A-Za-z0-9._/-]+", path):
            raise ValueError("invalid inventory path")
        observed = row["observation"]
        oid = observed.get("git_blob_sha1")
        blobs[path] = oid if observed.get("state") == "OBSERVED" and isinstance(oid, str) and OID.fullmatch(oid) else None
    return blobs


def compare(inventory: dict, reference: str, scope_refs: list[str]) -> dict:
    blobs = inventory_blobs(inventory)
    scope = {ref: resolve(ref) for ref in dict.fromkeys([reference, *scope_refs])}
    base = scope[reference]
    covered = all(scope.values()) and git("rev-parse", "--is-shallow-repository") == "false"
    reachable = None
    if covered:
        reachable = git("rev-list", "--objects", "--no-object-names", "--missing=error", *sorted(set(scope.values())))
    wanted = {oid for oid in blobs.values() if oid is not None}
    matches = wanted.intersection(reachable.splitlines()) if reachable is not None else set()
    exact = None
    if base:
        tree = git("ls-tree", "-r", "--full-tree", base, "--", *blobs) if blobs else ""
        if tree is not None:
            exact = {}
            for line in tree.splitlines():
                header, path = line.split("\t", 1)
                mode, kind, oid = header.split()
                if kind == "blob" and mode in ("100644", "100755"):
                    exact[path] = oid

    complete = bool(scope_refs and reachable is not None and exact is not None)
    rows = {}
    for path, oid in sorted(blobs.items()):
        if oid is None:
            state = "UNKNOWN"
        elif exact is not None and exact.get(path) == oid:
            state = "SAME_AS_REF"
        elif oid in matches:
            state = "IN_GITHUB_OTHER"
        elif complete and not path.startswith("frontend/dist/"):
            state = "ABSENT"
        else:
            state = "UNKNOWN"
        rows[path] = {"class": state, "blob": oid}
    return {"reference": reference, "scope_refs": scope, "absence_scope_checked": complete, "files": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--ref", default="origin/main")
    parser.add_argument("--scope-ref", action="append", default=[])
    args = parser.parse_args()
    try:
        inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
        result = compare(inventory, args.ref, args.scope_ref)
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        parser.error("unreadable or invalid inventory")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
