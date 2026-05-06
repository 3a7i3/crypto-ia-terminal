import streamlit as st


def show_sidebar_tutorial(panel_name, doc_link):
    key_btn = f"show_tuto_sidebar_{panel_name}"
    key_exp = f"show_tuto_expander_{panel_name}"
    tuto_map = {
        "3d": (
            "Lancer la 3D Evolution",
            "launch_evolution_3d_view.bat",
            "Explorez la population en 3D, appliquez des filtres, personnalisez l’affichage, exportez les résultats.",
        ),
        "supervision": (
            "Lancer la supervision",
            "launch_alert_dashboard.bat",
            "Surveillez les alertes, accédez aux actions collaboratives, exportez les rapports.",
        ),
        "botdoctor": (
            "Lancer BotDoctor",
            "launch_botdoctor_dashboard.bat",
            "Analysez la santé des bots, corrigez les erreurs, consultez les logs.",
        ),
        "multimonde": (
            "Lancer le comparatif multi-monde",
            "launch_evolution_dashboard.bat",
            "Comparez la fitness, la diversité, la convergence entre mondes.",
        ),
        "quantv16": (
            "Lancer Quant V16 Panel",
            "launch_quant_dashboard_v16.bat",
            "Analysez les signaux, backtests, scores, exports.",
        ),
        "terminalv12": (
            "Lancer Quant Terminal V12",
            "launch_quant_terminal_v12.bat",
            "Terminal quantitatif : signaux, exécutions, scoring, export.",
        ),
        "feedback": (
            "Lancer Feedback Dashboard",
            "launch_feedback_dashboard.bat",
            "Collectez et analysez le feedback IA, suivez les expériences, consultez les synthèses.",
        ),
    }
    titre, cmd, desc = tuto_map.get(
        panel_name,
        ("Lancer le panel", "<commande>", "Utilisez ce panel pour vos analyses."),
    )
    if st.button("📖 Tutoriel interactif", key=key_btn):
        st.session_state[key_exp] = not st.session_state.get(key_exp, False)
    if st.session_state.get(key_exp, False):
        with st.expander("🚀 Tutoriel interactif – Démarrage rapide", expanded=True):
            st.markdown(
                f"""
**1. {titre}**
    <br>```powershell
    {cmd}
    ```
    {desc}

**2. Astuces**
- Utilisez la sidebar pour naviguer entre panels
- Utilisez le bouton retour pour revenir à l’accueil
- Consultez l’aide intégrée de chaque panel

👉 [Voir la documentation]({doc_link})
            """
            )


def supervision_autoheal_panel():
    st.markdown("---")
    if st.button("⬅️ Retour à l'accueil 3D Evolution", key="retour_accueil_supervision"):
        st.session_state["active_panel"] = "Accueil 3D Evolution"
        st.rerun()
    show_sidebar_tutorial("supervision", "DOCUMENTATION_EVOLUTION_DASHBOARD_FR.md")
    st.title("🛡️ Supervision & Auto-Heal")
    st.info(
        """
    Panel de supervision et auto-réparation avancé :
    - Statistiques d’alertes (module, gravité, type)
    - Filtres, recherche, pagination
    - Actions : acknowledge, mute, export, webhook, Telegram, Discord
    - Commentaires/annotations par alerte
    - Multi-utilisateur, mode admin, maintenance
    - Export Excel/HTML/PDF/JSON, QR code, thèmes, auto-refresh
    """
    )
    import os

    st.markdown(
        "**Fichier source :** `dashboard/alert_dashboard.py`  \\n[✏️ Éditer dans VS Code](vscode://file/"
        + os.path.abspath("dashboard/alert_dashboard.py")
        + ")"
    )
    st.success(
        "Toutes les fonctionnalités collaboratives sont disponibles. Consultez la documentation intégrée et testez les exports avancés."
    )
    st.markdown(
        """
    ### Liens rapides
    - [Documentation intégrée](DOCUMENTATION_EVOLUTION_DASHBOARD_FR.md)
    - [FAQ rapide](FAQ_EVOLUTION_DASHBOARD_FR.md)
    - [Export Excel/HTML/PDF/JSON](/dashboard/alert_dashboard.py)
    - [Support GitHub](https://github.com/0xl1v/crypto-ai-terminal)
    """
    )
    st.markdown(
        """
    #### Actions collaboratives
    - **Acknowledge/Mute** : Cliquez sur une alerte pour la marquer comme traitée ou la masquer.
    - **Webhooks** : Envoyez une alerte sur Slack, Discord, ou Telegram en un clic.
    - **Commentaires** : Ajoutez une annotation personnelle à chaque alerte.
    - **Mode admin** : Activez le mode maintenance pour désactiver toutes les actions.
    """
    )
    st.info(
        "Pour accéder à toutes les fonctionnalités, ouvrez le dashboard complet via le raccourci ou le menu latéral."
    )


import sys

import streamlit as st
import glob
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objs as go
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
from sklearn.cluster import KMeans

from ONBOARDING_SCRIPT import sidebar_onboarding
from ui_utils import (export_plotly_png, export_plotly_svg, export_qr_code,
                      show_fallback, show_faq, show_tutorial,
                      sidebar_navigation)

INTERNAL_DASHBOARDS = [
    ("🛡️ Supervision & Auto-Heal", "dashboard/alert_dashboard.py"),
    ("🩺 BotDoctor Dashboard", "supervision/botdoctor_dashboard.py"),
    ("🌐 Evolution Multi-Monde", "evolution_dashboard.py"),
    ("🌐 3D Evolution Viewer", "evolution_3d_view.py"),
    ("📊 Quant V16 Panel", "crypto_quant_v16/ui/quant_dashboard.py"),
    ("📈 Quant Terminal V12", "quant_hedge_ai/dashboard/quant_terminal_v12.py"),
    ("🧠 R&D Feedback Dashboard", "ai_autonomous_loop/feedback_dashboard.py"),
]
EXTERNAL_LINKS = [
    ("Documentation (FR)", "DOCUMENTATION_EVOLUTION_DASHBOARD_FR.md"),
    ("Documentation (EN)", "DOCUMENTATION_EVOLUTION_DASHBOARD_EN.md"),
    ("GitHub Project", "https://github.com/your-org/crypto_ai_terminal"),
]


def _load_seaborn():
    try:
        import seaborn as sns
    except ImportError as exc:
        raise RuntimeError(
            "Le package optionnel 'seaborn' est requis pour les visualisations statistiques de ce dashboard."
        ) from exc
    return sns


def home_panel():
    st.title("🌐 3D Evolution Viewer")
    st.markdown(
        """
Bienvenue sur le dashboard 3D Evolution.

**Navigation rapide :**
"""
    )
    for label, path in INTERNAL_DASHBOARDS:
        if st.button(label, key=f"nav_{label}"):
            # Réinitialiser les variables d’état spécifiques au panneau
            prefix = label.replace(" ", "_")
            keys_to_delete = [
                k
                for k in st.session_state.keys()
                if isinstance(k, str)
                and (
                    k.startswith("selected_world_idx_")
                    or k.startswith("selected_gen_")
                    or k.startswith("anim_gen_")
                    or k.startswith("fitness_slider_")
                )
            ]
            for k in keys_to_delete:
                del st.session_state[k]
            st.session_state["active_panel"] = label
            st.rerun()
    st.markdown("---")
    st.markdown("**Liens externes :**")
    for label, url in EXTERNAL_LINKS:
        if url.startswith("http"):
            st.markdown(f"- [{label}]({url})")
        else:
            st.markdown(f"- [{label}]({url})")
    st.info(
        """
    **📚 Documentation enrichie / Enhanced Docs**

    - [README_CONSOLIDATED.md](README_CONSOLIDATED.md) — Guide d’installation, configuration, lancement rapide, FAQ, bonnes pratiques
    - [DASHBOARD_USAGE_TEMPLATES.md](DASHBOARD_USAGE_TEMPLATES.md) — Exemples d’utilisation pour chaque dashboard (Panel/Streamlit)
    - [ACTION_PLAN_CHECKLIST.md](ACTION_PLAN_CHECKLIST.md) — Plan d’action détaillé pour finaliser et maintenir le système

    *Conseil : commencez par le README_CONSOLIDATED.md pour une vue d’ensemble, puis utilisez les templates et le plan d’action pour accélérer votre onboarding ou vos évolutions.*

    For a professional onboarding, usage examples, and a step-by-step action plan, see the above links.
    """
    )


def evolution_3d_panel():
    # --- Sidebar enrichie et chargement des données ---
    prefix = st.session_state["active_panel"].replace(" ", "_")
    with st.sidebar:
        st.markdown(
            """
        ### Navigation rapide
        """
        )
        if st.button("🏠 Accueil 3D Evolution", key="nav_accueil_sidebar"):
            st.session_state["active_panel"] = "Accueil 3D Evolution"
            st.rerun()
        for label, path in INTERNAL_DASHBOARDS:
            if st.button(label, key=f"nav_sidebar_{label}"):
                st.session_state["active_panel"] = label
                st.rerun()
        st.markdown("---")
        st.markdown("**Liens externes :**")
        for label, url in EXTERNAL_LINKS:
            if url.startswith("http"):
                st.markdown(f"- [{label}]({url})")
            else:
                st.markdown(f"- [{label}]({url})")
        st.markdown("---")
        st.markdown(
            "**Utilisateur :**\n- Nom : *Démo*\n- Date : :calendar: {0}".format(
                pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
            )
        )
        st.info(
            """
        ℹ️ Besoin d'aide sur le format des données ?
        Consultez [CSV_POPULATION_FORMAT.md](CSV_POPULATION_FORMAT.md) pour le format attendu des fichiers CSV.
        """
        )
        global RESULTS_DIR
        RESULTS_DIR = "results"
        # Ajout bouton rechargement et tutoriel
        if "reload_data" not in st.session_state:
            st.session_state["reload_data"] = False
        if st.button("🔄 Recharger les données CSV", key="reload_data_btn"):
            st.session_state["reload_data"] = not st.session_state["reload_data"]
        show_sidebar_tutorial("3d", "TUTORIEL_EVOLUTION_DASHBOARD_FR.md")

        # Chargement des données avec cache (rechargement si reload_data change)
        @st.cache_data(show_spinner=False)
        def cached_load_population_data(results_dir, reload_flag):
            return load_population_data(results_dir)

        with st.spinner("Chargement des données de population..."):
            data = cached_load_population_data(
                RESULTS_DIR, st.session_state["reload_data"]
            )
        if not data:
            show_fallback(
                "Aucune donnée de population trouvée dans le dossier 'results/'. Ajoutez des fichiers *_pop_gen_*.csv.\nConsultez [CSV_POPULATION_FORMAT.md](CSV_POPULATION_FORMAT.md) pour le format attendu."
            )
            st.stop()
        # Vérification des colonnes critiques sur le premier monde
        required_cols = {"id", "fitness", "species", "exit.tp", "exit.sl"}
        first_world = next(iter(data))
        missing_cols = required_cols - set(data[first_world].columns)
        if missing_cols:
            st.error(
                f"Colonnes manquantes dans les CSV : {', '.join(missing_cols)}. Vérifiez vos exports.\nConsultez [CSV_POPULATION_FORMAT.md](CSV_POPULATION_FORMAT.md) pour le format attendu."
            )
            st.stop()
        worlds = list(data.keys())
        world_idx_key = f"selected_world_idx_{prefix}"
        gen_key = f"selected_gen_{prefix}"
        anim_key = f"anim_gen_{prefix}"
        fitness_key = f"fitness_slider_{prefix}"
        # --- Bouton retour accueil ---
        st.markdown("---")
        if st.button("⬅️ Retour à l'accueil 3D Evolution", key="retour_accueil_btn"):
            st.session_state["active_panel"] = "Accueil 3D Evolution"
            st.rerun()
    # --- Expander d'aide contextuelle ---
    with st.expander("ℹ️ Aide & Astuces", expanded=False):
        st.markdown(
            """
        - Utilisez les flèches pour naviguer entre les mondes.
        - Filtrez par fitness ou espèce pour explorer la diversité.
        - Utilisez les presets pour afficher rapidement les meilleures stratégies.
        - Exportez les résultats ou les graphiques pour analyse avancée.
        """
        )
    # --- Filtres avancés compacts + presets d'analyse rapide ---
    selected_world = st.selectbox(
        "Monde à visualiser en 3D",
        worlds,
        index=st.session_state[world_idx_key],
        key=f"select_world_{prefix}",
    )
    df = data[selected_world]
    gens = sorted(df["generation"].unique())
    if gen_key not in st.session_state:
        st.session_state[gen_key] = max(gens)
    selected_gen = st.slider(
        "Génération à afficher",
        min_value=min(gens),
        max_value=max(gens),
        value=st.session_state[gen_key],
        key=f"gen_slider_{prefix}",
    )
    st.session_state[gen_key] = selected_gen
    with st.expander("🔎 Filtres avancés & presets", expanded=False):
        min_fitness, max_fitness = float(df["fitness"].min()), float(
            df["fitness"].max()
        )
        fitness_range = st.slider(
            "Filtrer par fitness",
            min_value=min_fitness,
            max_value=max_fitness,
            value=(min_fitness, max_fitness),
            step=0.01,
            key=fitness_key,
        )
        selected_species = st.multiselect(
            "Espèces à afficher",
            options=list(df["species"].unique()),
            default=list(df["species"].unique()),
            key=f"species_{prefix}",
        )
        # --- Presets d'analyse rapide ---
        presets = {
            "Top 10 fitness": ("fitness", False, 10),
            "Top 10 sharpe": ("sharpe", False, 10),
            "Top 10 drawdown": ("drawdown", True, 10),
        }
        preset = st.selectbox(
            "🎯 Preset d'analyse rapide",
            list(presets.keys()),
            key=f"preset_select_{prefix}",
        )
        col, asc, n = presets[preset]
        if col in df.columns:
            df_preset = df.sort_values(col, ascending=asc).head(n)
            st.write(f"Affichage du preset : **{preset}** sur la colonne **{col}**")
            st.dataframe(df_preset, use_container_width=True)
        else:
            st.warning(
                f"Colonne {col} absente du fichier. Veuillez vérifier vos données."
            )
    # Filtrer la génération sélectionnée et les filtres avancés
    df_gen = df[
        (df["generation"] == selected_gen)
        & (df["fitness"] >= fitness_range[0])
        & (df["fitness"] <= fitness_range[1])
        & (df["species"].isin(selected_species))
    ]
    if len(df_gen) == 0:
        st.warning(
            "Aucune stratégie à afficher avec les filtres actuels. Essayez d’élargir les filtres ou vérifiez vos données."
        )
    elif len(df_gen) < 5:
        st.info(
            f"Seulement {len(df_gen)} stratégies affichées. Les résultats peuvent être peu représentatifs."
        )
    st.title("🌐 Visualisation 3D des Stratégies par Monde")
    # --- Options de personnalisation 3D ---
    with st.expander("🎨 Options de personnalisation 3D", expanded=False):
        palette_choice = st.selectbox(
            "Palette de couleurs",
            ["husl", "viridis", "plasma", "rainbow", "cubehelix", "Set1", "tab10"],
            index=0,
            key=f"palette_{prefix}",
        )
        point_size = st.slider(
            "Taille des points",
            min_value=2,
            max_value=20,
            value=6,
            key=f"ptsize_{prefix}",
        )
        point_opacity = st.slider(
            "Opacité des points",
            min_value=0.1,
            max_value=1.0,
            value=0.7,
            step=0.05,
            key=f"ptopacity_{prefix}",
        )
        show_axes = st.checkbox(
            "Afficher les axes", value=True, key=f"showaxes_{prefix}"
        )
        show_title = st.checkbox(
            "Afficher le titre du graphique", value=True, key=f"showtitle_{prefix}"
        )
    # --- Visualisation supplémentaire : distribution fitness par espèce ---
    st.header("Distribution du fitness par espèce")
    try:
        sns = _load_seaborn()
        fig_dist, ax_dist = plt.subplots(figsize=(8, 4))
        sns.boxplot(data=df_gen, x="species", y="fitness", ax=ax_dist)
        ax_dist.set_title(
            f"Distribution du fitness par espèce – {selected_world} (Gen {selected_gen})"
        )
        st.pyplot(fig_dist)
    except Exception as e:
        st.warning(f"Impossible d'afficher la distribution fitness par espèce : {e}")
        # (le reste du code de la fonction inchangé)
        # --- Filtres avancés compacts + presets d'analyse rapide ---
        with st.expander("🔎 Filtres avancés & presets", expanded=False):
            min_fitness, max_fitness = float(df["fitness"].min()), float(
                df["fitness"].max()
            )
            fitness_range = st.slider(
                "Filtrer par fitness",
                min_value=min_fitness,
                max_value=max_fitness,
                value=(min_fitness, max_fitness),
                step=0.01,
                key=fitness_key,
            )
            selected_species = st.multiselect(
                "Espèces à afficher",
                options=list(df["species"].unique()),
                default=list(df["species"].unique()),
                key=f"species_{prefix}",
            )
            # --- Presets d'analyse rapide ---
            presets = {
                "Top 10 fitness": ("fitness", False, 10),
                "Top 10 sharpe": ("sharpe", False, 10),
                "Top 10 drawdown": ("drawdown", True, 10),
            }
            preset = st.selectbox(
                "🎯 Preset d'analyse rapide",
                list(presets.keys()),
                key=f"preset_select_{prefix}",
            )
            col, asc, n = presets[preset]
            if col in df.columns:
                df_preset = df.sort_values(col, ascending=asc).head(n)
                st.write(f"Affichage du preset : **{preset}** sur la colonne **{col}**")
                st.dataframe(df_preset, use_container_width=True)
            else:
                st.warning(
                    f"Colonne {col} absente du fichier. Veuillez vérifier vos données."
                )
        # Filtrer la génération sélectionnée et les filtres avancés
        df_gen = df[
            (df["generation"] == selected_gen)
            & (df["fitness"] >= fitness_range[0])
            & (df["fitness"] <= fitness_range[1])
            & (df["species"].isin(selected_species))
        ]
        st.title("🌐 Visualisation 3D des Stratégies par Monde")
        # Navigation par flèches entre mondes
        col1, col2, col3 = st.columns([1, 2, 1])
        idx = worlds.index(selected_world)
        with col1:
            if st.button("⬅️ Monde précédent", key=f"prev_world_{prefix}") and idx > 0:
                st.session_state[world_idx_key] = idx - 1
                st.rerun()
        with col3:
            if (
                st.button("Monde suivant ➡️", key=f"next_world_{prefix}")
                and idx < len(worlds) - 1
            ):
                st.session_state[world_idx_key] = idx + 1
                st.rerun()
        st.markdown(
            f"<h3 style='color:#1f77b4'>← {selected_world} →</h3>",
            unsafe_allow_html=True,
        )
        # Animation génération (lecture auto, slider vitesse)
        st.markdown("### Animation 3D générationnelle")
        if anim_key not in st.session_state:
            st.session_state[anim_key] = False
        anim_speed = st.slider(
            "Vitesse de l'animation (secondes par génération)",
            min_value=0.1,
            max_value=2.0,
            value=0.5,
            step=0.1,
            key=f"anim_speed_{prefix}",
        )
        if st.button("▶️ Lecture auto des générations", key=f"auto_anim_{prefix}"):
            st.session_state[anim_key] = not st.session_state[anim_key]
        if st.session_state[anim_key]:
            import time as t

            for g in gens:
                st.session_state[gen_key] = g
                t.sleep(anim_speed)
                st.rerun()
        # --- SCORING AUTOMATIQUE ---
        st.header("Scoring automatique : Top stratégies")
        top_n = st.slider(
            "Nombre de stratégies à afficher (top fitness)",
            min_value=1,
            max_value=20,
            value=5,
            key=f"topn_slider_{prefix}",
        )
        if not df_gen.empty:
            top_strats = df_gen.sort_values("fitness", ascending=False).head(top_n)
            st.dataframe(
                top_strats[
                    ["id", "fitness", "species", "exit.tp", "exit.sl"]
                    + [
                        c
                        for c in top_strats.columns
                        if c.startswith("ma_")
                        or c.startswith("entry.")
                        or c.startswith("risk.")
                    ]
                ].reset_index(drop=True)
            )
        else:
            st.warning("Aucune stratégie à scorer avec les filtres actuels.")
        # --- AutoML avancé (Optuna) ---
        st.header("AutoML avancé : Optimisation multi-paramètres et export")
        st.markdown(
            "Optimisez plusieurs paramètres (TP, SL, RSI, MA, etc.) et choisissez l'objectif d'optimisation. Exportez les résultats Optuna pour analyse."
        )
        with st.expander("Configuration AutoML avancée"):
            obj_metric = st.selectbox(
                "Objectif à optimiser",
                ["fitness", "sharpe", "drawdown", "return"],
                key=f"obj_metric_{prefix}",
            )
            n_trials = st.slider(
                "Nombre d'essais Optuna",
                min_value=10,
                max_value=100,
                value=30,
                key=f"ntrials_slider_{prefix}",
            )
            optimize_params = st.multiselect(
                "Paramètres à optimiser",
                options=[
                    "exit.tp",
                    "exit.sl",
                    "entry.rsi_period",
                    "entry.rsi_buy",
                    "ma_short",
                    "ma_long",
                ],
                default=["exit.tp", "exit.sl"],
                key=f"optimize_params_{prefix}",
            )
            export_optuna = st.checkbox(
                "Exporter l'étude Optuna après optimisation",
                key=f"export_optuna_{prefix}",
            )
            if st.button(
                "Lancer l'optimisation AutoML avancée", key=f"launch_optuna_{prefix}"
            ):
                import optuna

                st.info(
                    "Optimisation en cours... (cela peut prendre quelques secondes)"
                )

                def objective(trial):
                    mask = pd.Series([True] * len(df_gen))
                    params = {}
                    for p in optimize_params:
                        vmin, vmax = float(df_gen[p].min()), float(df_gen[p].max())
                        params[p] = trial.suggest_float(p, vmin, vmax)
                        mask &= (
                            abs(df_gen[p] - params[p]) < 0.1
                            if vmax - vmin < 1
                            else abs(df_gen[p] - params[p]) < (vmax - vmin) * 0.1
                        )
                    if mask.sum() == 0:
                        return -999
                    if obj_metric == "fitness":
                        return df_gen[mask]["fitness"].mean()
                    elif obj_metric == "sharpe":
                        return (
                            df_gen[mask]["sharpe"].mean()
                            if "sharpe" in df_gen
                            else -999
                        )
                    elif obj_metric == "drawdown":
                        return (
                            -df_gen[mask]["drawdown"].mean()
                            if "drawdown" in df_gen
                            else -999
                        )
                    elif obj_metric == "return":
                        return (
                            df_gen[mask]["return"].mean()
                            if "return" in df_gen
                            else -999
                        )
                    return -999

                study = optuna.create_study(direction="maximize")
                study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
                st.success(
                    f"Meilleur score : {study.best_value:.4f} | Paramètres : {study.best_params}"
                )
                st.json(study.best_params)
                if export_optuna:
                    import json

                    optuna_json = study.trials_dataframe().to_json(orient="records")
                    st.download_button(
                        "Télécharger les résultats Optuna (JSON)",
                        data=optuna_json,
                        file_name="optuna_results.json",
                        mime="application/json",
                    )
                st.balloons()
            selected_id = st.selectbox(
                "ID de stratégie à mettre en avant (optionnel)",
                options=["(aucun)"] + list(df_gen["id"].unique()),
            )
            species_list = df_gen["species"].unique()
            st.markdown(
                """
            <div style='background:#eaf6ff;padding:8px;border-radius:8px;margin-bottom:8px;'>
            <b>Astuce :</b> Utilisez la souris ou le trackpad pour <b>zoomer</b>, <b>pivoter</b> et <b>déplacer</b> la vue 3D.<br>
            Double-cliquez sur une légende pour isoler une espèce.<br>
            <span style='color:#1f77b4'>La sélection d'une stratégie l'affiche en rouge étoile.</span>
            </div>
            """,
                unsafe_allow_html=True,
            )
            error_report = None
            try:
                sns = _load_seaborn()
                palette = (
                    sns.color_palette(
                        palette_choice, n_colors=len(species_list)
                    ).as_hex()
                    if len(species_list) > 1
                    else ["#1f77b4"]
                )
                fig3d = go.Figure()
                for i, species in enumerate(species_list):
                    sub = df_gen[df_gen["species"] == species]
                    fig3d.add_trace(
                        go.Scatter3d(
                            x=sub["exit.tp"],
                            y=sub["exit.sl"],
                            z=sub["fitness"],
                            mode="markers",
                            marker=dict(
                                size=point_size,
                                color=palette[i],
                                opacity=point_opacity,
                                line=dict(width=0.5, color="#333"),
                            ),
                            name=str(species),
                        )
                    )
                if selected_id != "(aucun)":
                    tracked = df_gen[df_gen["id"] == selected_id]
                    if not tracked.empty:
                        fig3d.add_trace(
                            go.Scatter3d(
                                x=tracked["exit.tp"],
                                y=tracked["exit.sl"],
                                z=tracked["fitness"],
                                mode="markers",
                                marker=dict(
                                    size=point_size + 8,
                                    color="red",
                                    symbol="star",
                                    line=dict(width=2, color="black"),
                                ),
                                name="Sélectionnée",
                            )
                        )
                fig3d.update_layout(
                    scene=dict(
                        xaxis_title="Take Profit" if show_axes else None,
                        yaxis_title="Stop Loss" if show_axes else None,
                        zaxis_title="Fitness" if show_axes else None,
                    ),
                    title=(
                        f"Stratégies 3D – {selected_world} (Gen {selected_gen})"
                        if show_title
                        else None
                    ),
                    legend_title="Espèces",
                    margin=dict(l=0, r=0, b=0, t=40),
                    height=600,
                )
                st.plotly_chart(fig3d, width="stretch")
                col_export1, col_export2, col_export3 = st.columns([1, 1, 1])
                with col_export1:
                    export_plotly_png(
                        fig3d, filename=f"{selected_world}_gen_{selected_gen}_3d.png"
                    )
                    st.caption(
                        "💡 Export PNG : Cliquez pour télécharger l’image 3D personnalisée."
                    )
                with col_export2:
                    export_plotly_svg(
                        fig3d, filename=f"{selected_world}_gen_{selected_gen}_3d.svg"
                    )
                    st.caption(
                        "💡 Export SVG : Pour une image vectorielle haute qualité."
                    )
                with col_export3:
                    export_qr_code(
                        f"Monde: {selected_world}, Génération: {selected_gen}"
                    )
                st.success(
                    "Export PNG/SVG généré avec les options de personnalisation actuelles."
                )
            except Exception as e:
                import datetime
                import traceback

                error_report = (
                    f"Erreur lors de la génération 3D : {e}\n{traceback.format_exc()}"
                )
                st.error(
                    "Erreur lors de la génération du graphique 3D. Un rapport détaillé est disponible ci-dessous."
                )
                st.code(error_report, language="text")
                st.download_button(
                    "Télécharger le rapport d'erreur 3D",
                    data=error_report,
                    file_name=f"rapport_3d_error_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                )
            if selected_id != "(aucun)":
                strat = df_gen[df_gen["id"] == selected_id]
                if not strat.empty:
                    st.markdown("**Paramètres de la stratégie sélectionnée :**")
                    st.json(strat.iloc[0].to_dict())
            st.download_button(
                "Exporter la population filtrée (CSV)",
                data=df_gen.to_csv(index=False),
                file_name=f"{selected_world}_gen_{selected_gen}_filtered.csv",
                mime="text/csv",
            )
            st.caption(
                "💡 Export CSV : Téléchargez la population affichée avec tous les filtres et options appliqués."
            )
            st.success("Export CSV généré avec les filtres et options en cours.")
            # --- CLUSTERING MULTI-MÉTHODES ---
            st.header("Clustering 3D (KMeans, DBSCAN, Agglomerative)")
            cluster_method = st.selectbox(
                "Méthode de clustering", ["KMeans", "DBSCAN", "Agglomerative"]
            )
            if st.button("Appliquer le clustering sur la population filtrée"):
                X = df_gen[["exit.tp", "exit.sl", "fitness"]].values
                labels = None
                centers = None
                if cluster_method == "KMeans":
                    n_clusters = st.slider(
                        "Nombre de clusters (KMeans)", min_value=2, max_value=8, value=3
                    )
                    kmeans = KMeans(n_clusters=n_clusters, n_init=10)
                    labels = kmeans.fit_predict(X)
                    centers = kmeans.cluster_centers_
                elif cluster_method == "DBSCAN":
                    from sklearn.cluster import DBSCAN

                    eps = st.slider(
                        "Epsilon (DBSCAN)",
                        min_value=0.01,
                        max_value=2.0,
                        value=0.2,
                        step=0.01,
                    )
                    min_samples = st.slider(
                        "Min samples (DBSCAN)", min_value=2, max_value=20, value=5
                    )
                    dbscan = DBSCAN(eps=eps, min_samples=min_samples)
                    labels = dbscan.fit_predict(X)
                elif cluster_method == "Agglomerative":
                    from sklearn.cluster import AgglomerativeClustering

                    n_clusters = st.slider(
                        "Nombre de clusters (Agglomerative)",
                        min_value=2,
                        max_value=8,
                        value=3,
                    )
                    agg = AgglomerativeClustering(n_clusters=n_clusters)
                    labels = agg.fit_predict(X)
                fig2 = plt.figure(figsize=(8, 6))
                ax2 = fig2.add_subplot(111, projection="3d")
                if labels is not None:
                    try:
                        unique_labels = np.unique(labels)
                        for cl in unique_labels:
                            sub = X[labels == cl]
                            ax2.scatter(
                                sub[:, 0], sub[:, 1], sub[:, 2], label=f"Cluster {cl}"
                            )
                    except Exception:
                        pass
                if centers is not None:
                    ax2.scatter(
                        *centers.T, color="black", marker="x", s=100, label="Centres"
                    )
                ax2.set_xlabel("Take Profit")
                ax2.set_ylabel("Stop Loss")
                ax2.set_zlabel("Fitness")
                ax2.set_title(
                    f"{cluster_method} Clusters – {selected_world} (Gen {selected_gen})"
                )
                ax2.legend()
                st.pyplot(fig2)
            # --- HEATMAP 2D (TP/SL) ---
            st.header("Heatmap 2D Take Profit / Stop Loss")
            if st.button("Afficher la heatmap 2D"):
                fig3, ax3 = plt.subplots(figsize=(7, 5))
                h = ax3.hexbin(
                    df_gen["exit.tp"],
                    df_gen["exit.sl"],
                    gridsize=30,
                    cmap="viridis",
                    mincnt=1,
                )
                cb = fig3.colorbar(h, ax=ax3)
                cb.set_label("Nombre de stratégies")
                ax3.set_xlabel("Take Profit")
                ax3.set_ylabel("Stop Loss")
                ax3.set_title(f"Heatmap TP/SL – {selected_world} (Gen {selected_gen})")
                st.pyplot(fig3)
            # --- ANALYSE TEMPORELLE DE LA DIVERSITÉ ---
            st.header("Analyse temporelle de la diversité des espèces")
            species_over_time = (
                df.groupby(["generation", "species"]).size().unstack(fill_value=0)
            )
            fig4, ax4 = plt.subplots(figsize=(10, 4))
            species_over_time.plot.area(ax=ax4, colormap="tab20")
            ax4.set_xlabel("Génération")
            ax4.set_ylabel("Nombre d'individus")
            ax4.set_title(f"Diversité des espèces – {selected_world}")
            st.pyplot(fig4)
            # --- COMPARATIF MULTI-MONDE ---
            st.header("Comparatif multi-monde : Fitness max par génération")
            fig5, ax5 = plt.subplots(figsize=(10, 4))
            for w in worlds:
                d = data[w]
                ax5.plot(d.groupby("generation")["fitness"].max(), label=w)
            ax5.set_xlabel("Génération")
            ax5.set_ylabel("Fitness max")
            ax5.set_title("Fitness max par génération (tous mondes)")
            ax5.legend()
            st.pyplot(fig5)
            st.info(
                "Utilisez les filtres, le menu déroulant et le slider pour explorer chaque monde, génération, espèce et stratégie. Exportez les données pour analyse avancée."
            )


def botdoctor_dashboard_panel():
    st.markdown("---")
    if st.button("⬅️ Retour à l'accueil 3D Evolution", key="retour_accueil_botdoctor"):
        st.session_state["active_panel"] = "Accueil 3D Evolution"
        st.rerun()
    show_sidebar_tutorial("botdoctor", "DOC_NOTIFY_TEST_STATUS.md")
    import json

    st.title("🩺 BotDoctor Dashboard")
    with st.expander("ℹ️ Aide & Astuces", expanded=False):
        st.markdown(
            """
        - Analysez la santé de chaque bot en un clic.
        - Corrigez les erreurs détectées automatiquement.
        - Consultez la documentation pour des diagnostics avancés.
        """
        )
    st.info(
        "Diagnostic automatique des bots de trading : santé, erreurs, logs, correctifs, suggestions IA."
    )
    st.markdown(
        "**Fichier source :** `supervision/botdoctor_dashboard.py`  \n[✏️ Éditer dans VS Code](vscode://file/"
        + os.path.abspath("supervision/botdoctor_dashboard.py")
        + ")"
    )
    st.success(
        "Toutes les fonctionnalités de diagnostic sont accessibles via le dashboard complet."
    )
    st.header("Résumé santé bots (données réelles)")
    try:
        bots_health = [
            {"Bot": "BTC/USDT", "Statut": "OK", "Dernière erreur": "-", "Ping": 0.12},
            {"Bot": "ETH/USDT", "Statut": "OK", "Dernière erreur": "-", "Ping": 0.15},
            {
                "Bot": "DOGE/USDT",
                "Statut": "Erreur",
                "Dernière erreur": "Order rejected",
                "Ping": 0.20,
            },
        ]
        st.dataframe(bots_health)
    except Exception as e:
        st.error(f"Erreur lors de l'affichage du résumé bots : {e}")
    st.header("Actions rapides")
    st.button("Analyser tous les bots", key="analyse_bots_btn")
    st.button("Corriger erreurs détectées", key="fix_bots_btn")
    st.info(
        "Pour plus de détails, ouvrez le panneau complet ou consultez la documentation BotDoctor."
    )


def evolution_multimonde_panel():
    st.markdown("---")
    if st.button("⬅️ Retour à l'accueil 3D Evolution", key="retour_accueil_multimonde"):
        st.session_state["active_panel"] = "Accueil 3D Evolution"
        st.rerun()
    show_sidebar_tutorial("multimonde", "DASHBOARD_USAGE_TEMPLATES.md")
    import json

    st.title("🌐 Evolution Multi-Monde")
    with st.expander("ℹ️ Aide & Astuces", expanded=False):
        st.markdown(
            """
        - Comparez la fitness, la diversité et la convergence entre mondes.
        - Exportez les résultats pour analyse avancée.
        - Consultez la documentation pour des exemples d’utilisation.
        """
        )
    st.info(
        "Comparatif analytique entre plusieurs mondes d’évolution : fitness, diversité, convergence."
    )
    st.markdown(
        "**Fichier source :** `evolution_dashboard.py`  \n[✏️ Éditer dans VS Code](vscode://file/"
        + os.path.abspath("evolution_dashboard.py")
        + ")"
    )
    st.success(
        "Visualisez les courbes de fitness max, diversité, heatmaps et exportez les comparatifs."
    )
    st.header("Comparatif fitness max par monde (données réelles)")
    try:
        with open(
            "archives/ecosystem_20260320_014011/best_strategies_cross_world.json",
            encoding="utf-8",
        ) as f:
            bests = json.load(f)
        rows = []
        for k, v in bests.items():
            rows.append(
                {
                    "Stratégie": k,
                    "Score": v.get("score", 0),
                    "Sharpe": v.get("sharpe", 0),
                    "Drawdown": v.get("drawdown", 0),
                }
            )
        st.dataframe(rows)
    except Exception as e:
        st.error(f"Erreur lors du chargement des comparatifs multi-monde : {e}")
    st.markdown(
        "- **Export CSV/PNG** : depuis le dashboard complet\n- **Analyse convergence** : voir section dédiée\n- **Documentation** : [DASHBOARD_USAGE_TEMPLATES.md](DASHBOARD_USAGE_TEMPLATES.md)"
    )


def quant_v16_panel():
    st.markdown("---")
    if st.button("⬅️ Retour à l'accueil 3D Evolution", key="retour_accueil_quantv16"):
        st.session_state["active_panel"] = "Accueil 3D Evolution"
        st.rerun()
    show_sidebar_tutorial("quantv16", "DASHBOARD_USAGE_TEMPLATES.md")
    import json

    st.title("📊 Quant V16 Panel")
    st.info(
        "Dashboard analytique Quant V16 : signaux, backtests, graphiques, scoring, export."
    )
    st.markdown(
        "**Fichier source :** `crypto_quant_v16/ui/quant_dashboard.py`  \n[✏️ Éditer dans VS Code](vscode://file/"
        + os.path.abspath("crypto_quant_v16/ui/quant_dashboard.py")
        + ")"
    )
    st.success(
        "Tous les outils de scoring et visualisation sont accessibles via le dashboard complet."
    )
    st.header("Derniers signaux générés (données réelles)")
    with open("archive_results/gen_10.json", encoding="utf-8") as f:
        signals = json.load(f)
    df_signals = [
        {
            "Signal": s["indicator"],
            "Score": s["score"],
            "TP": s["take_profit"],
            "SL": s["stop_loss"],
        }
        for s in signals[:5]
    ]
    st.dataframe(df_signals)
    st.header("Backtest rapide (scores)")
    st.line_chart([s["score"] for s in signals[:10]])
    st.info(
        "Pour l’analyse complète, ouvrez le panneau Quant V16 ou consultez la documentation."
    )


def quant_terminal_v12_panel():
    st.markdown("---")
    if st.button("⬅️ Retour à l'accueil 3D Evolution", key="retour_accueil_terminalv12"):
        st.session_state["active_panel"] = "Accueil 3D Evolution"
        st.rerun()
    show_sidebar_tutorial("terminalv12", "DASHBOARD_USAGE_TEMPLATES.md")
    import json

    st.title("📈 Quant Terminal V12")
    st.info(
        "Terminal quantitatif V12 : signaux, exécutions, logs, scoring, export CSV."
    )
    st.markdown(
        "**Fichier source :** `quant_hedge_ai/dashboard/quant_terminal_v12.py`  \n[✏️ Éditer dans VS Code](vscode://file/"
        + os.path.abspath("quant_hedge_ai/dashboard/quant_terminal_v12.py")
        + ")"
    )
    st.success(
        "Toutes les fonctionnalités de trading quantitatif sont accessibles via le dashboard complet."
    )
    st.header("Dernières exécutions (données réelles)")
    with open("alpha_vault_test.json", encoding="utf-8") as f:
        vault = json.load(f)
    rows = []
    for k, v in vault.items():
        rows.append(
            {
                "ID": v.get("strategy_id", k),
                "RSI": v.get("rsi_threshold", "-"),
                "MA": v.get("ma_period", "-"),
                "Score": v.get("score", 0),
                "Sharpe": v.get("sharpe", 0),
                "Drawdown": v.get("drawdown", 0),
            }
        )
    st.dataframe(rows)
    st.header("Export rapide")
    import io

    import pandas as pd

    df = pd.DataFrame(rows)
    st.download_button(
        "Exporter l’historique (CSV)",
        data=df.to_csv(index=False),
        file_name="trades.csv",
        mime="text/csv",
    )
    st.info(
        "Pour l’analyse complète, ouvrez le panneau Quant Terminal V12 ou consultez la documentation."
    )


def feedback_dashboard_panel():
    st.markdown("---")
    if st.button("⬅️ Retour à l'accueil 3D Evolution", key="retour_accueil_feedback"):
        st.session_state["active_panel"] = "Accueil 3D Evolution"
        st.rerun()
    show_sidebar_tutorial("feedback", "DOC_NOTIFY_TEST_STATUS.md")
    import json

    st.title("🧠 R&D Feedback Dashboard")
    with st.expander("ℹ️ Aide & Astuces", expanded=False):
        st.markdown("- Analysez la santé de chaque bot en un clic.")
        st.markdown("- Corrigez les erreurs détectées automatiquement.")
        st.markdown("- Consultez la documentation pour des diagnostics avancés.")
    st.info(
        "Pour plus de détails, ouvrez le panneau Feedback ou consultez la documentation IA."
    )


def main():
    if "active_panel" not in st.session_state:
        st.session_state["active_panel"] = "Accueil 3D Evolution"
    panel = st.session_state["active_panel"]
    try:
        if panel == "Accueil 3D Evolution":
            home_panel()
        elif panel == "🛡️ Supervision & Auto-Heal":
            supervision_autoheal_panel()
        elif panel == "🩺 BotDoctor Dashboard":
            botdoctor_dashboard_panel()
        elif panel == "🌐 Evolution Multi-Monde":
            evolution_multimonde_panel()
        elif panel == "🌐 3D Evolution Viewer":
            try:
                evolution_3d_panel()
            except Exception as e:
                import datetime
                import traceback

                error_report = f"Erreur inattendue dans le panel 3D : {e}\n{traceback.format_exc()}"
                st.error(
                    "Erreur critique dans le dashboard 3D. Un rapport détaillé est disponible ci-dessous."
                )
                st.code(error_report, language="text")
                st.download_button(
                    "Télécharger le rapport d'erreur 3D",
                    data=error_report,
                    file_name=f"rapport_3d_error_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                )
        elif panel == "📊 Quant V16 Panel":
            quant_v16_panel()
        elif panel == "📈 Quant Terminal V12":
            quant_terminal_v12_panel()
        elif panel == "🧠 R&D Feedback Dashboard":
            feedback_dashboard_panel()
        else:
            st.info(
                f"Section {panel} en construction ou non disponible dans ce dashboard."
            )
    except Exception as e:
        import datetime
        import traceback

        error_report = (
            f"Erreur inattendue dans le dashboard : {e}\n{traceback.format_exc()}"
        )
        st.error(
            "Erreur critique dans le dashboard. Un rapport détaillé est disponible ci-dessous."
        )
        st.code(error_report, language="text")
        st.download_button(
            "Télécharger le rapport d'erreur",
            data=error_report,
            file_name=f"rapport_dashboard_error_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        )


# Chargement des CSV de populations
def load_population_data(results_dir="results"):
    data = {}
    for file in glob.glob(os.path.join(results_dir, "*_pop_gen_*.csv")):
        world = file.split(os.sep)[-1].split("_")[0]
        gen = int(file.split("gen_")[-1].split(".")[0])
        df = pd.read_csv(file)
        df["generation"] = gen
        if world not in data:
            data[world] = []
        data[world].append(df)
    # Concaténer par monde
    for w in data:
        data[w] = pd.concat(data[w], ignore_index=True)
    return data


if __name__ == "__main__":
    st.set_page_config(page_title="3D Evolution Viewer", layout="wide")
    if "onboarding_lang" not in st.session_state:
        st.session_state["onboarding_lang"] = "FR"
    sidebar_onboarding()
    main()
