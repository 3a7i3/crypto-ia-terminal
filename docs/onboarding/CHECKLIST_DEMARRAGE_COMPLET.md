# Checklist de démarrage complet

1. **Activation de l’environnement virtuel**
   - [ ] L’environnement virtuel Python est activé (`.venv` ou autre)

2. **Installation des dépendances**
   - [ ] Les commandes `pip install -r requirements.txt` et `pip install -r requirements-dev.txt` ont été exécutées sans erreur
4. **Fichiers de configuration**
   - [ ] Les fichiers `.env`, `config.ini`, et autres fichiers de configuration nécessaires sont présents et valides

5. **Lancement global**
   - [ ] La commande `.\launch_all.bat` ou `.\launch_all.ps1 -Visible -LoadEnv` a été exécutée

6. **Contrôle des terminaux/modules**
   - [ ] Chaque fenêtre/terminal affiche un message de démarrage sans erreur
   - [ ] Aucun message d’erreur critique n’apparaît dans les logs

7. **Vérification de la santé des modules**
   - [ ] Les scripts de healthcheck (`healthcheck_v30.bat`, etc.) sont lancés et valident l’état des modules

8. **Accès aux dashboards/UI**
   - [ ] Les dashboards sont accessibles via le navigateur sur les ports attendus

9. **Tests rapides**
   - [ ] Les tests unitaires ou de validation rapide (`run_all_tests.py`, `python test_v30_profile.py`, etc.) passent sans erreur

10. **Surveillance continue**
   - [ ] Les logs sont surveillés pour détecter toute anomalie après le lancement

---

Coche chaque étape pour garantir un démarrage 100% opérationnel.