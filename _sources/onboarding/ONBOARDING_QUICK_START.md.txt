## 5. Navigation et UI/UX (Nouveautés 2026)

Tous les dashboards disposent :
- D’une sidebar interactive pour accéder à tous les panels et à la documentation
- D’un bouton “Retour à l’accueil 3D Evolution” en bas de chaque panel
- D’une structure homogène (titre, aide, actions, exports, navigation)
- D’icônes et wording standardisés pour toutes les actions (ex : “🔍 Analyser”, “🛠️ Corriger”, “⬇️ Exporter”)
- D’options de personnalisation et d’export (PNG, SVG, CSV, JSON…)

**Astuce :** Utilisez la sidebar pour naviguer, le bouton retour pour revenir à l’accueil, et consultez l’aide intégrée de chaque panel pour les usages avancés.
# Onboarding rapide : crypto_ai_terminal

Bienvenue ! Ce guide vous permet de démarrer sur n'importe quel poste (Windows, Linux, Mac) en toute autonomie.

## 1. Prérequis
- Python 3.8+ installé (https://www.python.org/downloads/)
- Git recommandé
- Accès à PowerShell (Windows) ou bash (Linux/Mac)

## 2. Installation automatique (Windows)
1. Ouvrez PowerShell dans le dossier du projet.
2. Exécutez :
   ```powershell
   ./install_all.ps1
   ```
   Exemple de session PowerShell attendue :
   ```powershell
   PS C:\Users\...\crypto_ai_terminal> ./install_all.ps1
   [INFO] Suppression de l'ancien environnement .venv (si présent)...
   [INFO] Création d'un nouvel environnement virtuel .venv avec python...
   [INFO] Activation de l'environnement virtuel...
   [INFO] Installation des dépendances racine...
   ...
   [INFO] Installation terminée. Vous pouvez lancer :
       .\.venv\Scripts\Activate.ps1
       python run_all_tests.py
   ```
   - Le script détecte Python, crée `.venv`, installe toutes les dépendances et modules critiques.
   - Si une erreur apparaît, suivez les instructions affichées.
3. Activez l'environnement :

---

## Mise à jour et déploiement

Pour toute mise à jour ou déploiement, suivez le guide détaillé :

- [UPDATE_DEPLOY_GUIDE.md](UPDATE_DEPLOY_GUIDE.md)

---

## Diagnostic rapide de l’environnement Python

Avant de lancer les dashboards ou les tests, vous pouvez vérifier que votre environnement est sain :

```powershell
python diagnostic_env.py
```

Ce script vérifie : version Python, pip, dépendances, permissions d’écriture, variables d’environnement, et git. Il signale toute anomalie critique pour garantir un fonctionnement optimal.
   ```
   .\.venv\Scripts\Activate.ps1
   ```

## 3. Installation automatique (Linux/Mac)
1. Ouvrez un terminal bash dans le dossier du projet.
2. Exécutez :
   ```bash
   bash install_all.sh
   ```
   Exemple de session bash attendue :
   ```bash
   user@host:~/crypto_ai_terminal$ bash install_all.sh
   [INFO] Suppression de l'ancien environnement .venv (si présent)...
   [INFO] Création d'un nouvel environnement virtuel .venv avec python...
   [INFO] Activation de l'environnement virtuel...
   [INFO] Installation des dépendances racine...
   ...
   [INFO] Installation terminée. Vous pouvez lancer :
       source .venv/bin/activate
       python run_all_tests.py
   ```
   - Le script détecte Python, crée `.venv`, installe toutes les dépendances et modules critiques.
   - Si une erreur apparaît, suivez les instructions affichées.
3. Activez l'environnement :
   ```bash
   source .venv/bin/activate
   ```

## 4. Diagnostic automatique
- Pour vérifier ou dépanner l'environnement, lancez :
  - Windows : `./diagnose_python_env.ps1`
  - Linux/Mac : `bash diagnose_python_env.sh`
- Le diagnostic teste Python, `.venv` et tous les modules critiques. Suivez les recommandations affichées.

## 5. Lancer tous les tests
1. Une fois `.venv` activé, lancez :
   ```
   python run_all_tests.py
   ```
2. Un rapport global (`all_tests_report.md`) est généré. Les notifications (Discord/email/Telegram) sont envoyées automatiquement si configurées.
   
   Exemple de notification Discord :
   ```
   [TEST NOTIFY] ✅ Tous les tests sont passés sur poste: user@host
   Fichier rapport: all_tests_report.md
   ```
   
   Extrait du rapport de tests généré :
   ```
   ==================== Résumé global ====================
   TOTAL: 42 tests
   OK:    42
   FAIL:  0
   SKIP:  0
   DURÉE: 18.2s
   ------------------------------------------------------
   Détail par module :
   - test_quant_engine.py ............ OK
   - test_dashboard_api.py .......... OK
   ...
   ```

## 6. Validation & Robustesse

Le système est validé par une batterie de tests automatisés (unitaires, intégration, extrêmes, performance, sécurité) et un audit complet.

- **CI/CD** : chaque push/PR déclenche les tests, la génération de rapports et la vérification des badges de couverture (Codecov, Coveralls)
- **Rapports** :
   - [Rapport final d’audit](RAPPORT_FINAL_AUDIT.md)
   - [Rapport global de tests](all_tests_report.md)
   - [Couverture Codecov](https://codecov.io/gh/0xl1v/crypto-ai-terminal)
   - [Couverture Coveralls](https://coveralls.io/github/0xl1v/crypto-ai-terminal)

Exemple de notification Discord :
```
[TEST NOTIFY] ✅ Tous les tests sont passés sur poste: user@host
Fichier rapport: all_tests_report.md
```

---
## 7. Dépannage
- Si `.venv` ou Python ne sont pas trouvés, relancez `install_all.ps1` ou `install_all.sh`.
- Si un module manque, relancez le script d'installation ou suivez les instructions du diagnostic.
- Pour toute erreur persistante, vérifiez les logs et consultez la documentation technique du projet.

---

**Ce workflow garantit une installation, un diagnostic et une exécution des tests fiables, même sur un poste neuf ou mal configuré.**
