"""
Module : generate_report.py
Génère un rapport PDF synthétique à partir des résultats multi-simulations.
"""

import os

import matplotlib.pyplot as plt
import pandas as pd
from fpdf import FPDF


def generate_pdf_report(sim_dir="sim_summaries", output_file="rapport_simulations.pdf"):
    sim_files = [f for f in os.listdir(sim_dir) if f.endswith(".csv")]
    if not sim_files:
        print("Aucun fichier de simulation trouvé.")
        return
    sim_dfs = [pd.read_csv(os.path.join(sim_dir, f)) for f in sim_files]
    sim_df = pd.concat(sim_dfs, ignore_index=True)
    # Figure : boxplot
    plt.figure(figsize=(6, 4))
    sim_df.boxplot(column=["best_fitness"])
    plt.title("Distribution des meilleurs fitness")
    plt.tight_layout()
    plt.savefig("boxplot.png")
    plt.close()
    # Figure : scatter
    plt.figure(figsize=(6, 4))
    plt.scatter(sim_df["std_fitness"], sim_df["best_fitness"], c="blue")
    plt.xlabel("Std fitness")
    plt.ylabel("Best fitness")
    plt.title("Best fitness vs Std fitness")
    plt.tight_layout()
    plt.savefig("scatter.png")
    plt.close()
    # PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=16)
    pdf.cell(0, 10, "Rapport Synthétique des Simulations", ln=1, align="C")
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, f"Nombre de runs : {len(sim_df)}", ln=1)
    pdf.cell(0, 10, f"Fitness moyen : {sim_df['best_fitness'].mean():.4f}", ln=1)
    pdf.cell(0, 10, f"Fitness max : {sim_df['best_fitness'].max():.4f}", ln=1)
    pdf.cell(0, 10, f"Fitness min : {sim_df['best_fitness'].min():.4f}", ln=1)
    pdf.ln(5)
    pdf.cell(0, 10, "Boxplot des meilleurs fitness :", ln=1)
    pdf.image("boxplot.png", w=120)
    pdf.ln(5)
    pdf.cell(0, 10, "Scatter plot : Best fitness vs Std fitness", ln=1)
    pdf.image("scatter.png", w=120)
    pdf.output(output_file)
    print(f"Rapport PDF généré : {output_file}")


if __name__ == "__main__":
    generate_pdf_report()
