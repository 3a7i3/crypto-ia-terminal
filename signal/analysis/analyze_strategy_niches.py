import glob
import os

import pandas as pd

# Analyse automatique des niches écologiques
# - Détecte les spécialistes trend/range/crash
# - Donne la proportion de chaque espèce (entry.type)
# - Affiche les meilleurs scores par environnement


def analyze_niches(csv_path=None, n_clusters=4, save_html=True, save_csv=True):
    required_cols = {"fitness_trend", "fitness_range", "fitness_crash", "entry.type"}
    if not csv_path:
        csv_files = sorted(glob.glob("results/pop_gen_*.csv"))[
            ::-1
        ]  # plus récent d'abord
        assert csv_files, "Aucun fichier CSV de population trouvé."
        for path in csv_files:
            df = pd.read_csv(path)
            if required_cols.issubset(df.columns):
                csv_path = path
                break
        else:
            print(
                "\n[INFO] Aucun CSV de population avec toutes les colonnes requises trouvé."
            )
            print(
                "Génère une nouvelle population avec le script run_strategy_factory.py pour activer l'analyse des niches écologiques."
            )
            return
    else:
        df = pd.read_csv(csv_path)
        assert required_cols.issubset(
            df.columns
        ), f"Colonnes manquantes dans {csv_path}"
    df = pd.read_csv(csv_path)

    # Détection des spécialistes
    def classify(row):
        vals = [row["fitness_trend"], row["fitness_range"], row["fitness_crash"]]
        max_env = ["trend", "range", "crash"][vals.index(max(vals))]
        return max_env

    df["specialist"] = df.apply(classify, axis=1)

    # Proportion par type d'espèce
    print("\nRépartition des types d'espèces (entry.type) :")
    print(df["entry.type"].value_counts(normalize=True).round(2))

    # Proportion de spécialistes par environnement
    print("\nRépartition des spécialistes par environnement :")
    print(df["specialist"].value_counts(normalize=True).round(2))

    # Meilleurs scores par environnement
    print("\nTop stratégies par environnement :")
    for env in ["trend", "range", "crash"]:
        best = df.loc[df[f"fitness_{env}"].idxmax()]
        print(
            f"  {env.upper()} : id={best['id']} | entry.type={best['entry.type']} | score={best[f'fitness_{env}']:.3f}"
        )

    # Visualisation 3D Plotly avec clustering réel (KMeans)
    try:
        import plotly.express as px
        from sklearn.cluster import KMeans

        X = df[["fitness_trend", "fitness_range", "fitness_crash"]].values
        kmeans = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
        df["cluster"] = kmeans.fit_predict(X)
        fig = px.scatter_3d(
            df,
            x="fitness_trend",
            y="fitness_range",
            z="fitness_crash",
            color="specialist",
            symbol="cluster",
            hover_data=[
                "entry.type",
                "fitness_trend",
                "fitness_range",
                "fitness_crash",
                "cluster",
            ],
            title=f"🧬 Écosystème des Stratégies (Espèces + Environnements, Clustering KMeans, n={n_clusters})",
        )
        fig.show()
        # Sauvegarde HTML
        if save_html:
            html_path = os.path.join("results", f"niches_clusters_{n_clusters}.html")
            fig.write_html(html_path)
            print(f"[EXPORT] Figure Plotly sauvegardée : {html_path}")
        # Export CSV avec clusters
        if save_csv:
            csv_out = os.path.join("results", f"niches_clusters_{n_clusters}.csv")
            df.to_csv(csv_out, index=False)
            print(f"[EXPORT] CSV avec clusters sauvegardé : {csv_out}")
            # Export JSON
            json_out = os.path.join("results", f"niches_clusters_{n_clusters}.json")
            df.to_json(json_out, orient="records", force_ascii=False)
            print(f"[EXPORT] JSON avec clusters sauvegardé : {json_out}")
            # Export Excel
            excel_out = os.path.join("results", f"niches_clusters_{n_clusters}.xlsx")
            df.to_excel(excel_out, index=False)
            print(f"[EXPORT] Excel avec clusters sauvegardé : {excel_out}")
            # Export Markdown
            md_out = os.path.join("results", f"niches_clusters_{n_clusters}.md")
            with open(md_out, "w", encoding="utf-8") as fmd:
                fmd.write(df.head(30).to_markdown(index=False))
            print(f"[EXPORT] Markdown (aperçu 30 lignes) sauvegardé : {md_out}")
    except ImportError:
        print(
            "[INFO] plotly ou scikit-learn n'est pas installé : pip install plotly scikit-learn pour la visualisation 3D avec clustering."
        )


# Entrée CLI enrichie
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyse des niches écologiques et visualisation clustering."
    )
    parser.add_argument(
        "--csv", type=str, default=None, help="Chemin du CSV de population à analyser."
    )
    parser.add_argument(
        "--clusters", type=int, default=4, help="Nombre de clusters KMeans."
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Ne pas sauvegarder la figure Plotly en HTML.",
    )
    parser.add_argument(
        "--no-csv", action="store_true", help="Ne pas exporter le CSV avec clusters."
    )
    args = parser.parse_args()
    analyze_niches(
        csv_path=args.csv,
        n_clusters=args.clusters,
        save_html=not args.no_html,
        save_csv=not args.no_csv,
    )

if __name__ == "__main__":
    analyze_niches()
