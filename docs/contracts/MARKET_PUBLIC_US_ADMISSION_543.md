# Proposition d’admission temporelle publique US — #543

**DESIGN_ONLY / NON_ADMIS / NON_DÉPLOYÉ.** Cette proposition complète la revue
[#543](https://github.com/3a7i3/crypto-ia-terminal/issues/543) ; elle ne modifie pas
les contrats exécutés, le lecteur actif, le plan #542 ou un seuil scientifique.
[Revue et population](../research/market_time_review_543/REVIEW.md) ·
[Décision structurée](../research/market_time_review_543/DECISION.json).

## 1. Frontières et états proposés

Conserver séparément :
- capture conservée cohérente ;
- observation native décodée, avec provenance et temps non qualifiés ;
- source temporellement qualifiée pour un usage défini ;
- paire comparable selon une politique explicite ;
- artifact compatible et admis pour la présentation ;
- permission distincte de publier ce SHA/artifact/chemin.

Un PASS au niveau capture ne promeut aucun niveau suivant.
COMPLETED, HTTP200, OBSERVED ou WITHIN_BUDGET n’accordent aucune autorité.
Un artifact historique peut servir à la recherche offline sans devenir FRESH
par une nouvelle date de génération. UNKNOWN reste null avec sa raison.

## 2. Attestations requises pour une future qualification

| Dimension | Preuve attendue avant une admission |
| --- | --- |
| Version et identité du flux | Hôte/route/API version, produit, filtre d’entité, symbole natif et mapping revus ; endpoints distincts Advanced/Exchange |
| Instrument | Base, devise USD distincte de USDT/USDC, Spot, unités/quantification et métadonnées liées au run ; politique d’expiration des métadonnées |
| Sens de la date | Contenu amont daté, hashé et versionné précisant l’événement daté et son périmètre bid/ask ; ne pas choisir BOOK_PUBLICATION ou MATCHING_ENGINE par convenance |
| Résolution | Unité, précision, arrondi/troncature et incertitude de représentation conservés ; texte natif exact et dérivé distincts |
| Cache | Headers reçus et politique documentée à cette version ; Age absent=UNKNOWN ; revalidation/hops non attestés=UNRESOLVED |
| Horloge locale | Identité/échelle de temps, diagnostics pré/post reliés au run et modèle d’incertitude valide sur l’intervalle ; saut et expiration explicites |
| Horloge du flux | Relation documentée entre horloge de la réponse, de l’événement et éventuelle sonde ; borne d’offset/incertitude/validité avec ses hypothèses |
| Durées | Bornes locales d’envoi/réception et monotone ; pas de correction RTT/2 ou Date arbitraire ; les délais d’intention restent visibles |
| Capture complète | Roster indépendant, intentions/reçus/bruts liés par hashes, erreurs et trous conservés, limites respectées |
| Usage | Définition de « comparable » et domaine autorisé ; absence de certification d’exécution ou de profit |

Une API d’heure serveur n’est pas requise par son seul nom et n’est pas réputée
suffisante : elle doit dater un événement compris dans une fenêtre justifiée et
être reliée à l’horloge du champ natif considéré. Un nouveau probe est une
requête nouvelle soumise à décision, pas une relecture hors réseau.

Le budget de cache annoncé n’est ni l’âge mesuré de la réponse, ni le retard
maximal du moteur. Age/Date/timestamp natif ne sont pas additionnés ou corrigés
sans relation documentée. L’incertitude inconnue reste inconnue, sans valeur zéro.

## 3. Modèle d’incertitude à décider avant tout calcul

Une future politique peut utiliser un intervalle d’événement par source.
Si l’offset o = temps_source - temps_commun est borné dans
[o_min,o_max], le timestamp natif t représente au mieux
[t-o_max,t-o_min], élargi de sa quantification et des délais sémantiques/cache
qui n’y seraient pas déjà inclus. Les signes, l’échelle et chaque élargissement
doivent être documentés pour éviter le double comptage.

Sans borne de ces composantes, aucun intervalle fini n’est inventé.
Une proximité de dates brutes, un intervalle HTTP ou leur intersection ne
prouve pas à lui seul la simultanéité des états du carnet.
Le critère d’âge et la relation temporelle acceptable entre sources doivent
être définis pour l’usage prévu, avec hypothèses, bornes et raisons de refus.
Aucune borne chiffrée nouvelle n’est adoptée ici. Le plan US #542 n’hérite pas
du skew du profil #539. Les bornes historiques ne sont pas ajustées à l’échantillon.

## 4. Refus à conserver dans un éventuel futur artifact

Motifs proposés à spécifier/tester en source avant toute installation :
TIME_SEMANTICS_UNRESOLVED, CACHE_UNRESOLVED, CLOCK_BOUND_NOT_PROVEN,
TEMPORAL_COMPARABILITY_NOT_PROVEN, METADATA_EXPIRED_OR_UNQUALIFIED,
HISTORICAL_STALE, SOURCE_NOT_SUPPLIED et FORMAT_NOT_ADMITTED.
Ces noms sont des propositions documentaires, pas de nouveaux enums actifs.
Les valeurs natives peuvent être conservées hors des métriques ; aucun zéro
ou valeur reconstruite ne remplace une observation absente.

Tant qu’une source n’est pas qualifiée : mid/spread et métriques de ses paires
restent indisponibles. Une publication de prix historiques non qualifiés,
sans métriques, serait elle-même un scope distinct de présentation avec ses
dates et états explicites. Cette proposition ne l’installe pas.

## 5. Compatibilité et chaîne d’admission

PublicUSCapture n’est pas MarketVenueComparison.
Ne pas configurer OPERATOR_VENUE_COMPARISON_PATH vers un cycle ou run-result.
Ne pas renommer coinbase_advanced en coinbase_exchange ni Bitstamp en une venue
existante. L’ajout de vrais IDs/endpoint IDs, mapping, décodeurs et projection
relève d’une modification source explicite, avec contrats Python/TypeScript
fermés et tests de la chaîne complète.

Tout adaptateur futur doit conserver les quatre sources attendues, les dates
natives, quantités exactes, hashes et cas indisponibles ; il ne reconstruit pas
son roster depuis les seuls succès. Le schéma peut vérifier la forme et la
cohérence interne, sans devenir l’autorité de qualification documentaire.
Les attestations d’admission doivent être liées à version/plan/source/boundary,
et expirables ou révoquées selon leur domaine de validité.

Tests utiles dans ce futur scope : Age absent, cache permis long, heure Date
antérieure à la requête, dérive/offset constant, preuve d’horloge expirée,
sémantiques différentes malgré dates proches, neuf décimales, metadata périmée,
fichier partiel et changement de roster, publication fraîche d’un carnet ancien.
Les fixtures restent inventées et ne certifient aucune plateforme réelle.

## 6. Séquence de décisions futures

1. Décider la portée documentaire/source nécessaire pour fermer les inconnus.
2. Si nécessaire, décider une collecte/probe ponctuelle explicitement bornée :
   SHA/plan/URLs, hypothèses, budget, stockage privé, arrêt, reçu exclusif.
3. Revoir ses preuves ; conserver les échecs et refuser une admission incomplète.
4. Préparer, tester et revoir un artifact exact compatible et son raccordement,
   avec ancien état/chemin/hash et rollback vers non configuré.
5. Décider séparément toute publication/runtime. Un merge source ne la permet pas.

Aucune de ces étapes futures n’est activée par ce document. Aucun nouveau caller,
header de cache, endpoint, service, port, secret ou permission n’est créé.
Le rollback de la présente revue consiste à ne pas intégrer ses propositions ;
aucune bascule active n’a eu lieu, les originaux et preuves sont conservés.
