# Procédure de mise à jour et déploiement

Ce guide décrit les étapes sûres pour mettre à jour, déployer et vérifier le système crypto-ai-terminal sur tout environnement (Windows/Linux/Mac, local ou CI/CD).

---

## 1. Pré-requis
- Accès au dépôt Git (droits de pull/push si besoin)
- Python 3.10+ installé
- Accès à PowerShell (Windows) ou bash (Linux/Mac)
- Accès internet pour installer les dépendances

## 2. Sauvegarde et vérification
- Sauvegardez vos fichiers de configuration personnalisés (API keys, .env, batch_configs.json, etc.)
- Vérifiez l’état du dépôt :
  ```bash
  git status
  git pull
  ```
- Vérifiez l’environnement avec :
  ```bash
  python diagnostic_env.py
  ```

## 3. Mise à jour du code
- Récupérez la dernière version :
  ```bash
  git pull origin main
  ```
- Si besoin, changez de branche/tag :
  ```bash
  git checkout <branch|tag>
  ```

## 4. Mise à jour des dépendances
- Installez/actualisez les dépendances :
  ```bash
  pip install -r requirements.txt
  ```
- Si un environnement virtuel est utilisé :
  ```bash
  ./.venv/Scripts/Activate.ps1  # Windows
  source .venv/bin/activate     # Linux/Mac
  ```

## 5. Migration de la base de données (si applicable)
- Suivez les instructions spécifiques à votre module (voir README du module concerné).

## 6. Lancement et vérification
- Lancez les tests :
  ```bash
  python run_all_tests.py
  ```
- Vérifiez les rapports :
  - all_tests_report.md
  - RAPPORT_FINAL_AUDIT.md
- Lancez les dashboards ou scripts nécessaires (voir DASHBOARD_USAGE_TEMPLATES.md).

## 7. Déploiement en production/serveur
- Utilisez les scripts batch ou .sh fournis (voir launch_*.bat, launch_*.sh)
- Pour Docker :
  ```bash
  docker-compose up -d
  ```
- Vérifiez les logs et la disponibilité des ports/services.

## 8. CI/CD
- Les workflows GitHub Actions automatisent :
  - Tests, couverture, badges, screenshots, diagnostic environnement
- Consultez les statuts dans l’onglet Actions du dépôt GitHub

## 9. Restauration en cas d’échec
- Restaurez la sauvegarde de vos fichiers de config
- Rebasculer sur la version précédente :
  ```bash
  git checkout <commit|tag>
  ```
- Réinstallez les dépendances si besoin

---

Pour toute question, ouvrez une issue ou consultez la documentation détaillée (README, ONBOARDING_QUICK_START.md, DASHBOARD_USAGE_TEMPLATES.md).
