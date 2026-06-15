"""
scripts/validate_trade_dataset.py — Certification du corpus de trades paper.

Vérifie l'intégrité scientifique du dataset avant tout burn-in ou calibration.
Produit databases/paper_trades.metadata.json si --certify est passé.

Usage :
    python scripts/validate_trade_dataset.py
    python scripts/validate_trade_dataset.py --certify
    python scripts/validate_trade_dataset.py --path databases/paper_trades_clean.jsonl
    python scripts/validate_trade_dataset.py --json   # sortie JSON machine-readable

Exit codes :
    0 — certifié, burn-in eligible
    1 — violations détectées, burn-in bloqué
    2 — dataset vide ou introuvable
"""

from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Certification corpus trades paper")
    parser.add_argument(
        "--path",
        default="databases/paper_trades.jsonl",
        help="Chemin vers le JSONL à valider",
    )
    parser.add_argument(
        "--certify",
        action="store_true",
        help="Écrire databases/paper_trades.metadata.json si certifié",
    )
    parser.add_argument(
        "--metadata-path",
        default="databases/paper_trades.metadata.json",
        help="Destination du fichier de certification",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Sortie JSON machine-readable",
    )
    args = parser.parse_args()

    try:
        from paper_trading.dataset_validator import validate_corpus, write_metadata
    except ImportError as exc:
        print(f"[ERREUR] Import échoué: {exc}", file=sys.stderr)
        return 2

    report = validate_corpus(log_path=args.path)

    if args.json_output:
        print(json.dumps(report.to_metadata(), indent=2, ensure_ascii=False))
    else:
        print(report.report())

    if args.certify:
        write_metadata(report, metadata_path=args.metadata_path)
        if not args.json_output:
            status = "écrit" if report.burnin_eligible else "écrit (NON CERTIFIÉ)"
            print(f"\nMétadonnées {status} → {args.metadata_path}")

    return 0 if report.burnin_eligible else 1


if __name__ == "__main__":
    sys.exit(main())
