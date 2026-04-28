# 🚀 Tutoriel pas-à-pas – Écosystème évolutif & Dashboard

## 1. Lancer la simulation évolutive
```powershell
python orchestrate_ecosystem.py
```
- Génère toutes les données nécessaires (CSV, JSON, PNG, archives).

## 2. Ouvrir le dashboard interactif
```powershell
.\.venv\Scripts\streamlit run evolution_dashboard.py
```
- Explorez les mondes, la fitness, la diversité, les survivants.
- Utilisez les filtres pour zoomer sur une espèce, une génération, un score.

## 3. Visualisation avancée 3D & AutoML
```powershell
.\.venv\Scripts\streamlit run evolution_3d_view.py
```
- Visualisez la population en 3D (TP, SL, fitness, espèce).
- Appliquez des clusters, heatmaps, scoring automatique.
- Lancez l’AutoML pour optimiser les paramètres (TP, SL, RSI, MA, etc.).
- Exportez les résultats (CSV, JSON, Optuna).

## 4. Bonnes pratiques
- Toujours relancer la simulation avant d’explorer.
- Utiliser les exports pour analyse externe.
- Tester différents objectifs et paramètres dans l’AutoML.

## 5. Dépannage rapide
- **Pas de données ?** Relancer la simulation.
- **Erreur Streamlit/Optuna ?** Vérifier les packages (`pip install -r requirements.txt`).
- **Port occupé ?** Ajouter `--server.port 8502` à la commande Streamlit.

---

Pour toute question, consultez la FAQ ou ouvrez une issue. Vous pouvez aussi écrire à : ia.strategy.support@gmail.com
