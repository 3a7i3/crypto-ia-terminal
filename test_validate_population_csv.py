import os

import pandas as pd

RESULTS_DIR = "results"
CRITICAL_COLS = {"id", "fitness", "species", "exit.tp", "exit.sl"}


def validate_csv_file(filepath):
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        return False, f"Erreur de lecture: {e}"
    missing = CRITICAL_COLS - set(df.columns)
    if missing:
        return False, f"Colonnes manquantes: {', '.join(missing)}"
    # Convertir le set en liste pour l'indexation
    cols_list = list(CRITICAL_COLS)
    if df[cols_list].isnull().any().any():
        return False, "Valeurs manquantes dans colonnes critiques"
    return True, "OK"


def main():
    errors = []
    for fname in os.listdir(RESULTS_DIR):
        if fname.endswith(".csv") and ("pop_gen_" in fname or "_pop_gen_" in fname):
            fpath = os.path.join(RESULTS_DIR, fname)
            valid, msg = validate_csv_file(fpath)
            if not valid:
                errors.append(f"{fname}: {msg}")
    if errors:
        print("\n[ERREURS TROUVÉES]")
        for err in errors:
            print("-", err)
        exit(1)
    else:
        print("Tous les fichiers CSV de population sont valides.")


if __name__ == "__main__":
    main()
