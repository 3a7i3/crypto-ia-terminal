import glob
import json
import os
import sys

import pandas as pd
import plotly.express as px
import plotly.io as pio
from jinja2 import Template

HTML_TEMPLATE = Template(
    """
<html>
<head><title>Rapport Simulation Evolution</title></head>
<body>
<h1>Rapport Simulation Evolution</h1>
<h2>Statistiques globales</h2>
<ul>
  <li>Nombre de générations : {{ stats.get("nb_generations", "N/A") }}</li>
  <li>Nombre total de stratégies : {{ stats.get("nb_strategies", "N/A") }}</li>
  <li>Espèces rencontrées : {{ stats.get("species", []) }}</li>
  <li>Fitness max : {{ stats.get("fitness_max", "N/A") }}</li>
  <li>Fitness moyen : {{ stats.get("fitness_mean", "N/A") }}</li>
  <li>Fitness médian : {{ stats.get("fitness_median", "N/A") }}</li>
</ul>
<h2>Meilleurs survivants cross-monde</h2>
<pre>{{ best | tojson(indent=2) }}</pre>
<h2>Fichiers exportés</h2>
<ul>
{% for f in files %}<li>{{ f }}</li>{% endfor %}
</ul>
<h2>Visualisations interactives</h2>
{% if plot_html %}
{{ plot_html|safe }}
{% endif %}
</body>
</html>
"""
)


def generate_report(results_dir: str = "sim_summaries") -> str:
    csv_files = sorted(glob.glob(os.path.join(results_dir, "*.csv")))
    csv_dfs = [pd.read_csv(f) for f in csv_files]
    full_df = pd.concat(csv_dfs, ignore_index=True) if csv_dfs else pd.DataFrame()

    best_json = os.path.join(results_dir, "best_strategies_cross_world.json")
    best = {}
    if os.path.exists(best_json):
        with open(best_json, "r", encoding="utf-8") as f:
            best = json.load(f)

    stats = {}
    if not full_df.empty:
        if "generation" in full_df.columns:
            stats["nb_generations"] = full_df["generation"].nunique()
        stats["nb_strategies"] = len(full_df)
        if "species" in full_df.columns:
            stats["species"] = list(full_df["species"].unique())
        if "fitness" in full_df.columns:
            stats["fitness_max"] = full_df["fitness"].max()
            stats["fitness_mean"] = full_df["fitness"].mean()
            stats["fitness_median"] = full_df["fitness"].median()

    plot_html = ""
    if not full_df.empty:
        try:
            if "best_fitness" in full_df.columns:
                fig = px.box(
                    full_df,
                    y="best_fitness",
                    points="all",
                    title="Distribution des meilleurs fitness",
                )
                plot_html += pio.to_html(fig, full_html=False, include_plotlyjs="cdn")
            if "std_fitness" in full_df.columns and "best_fitness" in full_df.columns:
                fig = px.scatter(
                    full_df,
                    x="std_fitness",
                    y="best_fitness",
                    title="Best fitness vs Std fitness",
                )
                plot_html += pio.to_html(fig, full_html=False, include_plotlyjs="cdn")
            exclude_cols = {
                "run",
                "seed",
                "elite_ratio",
                "mutation_base",
                "stagnation_patience",
                "pop_size",
                "n_generations",
            }
            num_cols = [
                c
                for c in full_df.select_dtypes(include=["number"]).columns
                if c not in exclude_cols
            ]
            if len(num_cols) >= 2:
                corr = full_df[num_cols].corr()
                fig = px.imshow(
                    corr, text_auto=True, title="Corrélation des paramètres"
                )
                plot_html += pio.to_html(fig, full_html=False, include_plotlyjs="cdn")
        except Exception as e:
            plot_html += f"<p>Erreur lors de la génération des graphiques : {e}</p>"

    files = [os.path.basename(f) for f in glob.glob(os.path.join(results_dir, "*"))]
    html = HTML_TEMPLATE.render(
        stats=stats, best=best, files=files, plot_html=plot_html
    )

    out_path = os.path.join(results_dir, "rapport_simulation.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


if __name__ == "__main__":
    results_dir = sys.argv[1] if len(sys.argv) >= 2 else "sim_summaries"
    out = generate_report(results_dir)
    print(f"[OK] Rapport HTML généré dans {out}")
