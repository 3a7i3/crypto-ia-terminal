"""CLI hors ligne : python -m observability.signals_indicators --input IN --output OUT.

Lit une enveloppe cat.signals.input.v1 déjà collectée, écrit la publication
cat.signals.indicators.v1. Aucun accès réseau, aucune écriture hors OUT.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from observability.signals_indicators.build import InputError, build_publication
from observability.signals_indicators.publish import dumps, write_atomic


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="signals_indicators")
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--code-sha", default="UNKNOWN")
    args = ap.parse_args(argv)
    try:
        doc = json.loads(args.input.read_text(encoding="utf-8"))
        pub = build_publication(doc, code_sha=args.code_sha)
    except (OSError, json.JSONDecodeError, InputError) as exc:
        print(f"signals_indicators: entrée refusée : {exc}", file=sys.stderr)
        return 2
    write_atomic(args.output, dumps(pub))
    print(f"signals_indicators: {pub['status']} -> {args.output}")
    return 0 if pub["status"] != "FAILED" else 1


if __name__ == "__main__":
    sys.exit(main())
