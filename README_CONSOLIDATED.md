
---
## 🛡️ Audit & Robustesse (avril 2026)

**Système validé par audit complet :**
- Tests extrêmes, mutation, CSV corrompus, NaN/inf, résilience API/réseau
- Logs/alertes centralisés, sécurité (secrets, permissions NTFS)
- Tests d’intégration multi-modules, benchmarks, fallback intelligents
- UI/UX homogène, navigation sidebar, tutoriel interactif sur tous les panels
- Couverture de code automatisée (Codecov, Coveralls), CI multi-plateforme

**Rapports :**
- [Rapport final d’audit](RAPPORT_FINAL_AUDIT.md)
- [Rapport global de tests](all_tests_report.md)

---

Tous les dashboards disposent désormais :
- D’une **sidebar interactive** pour naviguer entre tous les panels (accès direct, liens externes, documentation)
- D’un **bouton “Retour à l’accueil 3D Evolution”** en bas de chaque panel
- D’une structure homogène : Titre (avec icône) → Bloc d’aide/info → Documentation/source → Actions principales (boutons, exports) → Navigation/Retour
- D’un wording et d’icônes standardisés pour toutes les actions (ex : “🔍 Analyser”, “🛠️ Corriger”, “⬇️ Exporter”)
- D’options de personnalisation et d’export avancées (PNG, SVG, CSV, JSON…)

# Diagnostic rapide de l’environnement Python

---

## Procédure de mise à jour et déploiement

Pour toute mise à jour, déploiement ou restauration, suivez :

- [UPDATE_DEPLOY_GUIDE.md](UPDATE_DEPLOY_GUIDE.md)

Avant toute utilisation, vérifiez votre environnement avec :

```bash
python diagnostic_env.py
```

Ce script contrôle : version Python, pip, dépendances, permissions d’écriture, variables d’environnement, git. Toute anomalie critique est signalée pour garantir la compatibilité et la stabilité du système.

---
# Système de Trading Quantitatif Crypto — README Consolidé & Démarrage Rapide

## Vue d'ensemble
Ce dépôt contient un système de trading quantitatif crypto modulaire et multi-agent, avec des tableaux de bord avancés, une orchestration et des analyses pilotées par l'IA. Il est conçu pour un déploiement professionnel, sécurisé et extensible sur Windows (et Linux/Mac avec quelques ajustements mineurs).

**Fonctionnalités clés :**
- Architecture modulaire : V9.1 (quant-hedge-ai), V16/V26/V30 (crypto_quant_v16), quant-ai-system (stack Docker)
- Multiples tableaux de bord : Panel & Streamlit (quant, alert, botdoctor, evolution, feedback, vue 3D, terminal)
- Menu de navigation unifié sur tous les tableaux de bord
- Configuration sécurisée basée sur l'environnement
- Scripts d'exemple et modèles d'utilisation pour chaque dashboard
- Documentation professionnelle et onboarding

---

## Démarrage Rapide (Windows)

### 1. Cloner & Préparer l'Environnement
```powershell
git clone <repo_url>
cd crypto_ai_terminal
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configuration
- Copier `.env.example` vers `.env` et renseigner les secrets requis (clés API, DB, etc.)
- Vérifier et ajuster `config.py` ou les fichiers de config versionnés si besoin

### 3. Lancer les Tableaux de Bord
- **V9.1 Quant Lab :**
  ```powershell
  cd quant-hedge-ai
  $env:V9_MAX_CYCLES="1"; python main_v91.py
  ```
- **Dashboard V16 :**
  ```powershell
  cd crypto_quant_v16
  launch_v16_dashboard.bat
  # Ou : panel serve ui\quant_dashboard.py --port 5011 --show
  ```
- **Autres Dashboards :**
  - `launch_alert_dashboard.bat`, `launch_botdoctor_dashboard.bat`, `launch_evolution_dashboard.bat`, etc.

### 4. Vérifications & Tests
- Lancer `healthcheck_v30.bat` ou `healthcheck_v30.ps1` pour V30
- Exemples de tests :
  ```powershell
  cd crypto_quant_v16
  python test_v30_profile.py
  python test_v30_multi_exchange.py
  python test_v30_profile_persistence.py
  python test_v30_smart_chart.py
  ```

---


## Exemples d’utilisation et captures d’écran

Pour chaque dashboard, des exemples d’utilisation détaillés et des captures d’écran sont disponibles dans :

- [DASHBOARD_USAGE_TEMPLATES.md](DASHBOARD_USAGE_TEMPLATES.md)

### Galerie rapide

| Quant Dashboard | Supervision & Auto-Heal | BotDoctor Dashboard |
|---|---|---|
| ![Quant Dashboard](screenshots/quant_v16_panel.png) | ![Supervision & Auto-Heal](screenshots/supervision_autoheal.png) | ![BotDoctor Dashboard](screenshots/botdoctor_dashboard.png) |

| Evolution Multi-Monde | 3D Evolution Viewer | Feedback Dashboard |
|---|---|---|
| ![Evolution Multi-Monde](screenshots/evolution_multimonde.png) | ![3D Evolution Viewer](screenshots/evolution_3d_viewer.png) | ![Feedback Dashboard](screenshots/feedback_dashboard.png) |

| Quant Terminal V12 |
|---|
| ![Quant Terminal V12](screenshots/quant_terminal_v12.png) |

Pour les usages détaillés (lancement, navigation, exports, etc.), voir le fichier DASHBOARD_USAGE_TEMPLATES.md.

### Utilisation type (avec navigation unifiée)

1. Lancez le dashboard souhaité (ex : `launch_evolution_3d_view.bat`)
2. Naviguez entre les panels via la sidebar interactive (tous accessibles sans recharger la page)
3. Utilisez le bouton « Retour à l’accueil 3D Evolution » pour revenir à la page principale
4. Personnalisez les visualisations (palette, taille, opacité, axes, titre…)
5. Exportez les résultats (PNG, SVG, CSV, JSON) via les boutons dédiés
6. Consultez l’aide intégrée de chaque panel pour des astuces et la documentation

---

### Quant Dashboard (Panel)
```powershell
cd crypto_quant_v16
panel serve ui\quant_dashboard.py --port 5011 --show
```
- Accès : http://localhost:5011
- Fonctionnalités : Navigation unifiée, stats de trading en direct, liens rapides, vérifications de statut

### Alert Dashboard (Panel)
```powershell
launch_alert_dashboard.bat
```
- Accès : http://localhost:5013
- Fonctionnalités : Alertes en temps réel, navigation rapide, statut système

### BotDoctor Dashboard (Panel)
```powershell
launch_botdoctor_dashboard.bat
```
- Accès : http://localhost:5010
- Fonctionnalités : Diagnostic des bots, vérifications de santé, menu de navigation

### Evolution Dashboard (Panel)
```powershell
launch_evolution_dashboard.bat
```
- Accès : http://localhost:5026
- Fonctionnalités : Analytique évolutionnaire, navigation, accès rapide

### Vue 3D Evolution (Panel)
```powershell
launch_evolution_3d_view.bat
```
- Accès : http://localhost:5012
- Fonctionnalités : Visualisation 3D, navigation, analytique

### Feedback Dashboard (Panel)
```powershell
launch_feedback_dashboard.bat
```
- Accès : http://localhost:5014
- Fonctionnalités : Feedback utilisateur, liens rapides, navigation

### Quant Terminal (Streamlit)
```powershell
launch_quant_terminal_v12.bat
```
- Accès : http://localhost:8502
- Fonctionnalités : Interface terminal, navigation, actions rapides

---

## Menu de Navigation Centralisé
Tous les dashboards disposent désormais d'une barre latérale avec :
- Accueil, liens rapides et ressources externes
- Vérifications de statut et changement de dashboard
- Expérience utilisateur cohérente sur tous les panels

---

## Dépannage & Conseils
- **Collisions de ports :** Vérifiez `ports_check.txt` ou utilisez `netstat` pour résoudre les conflits
- **Erreurs d'import :** Assurez-vous que `.venv` est activé et que PYTHONPATH est défini si besoin
- **Trading réel :** Utilisez le mode papier/simulé par défaut ; ne jamais committer de vraies clés API
- **Vérifications de santé :** Considérez les warnings comme des problèmes de connectivité sauf si l'échec strict est requis

---

## Contribution & Extension
- Suivre les conventions de code (voir CODE_STYLE.md si présent)
- Ajouter de nouveaux dashboards/modules dans leurs dossiers respectifs
- Mettre à jour la logique de navigation pour les nouveaux dashboards
- Ajouter des exemples d'utilisation et mettre à jour la documentation pour les nouvelles fonctionnalités

---

## Références & Documentation
- [QUICK_START_V91.md](QUICK_START_V91.md)
- [crypto_quant_v16/QUICK_START.md](crypto_quant_v16/QUICK_START.md)
- [CONFIG_REFERENCE_V91.md](CONFIG_REFERENCE_V91.md)
- [DASHBOARDS_README.md](DASHBOARDS_README.md)
- [PROJECT_INVENTORY.md](PROJECT_INVENTORY.md)

---

## Checklist du Plan d'Action
- [x] Inventorier la documentation existante
- [x] Centraliser la configuration (fichier unique)
- [x] Unifier la navigation des dashboards
- [x] Ajouter un menu d'accès rapide à tous les panels
- [ ] Compléter/structurer README et QUICK_START
- [ ] Ajouter des exemples d'utilisation pour chaque dashboard
- [ ] Préparer un plan d'action détaillé

---

## Contact & Support
Pour toute question, demande de fonctionnalité ou aide à l'onboarding, ouvrez une issue ou contactez le mainteneur.
