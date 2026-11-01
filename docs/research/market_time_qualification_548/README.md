# Dossier de qualification temporelle — #548

1er novembre 2026, America/Mexico_City. Base `fa1d39f0bee74e68c569d46b9ae469afa10e3e8e`.
**Préparé, non admis, non installé.** Cette suite de #546/#547 précise les
preuves manquantes et les actions qui pourraient réellement les fournir.

- [Matrice par flux/instrument](QUALIFICATION_MATRIX.json)
- [Nouvelles pièces documentaires](DOCUMENTARY_DELTA.json)
- [Protocole de fermeture des inconnus](../../contracts/MARKET_TIME_QUALIFICATION_PROTOCOL_548.md)
- [Exemples synthétiques](SYNTHETIC_COUNTEREXAMPLES.json)
- [Questions à faire clarifier, non envoyées](PROVIDER_QUESTIONS.md)
- [Vérificateur des seuls exemples](verify_synthetic_examples.py)

## Ce qui est qualifié et ce qui ne l'est pas

Les quatre bindings REST de #542 sont conservés, trois observations chacun :
Coinbase Advanced et Bitstamp, BTC/USD et ETH/USD Spot. Métadonnées et
représentations sont rejouables ; les formats sont documentés dans le
[registre #546](../market_time_attestation_546/ATTESTATIONS.json).
Cela ne qualifie pas l'événement, l'arrondi, les horloges ou l'âge réel.
Aucune borne finie justifiée ne peut en être tirée dans le modèle retenu.

Les comptages de cache de la matrice concernent uniquement les douze carnets :
six headers Coinbase max-age14400 ; trois Bitstamp max-age1 et trois absents.
Les huit headers Coinbase et quatre absents du rapport #543 incluaient aussi
les trois requêtes de métadonnées. Les populations ne sont pas confondues.
Age manque dans tous les carnets. L'absence ne prouve ni fraîcheur ni péremption.

## Deux apports documentaires, une limite d'accès

Le schéma du candidat L2 Coinbase définit séparément le temps d'événement
moteur et celui d'envoi. Le numéro de séquence est par connexion ; le champ
d'événement n'est pas requis dans le schéma ciblé. Cette piste demande encore
les bornes d'horloge, l'intégrité du carnet et son domaine d'accès.
Aucune définition L2 n'est transférée à pricebook.time REST et aucune connexion
WebSocket n'a été tentée. Les clés privées ne sont pas nécessaires selon
la notice publique consultée ; aucun compte ou secret n'a été ouvert.

Les diagnostics sauvegardés nomment metadata.google.internal. La documentation
Google décrit une politique de lissage des secondes intercalaires. C'est une
question de relation entre échelles à expliciter, pas la découverte d'une erreur
de la VM ; aucun lissage actif à cette date n'est affirmé, aucun NTP modifié.

La documentation Bitstamp WS n'a pas été lisible par les deux lecteurs :
texte web vide, puis challenge HTML. Aucun script/challenge exécuté, aucun
autre hôte ou navigateur utilisé pour le contourner. Le gap reste ouvert.

Les extraits et leurs hashes bornent les affirmations ; les snapshots complets
restent privés. La version déclarée d'un document ne fournit pas une révision
amont immuable. Notre commit versionne la relecture, sans certifier le passé.
Les sources nouvelles sont liées dans DOCUMENTARY_DELTA.json ; les notices
précédentes et preuves #542/#543 ne sont pas modifiées.

## Démonstration et reproduction

Les exemples inventés montrent qu'un offset ou délai non borné peut changer
l'âge réel tout en gardant les mêmes valeurs visibles. Les différences
wall/monotone éliminent un offset constant. Les valeurs ne sont pas des
estimations d'erreur des plateformes et ne définissent aucun seuil.

Depuis la racine du dépôt :

```bash
python -B docs/research/market_time_qualification_548/verify_synthetic_examples.py
```

Le vérificateur lit ces seuls exemples et la référence #546, utilise la
bibliothèque standard et ne fait aucun appel réseau ou mesure d'horloge.
Il contrôle des égalités sous hypothèses ; il ne valide aucune preuve d'origine,
aucune observation réelle ou admission de comparaison.
La relecture privée vérifie en plus les 65 empreintes de la capture, les
ancres #543/#546 et les schémas officiels conservés.

App active1da737 et paquet isolé9af84de7 inchangés. Aucun fichier producteur,
pilote, API, publisher, frontend, stratégie, seuil ou dépendance modifié.
Questions préparées sans envoi ; aucune nouvelle capture/probe, installation,
action de service ou publication. Les décisions restent séparées.
