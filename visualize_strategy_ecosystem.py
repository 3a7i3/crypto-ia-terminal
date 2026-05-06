import configparser


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

config = configparser.ConfigParser()
config.read("strategy_factory_config.ini")
SHOW_PLOTS = config.getboolean("visualization", "show_plots", fallback=True)
DEFAULT_POPULATION_CSV = "results/pop_gen_19.csv"


def build_figure(csv_path: str = DEFAULT_POPULATION_CSV):
    # Charger le CSV de population (adapter le chemin/génération si besoin)
    df = pd.read_csv(csv_path)

    # Définir la couleur selon le type d'espèce (entry.type)
    if "entry.type" not in df.columns:
        # fallback si le nom de colonne diffère
        entry_type_col = [c for c in df.columns if "entry.type" in c][0]
    else:
        entry_type_col = "entry.type"

    # S'assurer que les colonnes nécessaires existent
    for col in ["fitness_trend", "fitness_range", "fitness_crash"]:
        if col not in df.columns:
            df[col] = float("nan")

    return px.scatter_3d(
        df,
        x="fitness_trend",
        y="fitness_range",
        z="fitness_crash",
        color=entry_type_col,
        hover_data=df.columns,
        title="Strategy Ecosystem: Specialization by Environment",
        symbol=entry_type_col,
    )


def main(csv_path: str = DEFAULT_POPULATION_CSV):
    fig = build_figure(csv_path)
    if SHOW_PLOTS:
        fig.show()
    return fig


if __name__ == "__main__":
    main()
