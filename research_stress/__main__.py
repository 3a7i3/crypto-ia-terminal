"""CLI offline à sortie stdout ; aucune racine runtime ou destination implicite."""
from __future__ import annotations

import argparse
from pathlib import Path

from .campaign import build_report
from .protocol import canonical, strict_json


def main() -> None:
    parser = argparse.ArgumentParser(description="PAPER-STRESS #401 : recherche uniquement")
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--research-code-sha", required=True)
    parser.add_argument("--dataset-copy", type=Path)
    parser.add_argument("--input-class", choices=["NO_DATASET", "SYNTHETIC_TEST_ONLY",
                                                "DECLARED_IMMUTABLE_RESEARCH_COPY"],
                        default="NO_DATASET")
    args = parser.parse_args()
    result = build_report(strict_json(args.protocol.read_bytes()),
                          research_code_sha=args.research_code_sha,
                          dataset_path=args.dataset_copy, input_class=args.input_class)
    print(canonical(result).decode("utf-8"))


if __name__ == "__main__":
    main()
