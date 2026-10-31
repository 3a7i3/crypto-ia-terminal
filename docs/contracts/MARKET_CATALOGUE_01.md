# MARKET-CATALOGUE-01 — extension observationnelle v1.1

Mission : #533. Base source : `0967a56924cc9fccc8b8cee386b591ba3fa5f885`.
Statut : préparation SOURCE_ONLY, sans installation ni admission de nouvelles données.
Cette extension complète [WEB-01](WEB_01_MARKET_CRYPTORADAR_CONTRACT.md).
Elle ne change ni les scores CryptoRadar, ni son ordre, ses seuils ou ses règles.

## Défaut constaté

La capture historique admise sous #532 contient 20 lignes, pour un univers déclaré
de 124 symboles dont 94 au seuil. La recherche React ne dispose pas des 74 autres
lignes au seuil, encore moins des symboles sous le seuil. Recharger le même JSON
ne permet pas de retrouver BTC ou ETH absents de ce fichier.

`DEFAULT_TOP_N` du producteur est 50 ; les 20 lignes sont une propriété de cette
capture. Le frontend ne doit pas prétendre disposer de l’univers complet en v1.0.

## Deux versions fermées

La production sans option reste `1.0.0`, avec ses 16 champs d’origine.
Le lecteur continue de l’accepter. Aucun enrichissement implicite de ce format.

`include_catalogue=True` / `--catalogue` produit `1.1.0` avec les mêmes champs,
plus un seul objet fermé `catalogue` :

| Champ | Sens |
| --- | --- |
| `population` | Constante `ALL_OBSERVED_PACKETS` |
| `rows` | Toutes les lignes de `compute_symbol_stats(included, min_conf=0)` |
| `qualified_rows` | Toutes les lignes de `compute_symbol_stats(included, min_conf=min_confidence)` |
| `coverage` | Bornes UTC et partition des paquets chargés |

Chaque ligne conserve exactement les 7 champs WEB-01. Les deux listes
conservent leur ordre source. `top_opportunities` est un préfixe exact de
`qualified_rows`. Aucun indicateur d’exécution, secret ou volume ne traverse
cette projection.

Attention : le seuil s’applique à chaque paquet **avant** l’agrégation.
Un même symbole peut donc avoir un score moyen, une dominance et un régime
différents selon la population. La recherche globale passe explicitement
à `rows`, hors seuil inclus ; l’interface indique cette population.
« Tous les observés » signifie tous les symboles des paquets inclus, jamais
toutes les paires cotées d’un exchange.

## Fenêtre temporelle réellement bornée

`coverage` contient exactement :

- `start_at_utc`, `end_at_utc` ;
- `input_packets`, `included_packets`, `outside_window_packets` ;
- `future_packets`, `unresolved_timestamp_packets`.

Le producteur v1.1 retient les instants dans [début, fin], bornes incluses.
La fin est l’instant unique de génération, sans arrondi à la seconde.
Les dates naïves du producteur DecisionPacket sont étiquetées UTC selon le
contrat WEB-OBS-TIME-01 ; les offsets explicites sont convertis en UTC.
Les dates non résolues et futures sont exclues, comptées et affichables.
Aucune date n’est reconstruite à partir du fichier ou de l’heure de lecture.

Les compteurs forment une partition de `input_packets`. `included_packets`
égale `packets_observed` et la somme des `n_signals` de `rows`.
Les tailles, unicités, sous-ensemble de symboles, préfixe et dates sont validés
en Python et TypeScript. Toute incohérence refuse la source entière.

Le chargeur historique sélectionne des fichiers journaliers et peut déjà
ignorer des lignes JSONL malformées. `input_packets` compte les objets qu’il
retourne, pas toutes les lignes brutes ou tous les marchés. Cette extension
ne certifie pas la complétude de ce chargeur. Le mode v1.0 historique garde
sa fenêtre nominale et sa compatibilité.

`--window-hours 1` ou `4` exige `--catalogue` en CLI. Une publication représente
une seule fenêtre. Un sélecteur frontend ne peut pas transformer des agrégats
24 h en statistiques 1 h/4 h. Aucune boucle ou publication réelle n’a été lancée
dans cette mission.

## Présentation

- 20 résultats par page, recherche sur le catalogue fourni, puis pagination ;
- population au seuil par défaut, population complète explicite ;
- filtres de biais et régime, sans classement supplémentaire ;
- tableau ou carte de symboles, un seul affichage détaillé à la fois ;
- couleur = biais publié, intensité = score moyen, texte chiffré toujours présent ;
- détail au clavier, Échap et retour du focus, thème clair/sombre ;
- dates, couverture, historique périmé, erreurs et absence de résultats conservés.

La carte n’est ni une corrélation de prix, ni une carte de volumes, ni un score
de timing. Les absences de Δscore, RVOL et transition datée restent explicites.

## Cadence et disponibilité

Le client MARKET effectue un GET à l’ouverture puis attend 20 secondes après
chaque requête terminée. Le producteur source propose une boucle de 30 secondes
par défaut, uniquement lorsqu’elle est lancée séparément.
Cela ne prouve aucune cadence de production sur la VM : la surface active
consomme une capture historique immuable. Rafraîchir sa lecture ne la rajeunit
pas. Cette mission n’active aucune alerte sonore, notification ou Telegram.

## Admission future, distincte de la source

La capture v1.0 active reste utilisable avec sa limite visible.
Le lecteur API déployé `82cd63e...` n’accepte pas v1.1 : ne pas déposer ce format
dans la présentation actuelle avec la seule nouvelle interface.

Une admission v1.1 exige une décision distincte couvrant le lecteur API compatible,
le frontend exact, le jeu de données autorisé, leurs contrôles et le rollback.
Reconstruire un catalogue réel depuis les JSONL récupérés exige un périmètre
de lecture autorisé ; cette mission n’a pas ouvert ces données.
Le privilège ponctuel de #532 est consommé et ne s’étend pas à cette extension.
Aucun check vert, fusion de source ou fichier de protocole n’accorde ces actes.

## Préparation historique et provenance — #535

Le nouvel outil offline `python -m tools.prepare_market_catalogue` accepte
des fichiers journaliers explicitement sélectionnés et vérifiés contre le
manifest reçu. Son dossier de sortie doit être nouveau, privé et extérieur
aux données récupérées et à `presentation`. Aucun chargeur runtime n’est
appelé quand `source_packets` est fourni explicitement au producteur.

Le reçu conserve hashes, état de la source, ancre historique, exclusions et
limites de provenance. Les clés métier/risque/secrets ne traversent pas la
projection. Le catalogue n’est pas un roster scientifique indépendant.
Le lecteur v1.1 vérifie le candidat offline ; cela ne modifie pas le lecteur
v1.0 installé et ne vaut pas autorisation de raccordement.

La provenance et la comparaison future sont détaillées dans
[MARKET-MULTI-VENUE-01](MARKET_MULTI_VENUE_01.md).
