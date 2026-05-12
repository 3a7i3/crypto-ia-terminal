from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from population_csv_validator import validate_population_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Valide les CSV de population générés.")
    parser.add_argument("results_dir", nargs="?", default="results")
    args = parser.parse_args()

    errors = validate_population_dir(Path(args.results_dir))
    if errors:
        print("\n[ERREURS TROUVÉES]")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Tous les fichiers CSV de population sont valides.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
