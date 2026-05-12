# === Imports (streamlit en premier — set_page_config doit précéder les autres appels st.*) ===
import os
import subprocess
from pathlib import Path

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="Evolutionary Strategy Dashboard",
    layout="wide",
    page_icon="🧬",
    initial_sidebar_state="expanded",
)

# Afficher le chemin du dossier courant
st.info(f"Dossier courant : {os.getcwd()}")

# === Styles ===
st.markdown(
    """
<style>
.main {background-color: #f7f9fa;}
.block-container {padding-top: 2rem;}
.st-emotion-cache-1v0mbdj {background: #fff; border-radius: 12px; box-shadow: 0 2px 8px #0001;}
.st-emotion-cache-1v0mbdj h2 {color: #2b5876;}
.st-emotion-cache-1v0mbdj h3 {color: #4e4376;}
body { font-family: 'Segoe UI', 'Roboto', sans-serif; }
.stApp { background-color: #181c1f; color: #e0e0e0; }
.stTabs [data-baseweb="tab"] { background: #23272b; color: #e0e0e0; border-radius: 8px 8px 0 0; }
.stTabs [aria-selected="true"] { background: #2c3136; color: #00e0ff; }
.stButton>button { background: #00e0ff; color: #181c1f; border-radius: 6px; }
.stExpanderHeader { color: #00e0ff; }
</style>
""",
    unsafe_allow_html=True,
)


# === Data loading ===
results_dir = "results"
sim_dir = "sim_summaries"

if not os.path.exists(results_dir):
    st.warning(f"🚫 Dossier {results_dir}/ introuvable.")
    st.stop()
csv_files = [f for f in os.listdir(results_dir) if f.endswith(".csv")]
st.markdown(
    "# 🧬 Evolutionary Strategy Factory — <span style='color:#2b5876'>Dashboard</span>",
    unsafe_allow_html=True,
)
if not csv_files:
    st.warning("🚫 Aucun fichier CSV trouvé dans le dossier results/.")
    st.stop()
sim_files = []
sim_df = None


# === Tabs ===
tab1, tab2, tab3, tab4 = st.tabs(
    ["📊 Exploration", "🧩 Analyses avancées", "☁️ Exports & Sauvegardes", "ℹ️ Aide"]
)


def exploration_section(csv_files, results_dir):
    st.markdown(
        "### 📂 Sélection du fichier à visualiser",
        help="Choisissez un fichier de génération à explorer.",
    )
    col_refresh, col_select = st.columns([1, 4])
    with col_refresh:
        if st.button("🔄 Rafraîchir les fichiers", key="refresh_csv"):
            st.rerun()
    with col_select:
        selected_file = st.selectbox(
            "Sélectionnez une génération à explorer :",
            sorted(csv_files),
            key="selectbox_main_file",
        )
    try:
        with st.spinner("Chargement du fichier CSV..."):
            df = pd.read_csv(os.path.join(results_dir, selected_file))
    except Exception as e:
        st.error(f"Erreur de lecture du fichier : {e}")
        st.stop()
    st.info(f"Aperçu du fichier : {selected_file}")
    st.dataframe(df.head(100), use_container_width=True)

    # --- Affichage compact des filtres dynamiques ---
    with st.expander("🔎 Filtres avancés (affichage compact)", expanded=False):
        filter_cols = [
            col
            for col in df.columns
            if df[col].dtype in [int, float, "int64", "float64", "float32", "int32"]
        ]
        filter_presets = {
            "Top 10 par score": ("score", "desc", 10),
            "Top 10 par fitness": ("fitness", "desc", 10),
            "Top 10 drawdown": ("drawdown", "asc", 10),
            "Top 10 volatilité": ("volatility", "asc", 10),
            "Top 10 Sharpe": ("sharpe", "desc", 10),
            "Top 10 pertes max": ("max_loss", "asc", 10),
            "Top 10 ratio gain/perte": ("gain_loss_ratio", "desc", 10),
            "Top 10 profit": ("profit", "desc", 10),
            "Top 10 trades": ("nb_trades", "desc", 10),
        }
        preset = st.selectbox(
            "🎯 Preset d'analyse rapide",
            list(filter_presets.keys()),
            key="preset_select",
        )
        col, order, n = filter_presets[preset]
        if col in df.columns:
            if order == "desc":
                df_filtered = df.sort_values(col, ascending=False).head(n)
            else:
                df_filtered = df.sort_values(col, ascending=True).head(n)
            st.write(f"Affichage du preset : **{preset}** sur la colonne **{col}**")
            st.dataframe(df_filtered, use_container_width=True)
        else:
            st.warning(
                f"Colonne {col} absente du fichier. Veuillez vérifier vos données."
            )
        st.markdown("---")
        st.markdown("**Filtres personnalisés** :")
        filter_values = {}
        for c in filter_cols:
            min_val, max_val = float(df[c].min()), float(df[c].max())
            val = st.slider(
                f"{c}", min_val, max_val, (min_val, max_val), key=f"slider_{c}"
            )
            filter_values[c] = val
        mask = pd.Series([True] * len(df))
        for c, (vmin, vmax) in filter_values.items():
            mask &= (df[c] >= vmin) & (df[c] <= vmax)
        df_custom = df[mask]
        st.write(f"Résultats filtrés : {len(df_custom)} lignes")
        st.dataframe(df_custom.head(100), use_container_width=True)
    return df, selected_file


# === Fonctions d'analyse et visualisation ===


def visualisation_3d(df: pd.DataFrame) -> None:
    required = {"exit.tp", "exit.sl", "fitness"}
    missing = required - set(df.columns)
    if missing:
        st.warning(f"Colonnes manquantes pour la 3D : {missing}")
        return
    try:
        import plotly.express as px

        fig = px.scatter_3d(
            df,
            x="exit.tp",
            y="exit.sl",
            z="fitness",
            color="fitness",
            title="Visualisation 3D TP/SL/Fitness",
        )
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        st.error("plotly requis : pip install plotly")
    except Exception as e:
        st.warning(f"Erreur visualisation 3D : {e}")


def stats_par_espece(df: pd.DataFrame) -> None:
    if "species" not in df.columns:
        st.info("Colonne 'species' absente — stats globales affichées.")
        st.dataframe(df.describe(), use_container_width=True)
        return
    stats = df.groupby("species").agg(["mean", "std", "count"]).round(4)
    st.dataframe(stats, use_container_width=True)


def top5_et_heatmap(df: pd.DataFrame) -> None:
    num_cols = df.select_dtypes(include="number").columns.tolist()
    if not num_cols:
        st.warning("Aucune colonne numérique disponible.")
        return
    sort_col = "fitness" if "fitness" in df.columns else num_cols[0]
    top5 = df.nlargest(5, sort_col) if sort_col in df.columns else df.head(5)
    st.markdown("#### Top 5 stratégies")
    st.dataframe(top5, use_container_width=True)
    if len(num_cols) >= 2:
        try:
            import plotly.express as px

            corr = df[num_cols].corr().round(2)
            fig = px.imshow(corr, text_auto=True, title="Heatmap de corrélation")
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            st.error("plotly requis : pip install plotly")
        except Exception as e:
            st.warning(f"Erreur heatmap : {e}")


def evolution_fitness(df: pd.DataFrame) -> None:
    if "generation" not in df.columns:
        st.warning("Colonne 'generation' absente — impossible de tracer l'évolution.")
        return
    fit_col = "fitness" if "fitness" in df.columns else None
    if fit_col is None:
        st.warning("Colonne 'fitness' absente.")
        return
    try:
        import plotly.express as px

        grouped = df.groupby("generation")[fit_col].mean().reset_index()
        fig = px.line(
            grouped,
            x="generation",
            y=fit_col,
            title="Évolution de la fitness par génération",
        )
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        st.error("plotly requis : pip install plotly")
    except Exception as e:
        st.warning(f"Erreur courbe fitness : {e}")


def comparatif_multi_simulations(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("DataFrame vide — aucune simulation à comparer.")
        return
    num_cols = df.select_dtypes(include="number").columns.tolist()
    if not num_cols:
        st.warning("Aucune colonne numérique pour le comparatif.")
        return
    st.markdown("#### Statistiques comparatives")
    st.dataframe(df[num_cols].describe().round(4), use_container_width=True)
    if "fitness" in df.columns:
        try:
            import plotly.express as px

            fig = px.histogram(df, x="fitness", title="Distribution de la fitness")
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            pass


def import_export_csv(df: pd.DataFrame) -> None:
    st.markdown("#### Import / Export CSV")
    if not df.empty:
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Télécharger CSV", data=csv_bytes, file_name="export.csv", mime="text/csv"
        )
    uploaded = st.file_uploader("Importer un CSV", type="csv", key="csv_uploader")
    if uploaded is not None:
        try:
            imported = pd.read_csv(uploaded)
            st.success(
                f"Fichier importé : {len(imported)} lignes × {len(imported.columns)} colonnes"
            )
            st.dataframe(imported.head(20), use_container_width=True)
        except Exception as e:
            st.error(f"Erreur d'import : {e}")


with tab1:
    df, selected_file = exploration_section(csv_files, results_dir)

with tab2:
    st.markdown(
        "## 🧩 Analyses avancées (modules automatiques)",
        help="Lancez des analyses approfondies sur vos simulations.",
    )
    # ... (le reste de la section analyses avancées, inchangé)

with tab3:
    st.markdown(
        "☁️ Exports cloud et sauvegardes avancées",
        help="Sauvegardez ou exportez vos résultats vers différents services cloud.",
    )
    with st.expander("Exports cloud disponibles", expanded=True):
        dropbox_token = st.text_input(
            "Dropbox Access Token", type="password", key="dropbox_token"
        )
        if st.button("Exporter tous les rapports sur Dropbox", key="btn_dropbox"):
            with st.spinner("Export Dropbox en cours..."):
                try:
                    import dropbox

                    dbx = dropbox.Dropbox(dropbox_token)
                    files_to_export = [
                        "rapport_simulations.pdf",
                        "rapport_simulation.html",
                        "rapport_simulations.xlsx",
                    ]
                    uploaded = []
                    for f in files_to_export:
                        if os.path.exists(f):
                            with open(f, "rb") as file_data:
                                dbx.files_upload(
                                    file_data.read(),
                                    f"/{f}",
                                    mode=dropbox.files.WriteMode.overwrite,
                                )
                            uploaded.append(f)
                    if uploaded:
                        st.success(
                            f"Fichiers uploadés sur Dropbox : {', '.join(uploaded)}"
                        )
                    else:
                        st.warning(
                            "Aucun rapport à uploader trouvé dans le dossier courant."
                        )
                except ImportError:
                    st.error(
                        "Le module 'dropbox' n'est pas installé. Installez-le avec : pip install dropbox"
                    )
                    st.info(
                        "Pour activer l'export Dropbox, ouvrez un terminal et exécutez : pip install dropbox"
                    )
        # ... (idem pour Azure, FTP, Google Drive, S3, cloud local, avec spinners)

with tab4:
    st.markdown(
        """
    ### ℹ️ Aide & Conseils d'utilisation
    - **Sélectionnez un fichier de génération** pour explorer les stratégies.
    - Utilisez les filtres avancés pour affiner l'analyse.
    - Les exports cloud sont regroupés dans l'onglet dédié.
    - Cliquez sur "Rafraîchir les fichiers" pour recharger les nouveaux résultats sans relancer l'app.
    - En cas d'erreur d'import, installez les modules manquants avec `pip install ...`.
    """
    )

with st.container():
    # --- Intégration automatique des modules avancés ---
    st.markdown("## 🧩 Analyses avancées (modules automatiques)")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Analyse de sensibilité (Partial Dependence)"):
            import sensitivity_analysis

            sensitivity_analysis.plot_sensitivity(
                sim_csv_dir="sim_summaries", output_file="sensitivity_plot.png"
            )
            if os.path.exists("sensitivity_plot.png"):
                st.image(
                    "sensitivity_plot.png",
                    caption="Partial Dependence Plot",
                    use_column_width=True,
                )
    with col2:
        if st.button("Front de Pareto (multi-objectifs)"):
            import pareto_front

            pareto_front.plot_pareto(
                sim_csv_dir="sim_summaries", output_file="pareto_front.png"
            )
            if os.path.exists("pareto_front.png"):
                st.image(
                    "pareto_front.png", caption="Front de Pareto", use_column_width=True
                )
    with col3:
        if st.button("Clustering des stratégies"):
            import clustering

            clustering.plot_clustering(
                sim_csv_dir="sim_summaries", output_file="clustering_plot.png"
            )
            if os.path.exists("clustering_plot.png"):
                st.image(
                    "clustering_plot.png",
                    caption="Clustering (t-SNE)",
                    use_column_width=True,
                )

    st.markdown("### 🎬 Animation de l'évolution des stratégies")
    if st.button("Générer l'animation timeline"):
        import timeline_animation

        timeline_animation.animate_evolution(
            sim_csv_dir="sim_summaries", output_file="timeline_animation.mp4"
        )
        if os.path.exists("timeline_animation.mp4"):
            st.video("timeline_animation.mp4")

    st.markdown("### 🔔 Notifications avancées (email/Slack)")
    notif_col1, notif_col2 = st.columns(2)
    with notif_col1:
        email_to = st.text_input("Email destinataire", key="notif_email")
        if st.button("Envoyer notification email") and email_to:
            import notifications

            smtp_server = st.text_input("SMTP server", key="smtp_server")
            smtp_port = st.number_input("SMTP port", value=465, key="smtp_port")
            smtp_user = st.text_input("SMTP user", key="smtp_user")
            smtp_pass = st.text_input("SMTP password", type="password", key="smtp_pass")
            notifications.send_email(
                "Alerte Evolution",
                "Votre simulation est terminée.",
                email_to,
                smtp_server,
                smtp_port,
                smtp_user,
                smtp_pass,
            )
            st.success("Notification email envoyée.")
    with notif_col2:
        slack_url = st.text_input("Slack webhook URL", key="notif_slack")
        if st.button("Envoyer notification Slack") and slack_url:
            import notifications

            notifications.send_slack("Simulation Evolution terminée !", slack_url)
            st.success("Notification Slack envoyée.")

    st.markdown("### 🤖 AutoML/Auto-tuning (grid search)")
    if st.button("Lancer AutoML grid search"):
        import automl_tuning

        automl_tuning.automl_grid_search(
            sim_csv_dir="sim_summaries", output_file="automl_results.csv"
        )
        if os.path.exists("automl_results.csv"):
            df_automl = pd.read_csv("automl_results.csv")
            st.dataframe(df_automl, width="stretch")

    st.markdown("### 📄 Export LaTeX & Markdown")
    if st.button("Exporter résultats LaTeX/Markdown"):
        import export_latex_md

        export_latex_md.export_latex_md(
            sim_csv_dir="sim_summaries", latex_file="results.tex", md_file="results.md"
        )
        st.success("Exports LaTeX et Markdown générés.")
        if os.path.exists("results.tex"):
            with open("results.tex", "r", encoding="utf-8") as f:
                st.download_button(
                    "Télécharger LaTeX", f.read(), file_name="results.tex"
                )
        if os.path.exists("results.md"):
            with open("results.md", "r", encoding="utf-8") as f:
                st.download_button(
                    "Télécharger Markdown", f.read(), file_name="results.md"
                )

    st.markdown("### 🌐 API REST (FastAPI)")
    st.info("Lancer l'API REST : `uvicorn api_rest:app --reload` (terminal)")

    # --- Visualisation avancée : importance des paramètres (feature importance) ---
    st.markdown("#### 🧠 Importance des paramètres sur la performance")
    if os.path.exists(sim_dir):
        sim_files = [f for f in os.listdir(sim_dir) if f.endswith(".csv")]
        if sim_files:
            sim_dfs = [pd.read_csv(os.path.join(sim_dir, f)) for f in sim_files]
            sim_df = pd.concat(sim_dfs, ignore_index=True)
    if sim_df is not None:
        try:
            from sklearn.linear_model import LinearRegression

            try:
                import numpy as np
            except ImportError:
                st.error(
                    "Le module 'numpy' n'est pas installé. Installez-le avec : pip install numpy"
                )
                raise
            exclude_cols = {"run", "seed", "best_fitness"}
            feat_cols = [
                col
                for col in sim_df.select_dtypes(include=["number"]).columns
                if col not in exclude_cols
            ]
            if len(feat_cols) >= 2:
                X = sim_df[feat_cols].values
                y = sim_df["best_fitness"].values
                y = np.asarray(y)
                model = LinearRegression()
                model.fit(X, y)
                try:
                    import plotly.express as px
                except ImportError:
                    st.error(
                        "Le module 'plotly' n'est pas installé. Installez-le avec : pip install plotly"
                    )
                    raise
                importance = np.abs(model.coef_)
                fig_imp = px.bar(
                    x=feat_cols,
                    y=importance,
                    labels={"x": "Paramètre", "y": "Importance absolue"},
                    title="Importance des paramètres (régression linéaire)",
                )
                st.plotly_chart(fig_imp, width="stretch")
            else:
                st.info(
                    "Pas assez de paramètres numériques pour calculer l'importance."
                )
        except Exception as e:
            st.warning(f"Erreur lors du calcul de l'importance des paramètres : {e}")
    st.markdown("#### ☁️ Export direct vers Dropbox")
    dropbox_token = st.text_input("Dropbox Access Token", type="password")
    if st.button("Exporter tous les rapports sur Dropbox"):
        try:
            import dropbox

            dbx = dropbox.Dropbox(dropbox_token)
            files_to_export = [
                "rapport_simulations.pdf",
                "rapport_simulation.html",
                "rapport_simulations.xlsx",
            ]
            uploaded = []
            for f in files_to_export:
                if os.path.exists(f):
                    with open(f, "rb") as file_data:
                        dbx.files_upload(
                            file_data.read(),
                            f"/{f}",
                            mode=dropbox.files.WriteMode.overwrite,
                        )
                    uploaded.append(f)
            if uploaded:
                st.success(f"Fichiers uploadés sur Dropbox : {', '.join(uploaded)}")
            else:
                st.warning("Aucun rapport à uploader trouvé dans le dossier courant.")
        except ImportError:
            st.error(
                "Le module 'dropbox' n'est pas installé. Installez-le avec : pip install dropbox"
            )
            st.info(
                "Pour activer l'export Dropbox, ouvrez un terminal et exécutez : pip install dropbox"
            )

    # --- Export direct vers Azure Blob Storage ---
    st.markdown("#### ☁️ Export direct vers Azure Blob Storage")
    azure_conn_str = st.text_input("Azure Storage connection string", type="password")
    azure_container = st.text_input("Nom du conteneur Azure", value="simu-exports")
    if st.button("Exporter tous les rapports sur Azure Blob"):
        try:
            from azure.storage.blob import BlobServiceClient

            try:
                blob_service_client = BlobServiceClient.from_connection_string(
                    azure_conn_str
                )
                container_client = blob_service_client.get_container_client(
                    azure_container
                )
                container_client.create_container()
                files_to_export = [
                    "rapport_simulations.pdf",
                    "rapport_simulation.html",
                    "rapport_simulations.xlsx",
                ]
                uploaded = []
                for f in files_to_export:
                    if os.path.exists(f):
                        with open(f, "rb") as data:
                            container_client.upload_blob(f, data, overwrite=True)
                        uploaded.append(f)
                if uploaded:
                    st.success(
                        f"Fichiers uploadés sur Azure Blob : {', '.join(uploaded)}"
                    )
                else:
                    st.warning(
                        "Aucun rapport à uploader trouvé dans le dossier courant."
                    )
            except Exception as e:
                st.error(f"Erreur lors de l'upload Azure Blob : {e}")
        except ImportError:
            st.error(
                "Le module 'azure-storage-blob' n'est pas installé. Installez-le avec : pip install azure-storage-blob"
            )
            st.info(
                "Pour activer l'export Azure Blob, ouvrez un terminal et exécutez : pip install azure-storage-blob"
            )

    # --- Export direct vers un serveur FTP ---
    st.markdown("#### ☁️ Export direct vers un serveur FTP")
    ftp_host = st.text_input("Adresse du serveur FTP", value="ftp.monsite.com")
    ftp_user = st.text_input("Utilisateur FTP", value="user")
    ftp_pass = st.text_input("Mot de passe FTP", type="password")
    if st.button("Exporter tous les rapports sur FTP"):
        try:
            from ftplib import FTP

            ftp = FTP(ftp_host)
            ftp.login(ftp_user, ftp_pass)
            files_to_export = [
                "rapport_simulations.pdf",
                "rapport_simulation.html",
                "rapport_simulations.xlsx",
            ]
            uploaded = []
            for f in files_to_export:
                if os.path.exists(f):
                    with open(f, "rb") as file_data:
                        ftp.storbinary(f"STOR {f}", file_data)
                    uploaded.append(f)
            ftp.quit()
            if uploaded:
                st.success(f"Fichiers uploadés sur FTP : {', '.join(uploaded)}")
            else:
                st.warning("Aucun rapport à uploader trouvé dans le dossier courant.")
        except Exception as e:
            st.error(f"Erreur lors de l'upload FTP : {e}")

    # --- Export direct vers Google Drive ---
    st.markdown("#### ☁️ Export direct vers Google Drive")
    st.info(
        "Pour utiliser cette fonction, placez un fichier client_secrets.json dans le dossier courant (instructions dans la doc Google Drive API). La première utilisation ouvrira une fenêtre d’authentification."
    )
    if st.button("Exporter tous les rapports sur Google Drive"):
        try:
            from pydrive2.auth import GoogleAuth
            from pydrive2.drive import GoogleDrive

            try:
                gauth = GoogleAuth()
                gauth.LocalWebserverAuth()
                drive = GoogleDrive(gauth)
                files_to_export = [
                    "rapport_simulations.pdf",
                    "rapport_simulation.html",
                    "rapport_simulations.xlsx",
                ]
                uploaded = []
                for f in files_to_export:
                    if os.path.exists(f):
                        gfile = drive.CreateFile({"title": f})
                        gfile.SetContentFile(f)
                        gfile.Upload()
                        uploaded.append(f)
                if uploaded:
                    st.success(
                        f"Fichiers uploadés sur Google Drive : {', '.join(uploaded)}"
                    )
                else:
                    st.warning(
                        "Aucun rapport à uploader trouvé dans le dossier courant."
                    )
            except Exception as e:
                st.error(f"Erreur lors de l'upload Google Drive : {e}")
        except ImportError:
            st.error(
                "Le module 'pydrive2' n'est pas installé. Installez-le avec : pip install pydrive2"
            )
            st.info(
                "Pour activer l'export Google Drive, ouvrez un terminal et exécutez : pip install pydrive2"
            )

    # --- Export direct vers Amazon S3 ---
    st.markdown("#### ☁️ Export direct vers Amazon S3")
    s3_bucket = st.text_input("Nom du bucket S3", value="mon-bucket-simu")
    aws_access_key = st.text_input("AWS Access Key ID", type="password")
    aws_secret_key = st.text_input("AWS Secret Access Key", type="password")
    if st.button("Exporter tous les rapports sur S3"):
        try:
            import boto3

            try:
                session = boto3.Session(
                    aws_access_key_id=aws_access_key,
                    aws_secret_access_key=aws_secret_key,
                )
                s3 = session.client("s3")
                files_to_export = [
                    "rapport_simulations.pdf",
                    "rapport_simulation.html",
                    "rapport_simulations.xlsx",
                ]
                uploaded = []
                for f in files_to_export:
                    if os.path.exists(f):
                        s3.upload_file(f, s3_bucket, f)
                        uploaded.append(f)
                if uploaded:
                    st.success(
                        f"Fichiers uploadés sur S3 bucket {s3_bucket} : {', '.join(uploaded)}"
                    )
                else:
                    st.warning(
                        "Aucun rapport à uploader trouvé dans le dossier courant."
                    )
            except Exception as e:
                st.error(f"Erreur lors de l'upload S3 : {e}")
        except ImportError:
            st.error(
                "Le module 'boto3' n'est pas installé. Installez-le avec : pip install boto3"
            )
            st.info(
                "Pour activer l'export Amazon S3, ouvrez un terminal et exécutez : pip install boto3"
            )

    # --- Export cloud local ---
    st.markdown("#### ☁️ Export automatique vers un dossier cloud")
    cloud_dir = st.text_input(
        "Dossier cloud local (OneDrive, Google Drive, Dropbox...)",
        value="C:/Users/WINDOWS/OneDrive/SimuExports",
    )
    if st.button("Exporter tous les rapports dans le cloud"):
        try:
            import shutil
        except ImportError:
            st.error("Le module 'shutil' est manquant (standard Python).")
            raise
        os.makedirs(cloud_dir, exist_ok=True)
        files_to_export = [
            "rapport_simulations.pdf",
            "rapport_simulation.html",
            "rapport_simulations.xlsx",
        ]
        exported = []
        for f in files_to_export:
            if os.path.exists(f):
                shutil.copy(f, os.path.join(cloud_dir, f))
                exported.append(f)
        if exported:
            st.success(f"Fichiers exportés dans {cloud_dir} : {', '.join(exported)}")
        else:
            st.warning("Aucun rapport à exporter trouvé dans le dossier courant.")

    # --- Analyse automatique des corrélations et suggestions ---
    st.markdown("#### 🤖 Corrélations significatives & suggestions d’optimisation")
    if sim_df is not None:
        exclude_cols = {"run", "seed"}
        num_cols = [
            col
            for col in sim_df.select_dtypes(include=["number"]).columns
            if col not in exclude_cols
        ]
        if "best_fitness" in num_cols:
            num_cols.remove("best_fitness")
        corrs = {}
        for col in num_cols:
            corr = sim_df[[col, "best_fitness"]].corr().iloc[0, 1]
            corrs[col] = corr
        # Filtrer corrélations significatives
        strong_corrs = {k: v for k, v in corrs.items() if abs(v) > 0.5}
        if strong_corrs:
            st.write("**Corrélations fortes (|corr| > 0.5) avec la performance :**")
            for k, v in sorted(strong_corrs.items(), key=lambda x: -abs(x[1])):
                st.write(
                    f"- {k} : corr = {v:.2f} {'(positif)' if v>0 else '(négatif)'}"
                )
            st.write("**Suggestions d’optimisation :**")
            for k, v in strong_corrs.items():
                if v > 0:
                    st.write(f"→ Augmenter {k} pourrait améliorer la performance.")
                else:
                    st.write(f"→ Diminuer {k} pourrait améliorer la performance.")
        else:
            st.info(
                "Aucune corrélation forte détectée entre les hyperparamètres et la performance."
            )

    # --- Suivi des hyperparamètres : impact sur la performance ---
    st.markdown("#### 🧮 Impact des hyperparamètres sur la performance")
    hyperparams = [
        "elite_ratio",
        "mutation_base",
        "stagnation_patience",
        "pop_size",
        "n_generations",
    ]
    import plotly.express as px

    if sim_df is not None:
        for hp in hyperparams:
            if hp in sim_df.columns:
                fig_hp = px.scatter(
                    sim_df,
                    x=hp,
                    y="best_fitness",
                    trendline="ols",
                    title=f"Impact de {hp} sur best_fitness",
                )
                st.plotly_chart(fig_hp, width="stretch")
        import subprocess
        from pathlib import Path
    st.markdown("### 📂 Sélection du fichier à visualiser")
    # Ne recharge pas selected_file/df ici, déjà fait dans tab1


# --- Recherche par ID ---
with st.container():
    st.markdown("### 🔎 Recherche par ID de stratégie")
    if "id" in df.columns:
        search_id = st.text_input("Recherche par ID de stratégie :", "")
        if search_id:
            filtered_id = df[df["id"].astype(str).str.contains(search_id)]
            st.success(
                f"Résultats pour l'ID '{search_id}' : {len(filtered_id)} trouvé(s)"
            )
            st.dataframe(filtered_id, width="stretch")
            if not filtered_id.empty:
                st.markdown("#### 🧬 Détails de la stratégie sélectionnée")
                row = filtered_id.iloc[0]
                st.json(row.to_dict())


# --- Filtre par espèce ---
with st.container():
    st.markdown("### 🐾 Filtres avancés")
    species_list = df["species"].unique() if "species" in df.columns else []
    col1, col2, col3 = st.columns(3)
    # Filtre par espèce
    if len(species_list) > 1:
        with col1:
            selected_species = st.multiselect(
                "Espèce :", options=species_list, default=list(species_list)
            )
            df = df[df["species"].isin(selected_species)]
    # Filtre par fitness
    if "fitness" in df.columns:
        with col2:
            min_f, max_f = float(df["fitness"].min()), float(df["fitness"].max())
            fitness_range = st.slider(
                "Fitness :", min_value=min_f, max_value=max_f, value=(min_f, max_f)
            )
            df = df[
                (df["fitness"] >= fitness_range[0])
                & (df["fitness"] <= fitness_range[1])
            ]
    # Filtre par TP/SL
    if "exit.tp" in df.columns and "exit.sl" in df.columns:
        with col3:
            min_tp, max_tp = float(df["exit.tp"].min()), float(df["exit.tp"].max())
            min_sl, max_sl = float(df["exit.sl"].min()), float(df["exit.sl"].max())
            tp_range = st.slider(
                "Take Profit :",
                min_value=min_tp,
                max_value=max_tp,
                value=(min_tp, max_tp),
            )
            sl_range = st.slider(
                "Stop Loss :",
                min_value=min_sl,
                max_value=max_sl,
                value=(min_sl, max_sl),
            )
            df = df[
                (df["exit.tp"] >= tp_range[0])
                & (df["exit.tp"] <= tp_range[1])
                & (df["exit.sl"] >= sl_range[0])
                & (df["exit.sl"] <= sl_range[1])
            ]

        # Filtres supplémentaires : environnement, génération, drawdown, sharpe
        extra_cols = []
        if "environment" in df.columns:
            extra_cols.append("environment")
        if "generation" in df.columns:
            extra_cols.append("generation")
        if "drawdown" in df.columns:
            extra_cols.append("drawdown")
        if "sharpe" in df.columns:
            extra_cols.append("sharpe")
        if extra_cols:
            with st.expander("Filtres supplémentaires"):
                for col in extra_cols:
                    if df[col].dtype == "O":
                        vals = df[col].unique()
                        selected = st.multiselect(
                            f"{col}", options=vals, default=list(vals)
                        )
                        df = df[df[col].isin(selected)]
                    else:
                        min_v, max_v = float(df[col].min()), float(df[col].max())
                        val_range = st.slider(
                            f"{col}",
                            min_value=min_v,
                            max_value=max_v,
                            value=(min_v, max_v),
                        )
                        df = df[(df[col] >= val_range[0]) & (df[col] <= val_range[1])]
# --- Histogramme interactif de fitness ---
with st.container():
    st.markdown("### 📈 Histogramme des valeurs de fitness")
    if "fitness" in df.columns:
        try:
            import plotly.express as px
        except ImportError:
            st.error(
                "Le module 'plotly' n'est pas installé. Installez-le avec : pip install plotly"
            )
        else:
            fig = px.histogram(
                df,
                x="fitness",
                nbins=30,
                title="Distribution du fitness",
                color="species" if "species" in df.columns else None,
            )
            st.plotly_chart(fig, width="stretch")

# --- Scatter plot personnalisable ---
with st.container():
    st.markdown("### 🎯 Scatter plot personnalisable")
    num_cols = [
        col
        for col in df.select_dtypes(include=["number"]).columns
        if col not in {"id", "generation"}
    ]
    if len(num_cols) >= 2:
        colx = st.selectbox("Axe X :", num_cols, index=0, key="selectbox_axex")
        coly = st.selectbox("Axe Y :", num_cols, index=1, key="selectbox_axey")
        color_col = st.selectbox(
            "Couleur :",
            [None] + num_cols + (["species"] if "species" in df.columns else []),
            index=0,
            key="selectbox_color",
        )
        try:
            import plotly.express as px
        except ImportError:
            st.error(
                "Le module 'plotly' n'est pas installé. Installez-le avec : pip install plotly"
            )
        else:
            fig = px.scatter(
                df,
                x=colx,
                y=coly,
                color=color_col if color_col else None,
                hover_data=["id"] if "id" in df.columns else None,
                title=f"Scatter plot : {colx} vs {coly}",
            )
            st.plotly_chart(fig, width="stretch")
    else:
        st.info("Pas assez de colonnes numériques pour le scatter plot.")


# --- Export CSV du DataFrame filtré ---
with st.container():
    st.markdown("### 💾 Export du DataFrame filtré")
    st.download_button(
        label="💾 Télécharger le CSV filtré",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"filtered_{selected_file}",
        mime="text/csv",
    )

    # Export Excel et JSON
    import io

    excel_buf = io.BytesIO()
    df.to_excel(excel_buf, index=False)
    st.download_button(
        label="⬇️ Télécharger Excel filtré",
        data=excel_buf.getvalue(),
        file_name=f"filtered_{selected_file.replace('.csv','.xlsx')}",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.download_button(
        label="⬇️ Télécharger JSON filtré",
        data=df.to_json(orient="records").encode("utf-8"),
        file_name=f"filtered_{selected_file.replace('.csv','.json')}",
        mime="application/json",
    )


# Visualisation 3D si colonnes présentes
with st.container():
    st.markdown("### 🌐 Visualisation 3D des stratégies")
    if all(col in df.columns for col in ["exit.tp", "exit.sl", "fitness", "species"]):
        try:
            import plotly.express as px
        except ImportError:
            st.error(
                "Le module 'plotly' n'est pas installé. Installez-le avec : pip install plotly"
            )
        else:
            fig = px.scatter_3d(
                df,
                x="exit.tp",
                y="exit.sl",
                z="fitness",
                color="species",
                symbol="species",
                hover_data=["id", "environment", "fitness"],
                title="Stratégies (3D) par espèce",
            )
            st.plotly_chart(fig, width="stretch")
    else:
        st.info("Colonnes nécessaires manquantes pour la 3D.")


# Statistiques par espèce
with st.container():
    st.markdown("### 📊 Répartition par espèce")
    if "species" in df.columns:
        st.bar_chart(df["species"].value_counts())


# Affichage des meilleurs individus et heatmap
with st.container():
    st.markdown("### 🏆 Top 5 stratégies (fitness)")
    if "fitness" in df.columns:
        st.dataframe(
            df.sort_values("fitness", ascending=False).head(5), width="stretch"
        )
        # Affichage détaillé d'un individu sélectionné dans le top 5
        top5 = df.sort_values("fitness", ascending=False).head(5)
        if not top5.empty:
            selected_idx = st.selectbox(
                "Afficher les détails d'une stratégie du top 5 :",
                top5["id"].astype(str),
                key="selectbox_top5_detail",
            )
            selected_row = top5[top5["id"].astype(str) == selected_idx].iloc[0]
            st.markdown("#### 🧬 Détails de la stratégie (top 5)")
            st.json(selected_row.to_dict())

        # --- Nouvelle section : Heatmap de corrélation (top N) ---
        st.markdown("### 🔥 Heatmap de corrélation des paramètres (top N)")
        top_n = st.slider(
            "Nombre de stratégies à inclure dans la heatmap :",
            min_value=5,
            max_value=min(100, len(df)),
            value=20,
        )
        topn_df = df.sort_values("fitness", ascending=False).head(top_n)
        exclude_cols = {"id", "fitness", "species", "generation", "environment"}
        num_cols = [
            col
            for col in topn_df.select_dtypes(include=["number"]).columns
            if col not in exclude_cols
        ]
        if len(num_cols) >= 2:
            corr = topn_df[num_cols].corr()
            try:
                import numpy as np
                import plotly.express as px
            except ImportError:
                st.warning(
                    "Le module 'plotly' ou 'numpy' n'est pas installé. Installez-les avec : pip install plotly numpy. Affichage matplotlib en secours."
                )
                try:
                    import matplotlib.pyplot as plt
                    import seaborn as sns
                except ImportError:
                    st.error(
                        "Les modules 'matplotlib' et 'seaborn' sont nécessaires pour l'affichage de la heatmap de secours. Installez-les avec : pip install matplotlib seaborn"
                    )
                else:
                    fig, ax = plt.subplots(figsize=(8, 6))
                    sns.heatmap(corr, annot=True, cmap="RdBu", center=0, ax=ax)
                    st.pyplot(fig)
            else:
                fig = px.imshow(
                    corr,
                    text_auto=True,
                    color_continuous_scale="RdBu",
                    zmin=-1,
                    zmax=1,
                    aspect="auto",
                    title="Matrice de corrélation (top N)",
                )
                st.plotly_chart(fig, width="stretch")
        else:
            st.info(
                "Pas assez de colonnes numériques pour afficher une heatmap de corrélation."
            )

            # --- Nouvelle section : Pairplot interactif ---
            st.markdown("### 🔗 Pairplot interactif des paramètres (top N)")
            with st.expander("Configurer le pairplot interactif"):
                pairplot_vars = st.multiselect(
                    "Variables à inclure dans le pairplot (min 2)",
                    num_cols,
                    default=num_cols[: min(4, len(num_cols))],
                )
                pairplot_lib = st.radio(
                    "Bibliothèque de visualisation",
                    ["Seaborn (statique)", "Plotly (interactif)"],
                    index=1,
                )
            if len(pairplot_vars) >= 2:
                st.info(f"Pairplot sur : {', '.join(pairplot_vars)}")
                if pairplot_lib == "Seaborn (statique)":
                    try:
                        import matplotlib.pyplot as plt
                        import seaborn as sns
                    except ImportError:
                        st.error(
                            "Les modules 'seaborn' et 'matplotlib' sont nécessaires pour le pairplot statique. Installez-les avec : pip install seaborn matplotlib"
                        )
                    else:
                        fig = sns.pairplot(topn_df[pairplot_vars], diag_kind="kde")
                        # st.pyplot attend une Figure matplotlib, pas un PairGrid
                        if hasattr(fig, "fig"):
                            st.pyplot(fig.fig)
                        else:
                            try:
                                from matplotlib.figure import \
                                    Figure as MplFigure
                            except ImportError:
                                MplFigure = None
                            if MplFigure is not None and isinstance(fig, MplFigure):
                                st.pyplot(fig)
                else:
                    try:
                        import plotly.express as px
                    except ImportError:
                        st.error(
                            "Le module 'plotly' n'est pas installé. Installez-le avec : pip install plotly"
                        )
                    else:
                        fig = px.scatter_matrix(
                            topn_df,
                            dimensions=pairplot_vars,
                            color=None,
                            title="Pairplot interactif (Plotly)",
                            height=600,
                        )
                        fig.update_traces(diagonal_visible=True)
                        st.plotly_chart(fig, width="stretch")
            else:
                st.warning(
                    "Veuillez sélectionner au moins 2 variables numériques pour le pairplot."
                )


# --- Courbe d'évolution du meilleur fitness ---
with st.container():
    st.markdown("### 📈 Évolution du meilleur fitness (toutes générations)")
    fitness_evolution = []
    gen_numbers = []
    all_species_counts = []
    for f in sorted(csv_files):
        try:
            d = pd.read_csv(os.path.join(results_dir, f))
            if "fitness" in d.columns:
                fitness_evolution.append(d["fitness"].max())
                gen_num = "".join(filter(str.isdigit, f))
                gen_numbers.append(int(gen_num) if gen_num else len(gen_numbers))
            if "species" in d.columns:
                all_species_counts.append(d["species"].value_counts())
            else:
                all_species_counts.append(pd.Series())
        except Exception:
            fitness_evolution.append(None)
            gen_numbers.append(len(gen_numbers))
            all_species_counts.append(pd.Series())
    if fitness_evolution:
        chart_df = pd.DataFrame(
            {"Génération": gen_numbers, "Best fitness": fitness_evolution}
        )
        st.line_chart(chart_df.set_index("Génération"))


# --- Courbe d'évolution du nombre d'individus par espèce ---
with st.container():
    st.markdown("### 🧬 Évolution du nombre d'individus par espèce")
    if any(len(s) > 0 for s in all_species_counts):
        # Synchronisation des longueurs pour éviter ValueError
        min_len = min(len(all_species_counts), len(gen_numbers))
        area_df = pd.DataFrame(all_species_counts[:min_len]).fillna(0).astype(int)
        area_df.index = gen_numbers[:min_len]
        st.area_chart(area_df)


# --- Téléchargement du top 5 ---
with st.container():
    st.markdown("### ⬇️ Télécharger le top 5")
    if "fitness" in df.columns:
        top5 = df.sort_values("fitness", ascending=False).head(5)
        st.download_button(
            label="⬇️ Télécharger le top 5 (CSV)",
            data=top5.to_csv(index=False).encode("utf-8"),
            file_name=f"top5_{selected_file}",
            mime="text/csv",
        )

# --- Comparatif multi-simulations ---
with st.container():
    st.markdown("### 📊 Comparatif multi-simulations")
    sim_dir = "sim_summaries"
    if os.path.exists(sim_dir):
        sim_files = [f for f in os.listdir(sim_dir) if f.endswith(".csv")]
        if sim_files:
            sim_dfs = [pd.read_csv(os.path.join(sim_dir, f)) for f in sim_files]
            sim_df = pd.concat(sim_dfs, ignore_index=True)
            st.dataframe(sim_df)
            # Bar chart des meilleurs fitness
            st.markdown("#### 🏅 Meilleur fitness par simulation")
            st.bar_chart(sim_df.set_index("run")["best_fitness"])
            # Boxplot des meilleurs fitness
            import plotly.express as px

            fig_box = px.box(
                sim_df,
                y="best_fitness",
                points="all",
                title="Distribution des meilleurs fitness (boxplot)",
            )
            st.plotly_chart(fig_box, width="stretch")
            # Scatter plot best_fitness vs std_fitness
            fig = px.scatter(
                sim_df,
                x="std_fitness",
                y="best_fitness",
                hover_data=["run", "seed"],
                title="Best fitness vs Std fitness",
            )
            st.plotly_chart(fig, width="stretch")
            # Téléchargement groupé des meilleurs individus
            csv = sim_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="⬇️ Télécharger tous les meilleurs individus (CSV)",
                data=csv,
                file_name="all_best_individuals.csv",
                mime="text/csv",
            )

            # Heatmap de corrélation globale sur tous les meilleurs individus
            # --- Génération et téléchargement du rapport PDF ---
            st.markdown("#### 📄 Rapport PDF synthétique")
            # from pathlib import Path
            # import subprocess
            pdf_path = Path("rapport_simulations.pdf")
            if st.button("Générer le rapport PDF"):
                with st.spinner("Génération du rapport PDF en cours..."):
                    result = subprocess.run(
                        ["python", "generate_report.py"], capture_output=True, text=True
                    )
                    if pdf_path.exists():
                        st.success("Rapport PDF généré !")
                    else:
                        st.error("Erreur lors de la génération du rapport PDF.")
                        st.text(result.stdout + "\n" + result.stderr)
            if pdf_path.exists():
                with open(pdf_path, "rb") as f:
                    st.download_button(
                        label="⬇️ Télécharger le rapport PDF",
                        data=f.read(),
                        file_name="rapport_simulations.pdf",
                        mime="application/pdf",
                    )
            st.markdown(
                "#### 🔥 Heatmap de corrélation (meilleurs individus de chaque run)"
            )
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
                col
                for col in sim_df.select_dtypes(include=["number"]).columns
                if col not in exclude_cols
            ]
            if len(num_cols) >= 2:
                corr = sim_df[num_cols].corr()
                try:
                    import plotly.express as px
                except ImportError:
                    st.error(
                        "Le module 'plotly' n'est pas installé. Installez-le avec : pip install plotly"
                    )
                else:
                    fig = px.imshow(
                        corr,
                        text_auto=True,
                        color_continuous_scale="RdBu",
                        zmin=-1,
                        zmax=1,
                        aspect="auto",
                        title="Corrélation des paramètres (meilleurs individus)",
                    )
                    st.plotly_chart(fig, width="stretch")
            else:
                st.info(
                    "Pas assez de colonnes numériques pour afficher une heatmap de corrélation."
                )
        else:
            st.info("Aucun résumé de simulation trouvé dans sim_summaries/.")
    else:
        st.info(
            "Dossier sim_summaries/ introuvable. Lancez run_multi_simulations.py pour générer des runs."
        )
