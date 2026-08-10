# Procédure d'isolation et d'automatisation des tests

## 1. Identification des modules critiques
Lister tous les modules/fonctions qui accèdent au disque, à l'environnement, au réseau ou manipulent des fichiers/logs/configs.

## 2. Création de tests isolés
- Créer un fichier de test dédié pour chaque module critique.
- Utiliser `pytest`, `monkeypatch`, `tmp_path` pour isoler l'environnement de chaque test.
- Patcher les accès fichiers (glob, open, pandas.read_csv, etc.) pour rediriger vers des fichiers temporaires.
- S'assurer que chaque test peut être relancé sans pollution (pas d'état global persistant).

## 3. Correction des modules
- Paramétrer les chemins d'accès aux fichiers/dossiers dans les modules.
- Gérer l'absence de colonnes attendues dans les DataFrames (ajouter si manquantes).
- Éviter les effets de bord lors de l'import (déplacer le code dans des fonctions ou sous `if __name__ == "__main__":`).

## 4. Automatisation de l'exécution
- Utiliser `pytest` pour exécuter tous les tests isolés :
  ```
  python -m pytest test_evolution_3d_view.py test_analyze_strategy_niches.py test_visualize_strategy_ecosystem_all_gens.py test_visualize_strategy_ecosystem.py --maxfail=3 --disable-warnings -q
  ```
- Vérifier que tous les tests passent (aucune pollution, robustesse assurée).

## 5. Documentation et extension
- Documenter la procédure dans un fichier dédié (ex: `TEST_ISOLATION_GUIDE.md`).
- Étendre la méthode à d'autres modules au besoin.

---

*Procédure validée le 20/03/2026. Tous les tests critiques passent en isolation complète.*
