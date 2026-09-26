#!/usr/bin/env python3
"""Offline RL-DATA-01 export command.

All source paths are explicit. This script performs no runtime/service discovery
and never deploys or mutates PAPER authority.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Running this file as `python scripts/rl_data_01_export.py` sets sys.path[0]
# to scripts/, not the repository root.  Add the source root explicitly so the
# offline CLI resolves the in-repo research_data package from any working dir.
_REPO_SOURCE_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_SOURCE_ROOT))

from research_data.operator import (  # noqa: E402
    OperatorError,
    OperatorExportRequest,
    export_from_clean_repo,
)
from research_data.paper_exporter import PaperExportError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export one immutable PAPER boundary into Research-owned storage."
    )
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--paper-epoch-id", required=True)
    parser.add_argument("--ppl-store-root", type=Path, required=True)
    parser.add_argument("--experiment-manifest", type=Path, required=True)
    parser.add_argument("--experiment-config", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--extracted-at-utc", required=True)
    parser.add_argument("--source-statuses-json", type=Path, required=True)
    parser.add_argument(
        "--decision-packet",
        dest="decision_packets",
        type=Path,
        action="append",
        default=[],
        help="DecisionPacket JSONL source shard; repeat for multiple shards.",
    )
    parser.add_argument("--decision-identity-journal", type=Path)
    parser.add_argument(
        "--certification-reference",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Immutable certification reference; repeat as needed.",
    )
    return parser


def _references(items: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise argparse.ArgumentTypeError(
                f"certification reference must be KEY=VALUE, got {item!r}"
            )
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise argparse.ArgumentTypeError(
                f"certification reference must be KEY=VALUE, got {item!r}"
            )
        if key in out:
            raise argparse.ArgumentTypeError(
                f"duplicate certification reference key: {key!r}"
            )
        out[key] = value
    return out


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        references = _references(args.certification_reference)
        result = export_from_clean_repo(
            OperatorExportRequest(
                repo_root=args.repo_root,
                paper_epoch_id=args.paper_epoch_id,
                ppl_store_root=args.ppl_store_root,
                experiment_manifest_path=args.experiment_manifest,
                experiment_config_path=args.experiment_config,
                output_root=args.output_root,
                extracted_at_utc=args.extracted_at_utc,
                source_statuses_path=args.source_statuses_json,
                decision_packet_paths=tuple(args.decision_packets),
                decision_identity_journal_path=args.decision_identity_journal,
                certification_references=references,
            )
        )
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    except (OperatorError, PaperExportError) as exc:
        print(f"RL-DATA-01 export refused: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "dataset_id": result.dataset_id,
                "source_boundary_id": result.source_boundary_id,
                "dataset_path": str(result.dataset_path),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
