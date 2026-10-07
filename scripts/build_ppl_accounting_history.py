"""Explicit offline publication. Runtime inputs are opened read-only."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from observability.ppl_accounting_history import build_history
from observability.operator_api.ppl_accounting_history_reader import validate_history


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    output = args.output.resolve()
    frozen = Path("/home/mathieu/crypto_ai_terminal").resolve()
    if output == frozen or frozen in output.parents:
        p.error("output must be outside the frozen runtime")
    if output in (args.snapshot.resolve(), args.manifest.resolve()):
        p.error("output must not overwrite an input")
    for source, limit in ((args.snapshot, 2_000_000), (args.manifest, 100_000)):
        if source.stat().st_size > limit:
            p.error("input exceeds bounded size")
    sha = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    if subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True).strip():
        p.error("producer source worktree must be clean")
    result = build_history(args.snapshot.read_bytes(), args.manifest.read_bytes(), producer_sha=sha)
    if not validate_history(result):
        p.error("generated artifact failed the closed transport contract")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=output.parent, prefix=".history-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(result, f, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp, 0o640)
        os.replace(temp, output)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    print(json.dumps({"verdict": "PPL_ACCOUNTING_HISTORY_BUILT", "paper_epoch_id": result["paper_epoch_id"],
                      "last_sequence": result["last_sequence"], "source_digest": result["source_snapshot_sha256"]}))


if __name__ == "__main__":
    main()
