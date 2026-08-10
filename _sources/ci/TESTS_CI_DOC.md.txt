# CI/CD: Pytest + Coverage (Windows/Unix)
#
# 1. Installez les dépendances (requirements.txt)
# 2. Exécutez tous les tests unitaires et d'intégration
# 3. Générez un rapport de couverture
# 4. Échouez si un test échoue ou si la couverture < 90%
#
# Utilisation locale :
#   .venv\Scripts\activate (Windows) ou source .venv/bin/activate (Unix)
#   pip install -r requirements.txt
#   pytest --maxfail=1 --disable-warnings --cov=. --cov-report=term-missing
#
# Exemple de workflow GitHub Actions (ci.yml) :
#
# name: Python package
# on: [push, pull_request]
# jobs:
#   build:
#     runs-on: ${{ matrix.os }}
#     strategy:
#       matrix:
#         os: [ubuntu-latest, windows-latest]
#         python-version: [3.10, 3.11, 3.12]
#     steps:
#     - uses: actions/checkout@v4
#     - name: Set up Python ${{ matrix.python-version }}
#       uses: actions/setup-python@v5
#       with:
#         python-version: ${{ matrix.python-version }}
#     - name: Install dependencies
#       run: |
#         python -m pip install --upgrade pip
#         pip install -r requirements.txt
#         pip install pytest pytest-cov
#     - name: Run tests
#       run: |
#         pytest --maxfail=1 --disable-warnings --cov=. --cov-report=term-missing
#
# Documentation :
# - Les tests couvrent robustesse, performance, visualisation, intégration, reproductibilité, gestion d'erreur.
# - Pour ajouter un test, créez un fichier test_xxx.py ou ajoutez une méthode test_ dans un fichier existant.
# - Les tests de visualisation désactivent l'affichage interactif (matplotlib.use('Agg')).
# - Les tests de robustesse vérifient les cas limites (populations vides, extinction totale, mutation extrême).
# - Les tests d'intégration valident la cohérence des fichiers produits (CSV, PNG, JSON).
# - Les tests de reproductibilité fixent le seed aléatoire.
# - Les tests de gestion d'erreur simulent des exceptions dans les fonctions critiques.
#
# Pour toute évolution, lancez la suite de tests avant de valider une PR.
