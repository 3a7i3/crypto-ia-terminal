# Radar composite BTC/USDT Spot M5 — lot local

Rejouer depuis la racine avec Python 3 et la bibliothèque standard.

    python -m observability.radar_composite.m5 tests/radar_composite/btc_m5.json
    python -m unittest discover -s tests/radar_composite -v

Le jeu de données contient uniquement des prix et des heures inventés. Pour chaque instant de la grille UTC (début inclus, fin exclue), le fichier fournit un relevé par plateforme. trade_ms est l'heure de la dernière transaction et received_ms celle de la réception. La préparation des relevés réels et leur attribution aux instants de grille restent à qualifier. Un timestamp de publication d'un ticker ne remplace pas trade_ms. L'observation doit déjà être reçue à l'instant de grille.

La méthode v1 utilise 30 instants espacés de 10 secondes, un âge maximal inclusif de 5 secondes et deux poids égaux. Ces paramètres constituent des hypothèses expérimentales. Le premier relevé peut porter sur une transaction légèrement antérieure au début de fenêtre. Les extrêmes décrivent la série échantillonnée. Les prix sont des chaînes décimales positives. Chaque trou conserve ses causes par source. Seule une fenêtre entièrement couverte produit des OHLC. Une source inconnue, une incohérence temporelle ou un doublon invalide le fichier. Une sortie complète décrit la couverture du jeu de test et ne vaut aucune admission runtime.

Avant tout pilote, vérifier pour chaque source la sémantique du prix et de son horodatage, les horloges et l'accès régional. Si les tickers ne donnent pas l'heure du trade, examiner une lecture publique bornée de la dernière transaction. Une collecte intégrale des transactions n'est pas nécessaire pour éprouver cette méthode.
