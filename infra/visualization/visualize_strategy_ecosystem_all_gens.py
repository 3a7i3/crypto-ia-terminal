import configparser
import glob
import os
from typing import Iterable


def missing_module_message():
    missing = []
    try:
        import pandas
    except ImportError:
        missing.append("pandas")
    try:
        import plotly
    except ImportError:
        missing.append("plotly")
    if missing:
        print(
            "\n[ERREUR] Ce script nécessite les modules suivants :\n  "
            + ", ".join(missing)
            + "\nInstallez-les avec :\n    pip install pandas plotly\n"
        )
        import sys

        sys.exit(1)


missing_module_message()

import pandas as pd
import plotly.express as px

# --- Centralisation config (ajouté automatiquement) ---
config = configparser.ConfigParser()
config.read("strategy_factory_config.ini")
SHOW_PLOTS = config.getboolean("visualization", "show_plots", fallback=True)

def _iter_csv_files(results_glob: str) -> list[str]:
    return sorted(glob.glob(results_glob))


def _entry_type_column(df: pd.DataFrame) -> str:
    if "entry.type" in df.columns:
        return "entry.type"
    return next(c for c in df.columns if "entry.type" in c)


def _visualize_generation(csv_path: str, *, show_plots: bool) -> None:
    gen = os.path.splitext(os.path.basename(csv_path))[0].split("_")[-1]
    df = pd.read_csv(csv_path)
    required_cols = {"fitness_trend", "fitness_range", "fitness_crash"}
    if not required_cols.issubset(df.columns):
        print(
            f"[GEN {gen}] Colonnes manquantes pour visualisation avancée. Fichier ignoré : {csv_path}"
        )
        return
    entry_type_col = _entry_type_column(df)
    fig = px.scatter_3d(
        df,
        x="fitness_trend",
        y="fitness_range",
        z="fitness_crash",
        color=entry_type_col,
        hover_data=df.columns,
        title=f"Strategy Ecosystem (Gen {gen})",
        symbol=entry_type_col,
    )
    if show_plots:
        fig.show()


def main(results_glob: str = "results/pop_gen_*.csv", *, pause: bool = True) -> int:
    csv_files = _iter_csv_files(results_glob)
    for csv_path in csv_files:
        _visualize_generation(csv_path, show_plots=SHOW_PLOTS)
        if pause:
            gen = os.path.splitext(os.path.basename(csv_path))[0].split("_")[-1]
            input(f"Appuyez sur Entrée pour passer à la génération suivante ({gen})...")
    return len(csv_files)


if __name__ == "__main__":
    raise SystemExit(main())
