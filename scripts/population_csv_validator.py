from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

RESULTS_DIR = Path("results")
CRITICAL_COLS = {"id", "fitness", "species", "exit.tp", "exit.sl"}


def validate_csv_file(filepath: str | Path) -> tuple[bool, str]:
    csv_path = Path(filepath)
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
        if len(rows) < 1:
            return False, "Erreur de lecture: fichier vide"
        expected_cols = len(rows[0])
        for i, row in enumerate(rows[1:], 2):
            if len(row) != expected_cols:
                return False, f"Erreur de lecture: ligne {i} a {len(row)} colonnes au lieu de {expected_cols}"
    except Exception as exc:
        return False, f"Erreur de lecture: {exc}"

    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        return False, f"Erreur de lecture: {exc}"

    missing = CRITICAL_COLS - set(df.columns)
    if missing:
        return False, f"Colonnes manquantes: {', '.join(sorted(missing))}"

    cols_list = sorted(CRITICAL_COLS)
    if df[cols_list].isnull().any().any():
        return False, "Valeurs manquantes dans colonnes critiques"
    return True, "OK"


def validate_population_dir(results_dir: str | Path = RESULTS_DIR) -> list[str]:
    base_dir = Path(results_dir)
    errors: list[str] = []
    for csv_path in base_dir.glob("*.csv"):
        if "pop_gen_" not in csv_path.name and "_pop_gen_" not in csv_path.name:
            continue
        valid, message = validate_csv_file(csv_path)
        if not valid:
            errors.append(f"{csv_path.name}: {message}")
    return errors