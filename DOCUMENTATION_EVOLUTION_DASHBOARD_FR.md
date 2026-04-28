# 📖 Documentation détaillée – Écosystème évolutif & Dashboard

## 1. Lancement automatique

- **Simulation complète** :
  ```powershell
  python orchestrate_ecosystem.py
  ```
  - Lance l’évolution multi-monde, archive les résultats, génère les CSV/JSON/PNG.

- **Dashboard interactif (résultats, analyse, AutoML)** :
  ```powershell
  .\.venv\Scripts\streamlit run evolution_dashboard.py
  # ou pour la 3D/AutoML avancé
  .\.venv\Scripts\streamlit run evolution_3d_view.py
  ```

## 2. Fonctionnalités principales

- **Évolution multi-monde** : 4 mondes (trend, range, crash, chaos), migration, extinction, export des survivants.
- **Archivage automatique** : Tous les résultats (CSV, JSON, PNG, logs) sont archivés dans `archives/` à chaque run.
- **Dashboards interactifs** :
  - `evolution_dashboard.py` : fitness, espèces, survivants, images, analyse temporelle, export CSV.
  - `evolution_3d_view.py` : visualisation 3D, clustering, heatmap, scoring, AutoML, comparatif multi-monde, export Optuna.
- **AutoML intégré** : Optimisation automatique des paramètres (TP, SL, RSI, MA, etc.) avec choix de l’objectif (fitness, sharpe, drawdown, return).
- **Filtres avancés** : fitness, espèce, génération, sélection de stratégie, export CSV/JSON.

## 3. Utilisation des dashboards

### a) Dashboard général (`evolution_dashboard.py`)
- **Sélection du monde** : menu déroulant.
- **Fitness par génération** : courbe interactive.
- **Répartition des espèces** : area chart dynamique.
- **Table des survivants** : meilleurs cross-monde.
- **Paramètres d’une stratégie** : recherche par ID.
- **Affichage des images** : PNG générés par la simulation.

### b) Dashboard avancé 3D & AutoML (`evolution_3d_view.py`)
- **Visualisation 3D** : scatter plot interactif (TP, SL, fitness, espèce).
- **Filtres avancés** : fitness, espèce, génération, sélection de stratégie.
- **Clustering KMeans** : segmentation automatique de la population.
- **Heatmap 2D** : densité TP/SL.
- **Analyse temporelle** : diversité des espèces au fil des générations.
- **Comparatif multi-monde** : fitness max par génération pour chaque monde.
- **Scoring automatique** : top stratégies filtrées.
- **AutoML avancé** : optimisation multi-paramètres, choix de l’objectif, export des résultats Optuna (JSON).

## 4. Export & archivage
- **CSV** : chaque population/génération, export filtré depuis le dashboard.
- **JSON** : meilleurs survivants cross-monde, résultats Optuna.
- **PNG** : visualisations automatiques (3D, dominance, etc.).
- **Archives** : tous les résultats sont copiés dans `archives/` à chaque run.

## 5. Bonnes pratiques & conseils
- **Toujours lancer la simulation avant d’ouvrir les dashboards** (pour générer les fichiers nécessaires).
- **Utiliser les filtres pour explorer la diversité** (espèces, fitness, générations).
- **Exploiter l’AutoML pour identifier les zones de performance** (optimisation fine des paramètres).
- **Exporter les résultats pour analyse externe** (Excel, Python, etc.).
- **Consulter les logs et archives pour audit ou reproductibilité.**

## 6. Dépannage
- **Pas de données dans le dashboard** : relancer `python orchestrate_ecosystem.py`.
- **Erreur Streamlit/Optuna** : vérifier que les packages sont installés dans le venv (`pip install -r requirements.txt`).
- **Port déjà utilisé** : changer le port Streamlit (`--server.port 8502`).

## 7. Ressources complémentaires
- [README.md](README.md)
- [QUICK_START_V91.md](QUICK_START_V91.md)
- [DOCUMENTATION_INDEX.md](DOCUMENTATION_INDEX.md)
- [DEMARRAGE_RAPIDE_FR.md](DEMARRAGE_RAPIDE_FR.md)


## 🚦 Onboarding & Support avancé

### 📧 Support / FAQ
- Pour toute question ou information sur le logiciel, contactez : ia.strategy.support@gmail.com

### Chatbot live (démo locale)
- Un assistant GPT local est accessible via l’onglet « Aide & FAQ » du dashboard 3D.
- Pour une intégration live (Slack, Teams, web), voir la section « Aide interactive GPT ».

### Onboarding utilisateur
- Au premier lancement du dashboard, un message d’accueil guide l’utilisateur (présentation, liens, tutoriel).
- Les ressources essentielles (tutoriel, FAQ, aide GPT) sont accessibles en un clic depuis l’UI.

### Support cloud (déploiement possible)
- Les dashboards Streamlit sont compatibles avec Streamlit Cloud, Azure, AWS, GCP.
- Pour déployer :
  1. Pousser le repo sur GitHub
  2. Lier à Streamlit Cloud ou un service cloud compatible
  3. Configurer les variables d’environnement et secrets si besoin
- Voir la documentation Streamlit pour le déploiement cloud sécurisé.

---

Pour toute question, ouvrez une issue ou consultez la documentation centrale.
