"""Deterministic frontend-only package from an already built checkout. No install, no network."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

SERVER = "frontend/scripts/web01_local_frontend_server.mjs"


def build(checkout: Path, merge_sha: str | None) -> tuple[bytes, dict]:
    head = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if subprocess.run(
        ["git", "-C", str(checkout), "status", "--porcelain", "--", "frontend"],
        check=True, capture_output=True, text=True,
    ).stdout:
        raise ValueError("DIRTY_FRONTEND_CHECKOUT")
    files = {SERVER: (checkout / SERVER).read_bytes()}
    dist = checkout / "frontend" / "dist"
    for path in sorted(p for p in dist.rglob("*") if p.is_file()):
        files[path.relative_to(checkout).as_posix()] = path.read_bytes()
    manifest = {
        "source_sha": head,
        "scope": "FRONTEND_ONLY",
        "source_merge_sha": merge_sha,
        "files": {n: hashlib.sha256(d).hexdigest() for n, d in sorted(files.items())},
    }
    members = {"manifest.json": json.dumps(manifest, indent=2, sort_keys=True).encode(), **files}
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w") as tar:
            for name, data in sorted(members.items()):
                info = tarfile.TarInfo(name)
                info.size, info.mtime, info.mode = len(data), 0, 0o644
                tar.addfile(info, io.BytesIO(data))
    return out.getvalue(), manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--merge-sha", help="verified merged source commit, if any")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw, manifest = build(args.checkout, args.merge_sha)
    args.output.write_bytes(raw)
    print(json.dumps({"archive_sha256": hashlib.sha256(raw).hexdigest(),
                      "source_sha": manifest["source_sha"], "files": len(manifest["files"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
