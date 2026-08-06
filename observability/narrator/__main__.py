"""Point d'entree du Narrateur : `python -m observability.narrator`.

Pourquoi ce fichier plutot que `-m observability.narrator.runner` : le
`__init__.py` du paquet importe deja `runner`, donc lancer ce module comme
`__main__` le chargait une SECONDE fois et Python emettait a chaque
demarrage :

    RuntimeWarning: 'observability.narrator.runner' found in sys.modules
    after import of package 'observability.narrator'

Benin ici — `main()` cree ses propres instances — mais un avertissement a
chaque boot entraine a ne plus lire ses journaux. Un point d'entree dedie
supprime la cause au lieu de filtrer le symptome.
"""

from observability.narrator.runner import main

if __name__ == "__main__":
    main()
