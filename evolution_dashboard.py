import sys

if __name__ != "__main__" and (
    "pytest" in sys.modules or any("pytest" in arg for arg in sys.argv)
):
    import pytest

    pytest.skip(
        "evolution_dashboard.py is a Streamlit app and should not be tested with pytest.",
        allow_module_level=True,
    )
"""
Dashboard évolutif multi-monde (évolution, espèces, fitness, best survivors)
Lancez avec : streamlit run evolution_dashboard.py
"""


import configparser
# --- Log de démarrage fichier ---
import datetime
import glob
import json
import os

import pandas as pd
import streamlit as st

from ui_utils import sidebar_navigation

try:
    with open("dashboard_startup.log", "a", encoding="utf-8") as f:
        f.write(
            f"[START] {datetime.datetime.now().isoformat()} - evolution_dashboard.py lancé\n"
        )
except Exception as e:
    pass

# --- Vérification des fichiers critiques + mode diagnostic ---
import platform


def check_critical_files():
    missing = []
    # Fichiers de config
    if not os.path.exists("strategy_factory_config.ini"):
        missing.append("strategy_factory_config.ini")
    # Dossier results
    if not os.path.isdir("results"):
        missing.append("results/")
    else:
        # Au moins un CSV population
        if not glob.glob(os.path.join("results", "*_pop_gen_*.csv")):
            missing.append("results/*_pop_gen_*.csv")
        # Fichier best survivors
        if not os.path.exists(
            os.path.join("results", "best_strategies_cross_world.json")
        ):
            missing.append("results/best_strategies_cross_world.json")
    return missing


with st.expander("🛠️ Diagnostic rapide (cliquer pour ouvrir)"):
    st.write(f"**Heure de démarrage :** {datetime.datetime.now().isoformat()}")
    st.write(
        f"**Python :** {platform.python_version()} | Platform : {platform.platform()}"
    )
    st.write(f"**cwd :** {os.getcwd()}")
    st.write(f"**Fichiers/dossiers présents :**")
    st.write(os.listdir("."))
    st.write(
        f"**results/** : {os.listdir('results') if os.path.isdir('results') else 'absent'}"
    )
    st.write(
        f"**strategy_factory_config.ini :** {'présent' if os.path.exists('strategy_factory_config.ini') else 'absent'}"
    )
    st.write(
        f"**best_strategies_cross_world.json :** {'présent' if os.path.exists(os.path.join('results','best_strategies_cross_world.json')) else 'absent'}"
    )
    st.write(
        f"**CSV population :** {glob.glob(os.path.join('results', '*_pop_gen_*.csv'))}"
    )
    st.write(
        f"**Dépendances :** streamlit, pandas, matplotlib, json, configparser, glob, os"
    )
    st.write(f"**Fichier de log :** dashboard_startup.log")
    try:
        with open("dashboard_startup.log", "r", encoding="utf-8") as flog:
            st.code(flog.read(), language="text")
    except Exception:
        st.info("Aucun log de démarrage trouvé.")

critical_missing = check_critical_files()
if critical_missing:
    st.error(
        f"Fichiers/dossiers critiques manquants : {', '.join(critical_missing)}\n\nLe dashboard ne peut pas fonctionner sans ces éléments. Veuillez vérifier l'installation et les exports de simulation."
    )
    st.stop()

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


def home_panel():
    st.title("🌐 Dashboard Évolution Multi-Monde")
    st.markdown(
        """
Bienvenue sur le dashboard d'évolution multi-monde.

**Navigation rapide :**
"""
    )
    for label, path in INTERNAL_DASHBOARDS:
        if path.endswith(".py"):
            if st.button(f"{label}"):
                st.session_state["dashboard"] = path
        else:
            st.button(f"{label}")
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


def main():
    if "dashboard" not in st.session_state:
        st.session_state["dashboard"] = None
    panel = sidebar_navigation(
        [
            "Accueil Évolution",
            *[label for label, _ in INTERNAL_DASHBOARDS],
            "Aide & FAQ",
            "Tutoriel pas-à-pas",
            "FAQ",
        ]
    )
    if panel == "Accueil Évolution" and not st.session_state["dashboard"]:
        home_panel()
        return
    elif panel == "Tutoriel pas-à-pas":
        st.markdown(
            """
## 📖 Tutoriel interactif – Evolution Multi-Monde

Bienvenue sur le dashboard d’évolution multi-monde ! Voici comment l’utiliser efficacement :

1. **Navigation** : Utilisez la sidebar pour accéder à tous les panels (Supervision, BotDoctor, 3D, Quant, Terminal, Feedback…)
2. **Exploration** : Sélectionnez un monde et explorez les populations, générations, et survivants.
3. **Visualisation** : Analysez les courbes, distributions, et scores pour chaque monde.
4. **Exports** : Téléchargez les données pour analyse avancée.
5. **Aide & FAQ** : Accédez à la documentation et à l’aide intégrée via la sidebar.

---

Pour plus de détails, consultez :
- [DASHBOARD_USAGE_TEMPLATES.md](DASHBOARD_USAGE_TEMPLATES.md)
- [README_CONSOLIDATED.md](README_CONSOLIDATED.md)
"""
        )
        return
    # Navigation par session_state
    if st.session_state["dashboard"]:
        st.info(f"Redirection vers le dashboard : {st.session_state['dashboard']}")
        # Ici, on pourrait utiliser st.experimental_rerun() ou afficher un message/iframe selon l'usage souhaité
        return
    # ...existing code...


config = configparser.ConfigParser()
config.read("strategy_factory_config.ini")
SHOW_PLOTS = config.getboolean("visualization", "show_plots", fallback=True)

if __name__ == "__main__":
    st.set_page_config(page_title="Dashboard Évolution Multi-Monde", layout="wide")
    main()
    # --- Code principal du dashboard (affiché si pas sur l'accueil) ---
    st.title("🌐 Dashboard Évolution Multi-Monde")
    RESULTS_DIR = "results"


# Chargement des CSV de populations
@st.cache_data
def load_population_data():
    data = {}
    for file in glob.glob(os.path.join(RESULTS_DIR, "*_pop_gen_*.csv")):
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


# Chargement des meilleurs survivants
@st.cache_data
def load_best_survivors():
    path = os.path.join(RESULTS_DIR, "best_strategies_cross_world.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


data = load_population_data()
best = load_best_survivors()

# Sélection du monde
worlds = list(data.keys())
selected_world = st.selectbox("Monde à explorer", worlds)
df = data[selected_world]

# Filtres dynamiques
st.sidebar.header("Filtres avancés")
species_list = sorted(df["species"].unique())
selected_species = st.sidebar.multiselect(
    "Espèces à afficher", species_list, default=species_list
)
min_gen, max_gen = int(df["generation"].min()), int(df["generation"].max())
selected_gen = st.sidebar.slider("Génération", min_gen, max_gen, (min_gen, max_gen))
score_min = float(df["fitness"].min())
score_max = float(df["fitness"].max())
selected_score = st.sidebar.slider(
    "Score minimal (fitness)", float(score_min), float(score_max), float(score_min)
)

# Application des filtres
filtered_df = df[
    (df["species"].isin(selected_species))
    & (df["generation"] >= selected_gen[0])
    & (df["generation"] <= selected_gen[1])
    & (df["fitness"] >= selected_score)
]


import base64
import io

# Visualisation fitness par génération (filtrée) avec export automatique, bouton de téléchargement et stats
import matplotlib.pyplot as plt

st.subheader(f"Fitness par génération – {selected_world} (filtres appliqués)")
if not filtered_df.empty:
    fitness_by_gen = filtered_df.groupby("generation")["fitness"].max()
    st.line_chart(fitness_by_gen)
    # Export automatique PNG/PDF
    fig1, ax1 = plt.subplots()
    fitness_by_gen.plot(ax=ax1)
    ax1.set_title(f"Fitness par génération – {selected_world}")
    ax1.set_xlabel("Génération")
    ax1.set_ylabel("Fitness")
    buf_png = io.BytesIO()
    buf_pdf = io.BytesIO()
    fig1.savefig(buf_png, format="png")
    fig1.savefig(buf_pdf, format="pdf")
    plt.close(fig1)
    buf_png.seek(0)
    buf_pdf.seek(0)
    st.download_button(
        "Télécharger ce graphique (PNG)",
        buf_png,
        file_name=f"fitness_{selected_world}.png",
        mime="image/png",
    )
    st.download_button(
        "Télécharger ce graphique (PDF)",
        buf_pdf,
        file_name=f"fitness_{selected_world}.pdf",
        mime="application/pdf",
    )
    # Statistiques fitness
    st.markdown("**Statistiques fitness (après filtres)**")
    stats = filtered_df["fitness"].describe()[["mean", "50%", "min", "max", "std"]]
    stats.index = ["Moyenne", "Médiane", "Min", "Max", "Écart-type"]
    st.table(stats)
else:
    st.info("Aucune donnée pour les filtres sélectionnés.")

# Visualisation répartition des espèces (filtrée) avec export automatique, bouton de téléchargement et stats
st.subheader(f"Répartition des espèces – {selected_world} (filtres appliqués)")
if not filtered_df.empty:
    species_counts = (
        filtered_df.groupby(["generation", "species"]).size().unstack(fill_value=0)
    )
    st.area_chart(species_counts)
    # Export automatique PNG/PDF
    fig2, ax2 = plt.subplots()
    species_counts.plot.area(ax=ax2)
    ax2.set_title(f"Répartition des espèces – {selected_world}")
    ax2.set_xlabel("Génération")
    ax2.set_ylabel("Nombre")
    buf2_png = io.BytesIO()
    buf2_pdf = io.BytesIO()
    fig2.savefig(buf2_png, format="png")
    fig2.savefig(buf2_pdf, format="pdf")
    plt.close(fig2)
    buf2_png.seek(0)
    buf2_pdf.seek(0)
    st.download_button(
        "Télécharger ce graphique (PNG)",
        buf2_png,
        file_name=f"species_{selected_world}.png",
        mime="image/png",
    )
    st.download_button(
        "Télécharger ce graphique (PDF)",
        buf2_pdf,
        file_name=f"species_{selected_world}.pdf",
        mime="application/pdf",
    )
    # Statistiques espèces
    st.markdown("**Statistiques espèces (après filtres)**")
    species_stats = (
        filtered_df["species"]
        .value_counts()
        .rename_axis("Espèce")
        .reset_index(name="Nombre")
    )
    st.table(species_stats)
else:
    st.info("Aucune donnée pour les filtres sélectionnés.")

# Table des meilleurs survivants
st.subheader("Meilleurs survivants cross-monde")
st.dataframe(pd.DataFrame(best).T)

# Affichage des paramètres d'une stratégie sélectionnée
if st.checkbox("Afficher les paramètres d'un survivant ?"):
    strat_id = st.text_input("ID de la stratégie (copiez depuis la table)")
    found = None
    for w, d in data.items():
        match = d[d["id"] == strat_id]
        if not match.empty:
            found = match.iloc[0]
            st.write(f"Stratégie trouvée dans le monde : {w}")
            st.json(found.to_dict())
            break
    if not found:
        st.warning("ID non trouvé dans les populations.")

# Affichage images (si disponibles)
if st.checkbox("Afficher les graphiques PNG exportés ?"):
    imgs = glob.glob(os.path.join(RESULTS_DIR, "*.png"))
    for img in imgs:
        st.image(img, caption=os.path.basename(img), use_column_width=True)
