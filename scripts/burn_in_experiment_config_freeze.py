"""RB3 — explicit burn-in configuration freeze over the certified F00 engine.

This module adds burn-in semantic identity only. Deterministic discovery,
secret exclusion, environment precedence, pre-start guards, immutable overlay
writes, source-SHA binding and drift validation remain implemented by
scripts.f00_experiment_config_freeze.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from scripts import f00_experiment_config_freeze as _engine


SNAPSHOT_SCHEMA = "BURN_IN_EXPERIMENT_CONFIG_V1"
ConfigFreezeError = _engine.ConfigFreezeError
snapshot_sha256 = _engine.snapshot_sha256


def build_snapshot_payload(
    *,
    repo_root: Path,
    env_files: list[Path],
    paper_epoch_id: str,
    activation_path: Path,
    activation_bytes: bytes,
) -> dict[str, Any]:
    return _engine.build_snapshot_payload(
        repo_root=repo_root,
        env_files=env_files,
        paper_epoch_id=paper_epoch_id,
        activation_path=activation_path,
        activation_bytes=activation_bytes,
        snapshot_schema=SNAPSHOT_SCHEMA,
    )


def capture(
    *,
    repo_root: Path,
    env_files: list[Path],
    paper_epoch_id: str,
    output: Path,
    activation_output: Path,
    activation_pb_max_positions: int,
) -> dict[str, Any]:
    return _engine.capture(
        repo_root=repo_root,
        env_files=env_files,
        paper_epoch_id=paper_epoch_id,
        output=output,
        activation_output=activation_output,
        activation_pb_max_positions=activation_pb_max_positions,
        snapshot_schema=SNAPSHOT_SCHEMA,
    )


def validate(*, repo_root: Path, snapshot_path: Path) -> dict[str, Any]:
    return _engine.validate(
        repo_root=repo_root,
        snapshot_path=snapshot_path,
        snapshot_schema=SNAPSHOT_SCHEMA,
    )


def _default_output(repo_root: Path, epoch: str) -> Path:
    return repo_root / "databases" / "ppl_authority" / (
        f"{epoch}.burn-in-experiment-config.json"
    )


def _default_activation_output(repo_root: Path, epoch: str) -> Path:
    return repo_root / "databases" / "ppl_authority" / (
        f"{epoch}.burn-in-admission.env"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="repository root")
    sub = parser.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capture", help="create immutable burn-in config snapshot")
    cap.add_argument("--epoch", required=True)
    cap.add_argument("--env-file", action="append", required=True, dest="env_files")
    cap.add_argument("--activation-pb-max-positions", type=int, required=True)
    cap.add_argument("--output", default=None)
    cap.add_argument("--activation-output", default=None)

    val = sub.add_parser("validate", help="validate current config against snapshot")
    val.add_argument("--snapshot", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    try:
        if args.command == "capture":
            env_files = [
                Path(item) if Path(item).is_absolute() else repo_root / item
                for item in args.env_files
            ]
            output = Path(args.output) if args.output else _default_output(
                repo_root, args.epoch
            )
            activation_output = (
                Path(args.activation_output)
                if args.activation_output
                else _default_activation_output(repo_root, args.epoch)
            )
            if not output.is_absolute():
                output = repo_root / output
            if not activation_output.is_absolute():
                activation_output = repo_root / activation_output

            doc = capture(
                repo_root=repo_root,
                env_files=env_files,
                paper_epoch_id=args.epoch,
                output=output,
                activation_output=activation_output,
                activation_pb_max_positions=args.activation_pb_max_positions,
            )
            print(f"SNAPSHOT_PATH={_engine._normalise_path(output, repo_root)}")
            print(f"SNAPSHOT_SCHEMA={doc['snapshot_schema']}")
            print(f"SNAPSHOT_SHA256={doc['snapshot_sha256']}")
            print(f"ACTIVATION_OVERLAY_PATH={doc['activation_overlay']['path']}")
            print(f"ACTIVATION_OVERLAY_SHA256={doc['activation_overlay']['sha256']}")
            print(f"RUNTIME_SOURCE_SHA={doc['runtime_source_sha']}")
            print(f"PAPER_EPOCH_ID={doc['paper_epoch_id']}")
            print("ACTIVATION_OVERLAY_WIRED=NO")
            print("BURN_IN_EXPERIMENT_CONFIG_CAPTURE=PASS")
            return 0

        snapshot = Path(args.snapshot)
        if not snapshot.is_absolute():
            snapshot = repo_root / snapshot
        result = validate(repo_root=repo_root, snapshot_path=snapshot)
        print(f"SNAPSHOT_SCHEMA={SNAPSHOT_SCHEMA}")
        print(f"SNAPSHOT_SHA256={result['snapshot_sha256']}")
        print(f"ACTIVATION_OVERLAY_SHA256={result['activation_sha256']}")
        print(f"RUNTIME_SOURCE_SHA={result['runtime_source_sha']}")
        print(f"PAPER_EPOCH_ID={result['paper_epoch_id']}")
        print("BURN_IN_EXPERIMENT_CONFIG_VALIDATE=PASS")
        return 0
    except ConfigFreezeError as exc:
        print(f"BURN_IN_EXPERIMENT_CONFIG=FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
