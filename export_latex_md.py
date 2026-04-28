"""
Module : export_latex_md.py
Export des résultats en LaTeX et Markdown pour rapports scientifiques.
"""

import os

import pandas as pd


def export_latex_md(
    sim_csv_dir="sim_summaries", latex_file="results.tex", md_file="results.md"
):
    csv_files = [f for f in os.listdir(sim_csv_dir) if f.endswith(".csv")]
    if not csv_files:
        print("Aucun fichier de simulation trouvé.")
        return
    sim_dfs = [pd.read_csv(os.path.join(sim_csv_dir, f)) for f in csv_files]
    sim_df = pd.concat(sim_dfs, ignore_index=True)
    # Export LaTeX
    with open(latex_file, "w", encoding="utf-8") as f:
        f.write(sim_df.to_latex(index=False))
    print(f"Export LaTeX sauvegardé : {latex_file}")
    # Export Markdown
    with open(md_file, "w", encoding="utf-8") as f:
        f.write(sim_df.to_markdown(index=False))
    print(f"Export Markdown sauvegardé : {md_file}")


if __name__ == "__main__":
    export_latex_md()
