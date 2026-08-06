"""
certification — outils de certification et de gel documentaire.

Ce fichier est nécessaire à la collecte pytest de tout le dépôt : ne pas le
supprimer.

`certification/tests/` possède un `__init__.py`. Sans `certification/__init__.py`,
pytest remonte l'arborescence tant qu'il trouve des `__init__.py`, s'arrête à
`certification/` et insère ce répertoire en tête de `sys.path`. Le nom `tests`
résout alors vers `certification/tests/`, qui masque le paquet `tests/` de la
racine — et les ~170 modules `tests.test_*` deviennent introuvables
(`ModuleNotFoundError: No module named 'tests.test_x'`), ce qui interrompt la
collecte de toute la suite.

Rendre `certification` importable comme paquet fait remonter le point d'insertion
à la racine du dépôt, où `tests` désigne bien le paquet racine.
"""
