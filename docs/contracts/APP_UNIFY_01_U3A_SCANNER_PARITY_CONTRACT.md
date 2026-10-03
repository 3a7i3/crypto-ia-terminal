# APP-UNIFY U3a — Scanner safe et parité CryptoRadar

Issue : #332 ; parent : #323 ; freeze : #286 ACTIVE.
Baseline : `d6c33404816afca0057c0e976a567f76be8c1a1f` (fusion U2b #331).

## Architecture et portée

Producteur existant `observability/market_radar_snapshot.py` → artifact atomique
`CryptoRadar` schema `1.0.0` → reader strict → GET `/api/operator/v1/market`
→ validation TypeScript → PAPER LIVE / Marché.

U3a étend le nombre de lignes publiées par défaut de 20 à 50. Aucun nouveau
champ, endpoint, paramètre runtime ou seuil. L'ancien artifact 20 lignes reste
compatible. Aucun changement à `radar_bot`, au dashboard historique, à leurs
agrégations, aux unités/timers, ni aux paramètres de trading.

Le seuil de présentation reste 65 ; il est appliqué aux packets individuels
avant agrégation par symbole. `universe_size` provient des agrégats sans seuil ;
`actionable_count` compte les symboles au seuil avant troncature. Le vocabulaire
historique `actionable_count` ne confère aucune permission de trading.

Recherche insensible à la casse et aux espaces périphériques, par sous-chaîne
littérale du symbole. Filtres ALL/LONG/SHORT/MIXED sur le biais dominant publié.
Ils se combinent, conservent l'ordre producteur et ne provoquent ni nouveau GET
ni recalcul statistique. Ils portent exclusivement sur les lignes publiées,
pas sur tout l'univers. Le compteur distingue résultats filtrés, lignes
publiées, symboles au seuil et univers observé. Couverture partielle explicite
si le nombre publié est inférieur au nombre au seuil ; aucun résultat filtré
ne signifie pas marché vide.

Le détail accessible par bouton symbole (desktop/mobile) présente exactement
les agrégats de la ligne validée : moyenne/max confidence, n_signals, biais,
dominance et régime. La population au seuil/fenêtre et la fraîcheur sont
explicites. La sélection est résolue depuis le snapshot courant et les lignes
filtrées ; aucun objet ancien n'est conservé lors d'un remplacement de source.
Un échec source supprime les cartes/détails ; STALE expose des données
historiques avec état actuel INCONNU. FRESH est la fraîcheur de publication du
snapshot existant, pas une attestation de prix live : le timestamp du dernier
packet reste dans la provenance. U3a ne redéfinit pas le contrat temporel.

Python et TypeScript rejettent les incohérences `published > actionable_count`
ou `actionable_count > universe_size`, et les doublons symbole. Les schémas
fermés interdisent les champs supplémentaires d'exécution ou de secret.

## Matrice de parité source

| Capacité standalone | U3a Operator App | Limite / décision |
|---|---|---|
| Scanner top 50 | 50 par défaut | artifact historique 20 accepté, couverture indiquée |
| Classement confidence | ordre `radar_bot.compute_symbol_stats` conservé | test compare la fonction historique sur mêmes packets et même seuil |
| Avg/max confidence, n_signals | tableau, cartes, détail | aucune recomputation React |
| Biais / dominance / régime | tableau, cartes, détail | MIXED/50 conserve la convention historique, pas une précision reconstruite |
| Recherche symbole | sous-chaîne, casse ignorée | uniquement les lignes publiées |
| LONG/SHORT | filtres combinés à recherche | biais dominant, pas tous les packets d'un côté |
| Détail symbole | agrégats observationnels au seuil | pas la population exhaustive historique |
| Comptages LONG/SHORT exacts | NOT_AVAILABLE explicite dans détail | absents du schema ; ne pas inférer depuis dominance arrondie |
| Seuil scanner historique UI 60 | projection gouvernée 65 conservée | parité du calcul à population/seuil égaux, aucune revendication de mêmes résultats avec seuils différents |
| Dernier signal Entry/SL/TP/R | DO_NOT_MIGRATE dans Market | compréhension décisions via domaine Decisions gouverné |
| Onglet Signaux / risk_pct / reward_pct | DO_NOT_MIGRATE dans Market | aucune surface d'exécution historique copiée |
| Packet counts/status | packets_observed et source_updated_at_utc | fenêtre et provenance affichées, pas métrique fichiers |
| dp_files / dp_total_gb | hors Market | System/Storage futur si projection gouvernée |
| LMI microstructure | DEFERRED U3b | producteur/projection distincts requis |
| Auth/serveur/HTML standalone | non migrés | transport Operator App existant |

## Preuves et limites

Tests : même classement/agrégats que la fonction historique pure extraite
sans démarrer son transport ; 60 symboles → 50 lignes par vrai publisher,
reader et GET API ; absence d'exécution ; contrats de couverture ; React
filtres combinés/reset/MIXED/aucun résultat/détail/STALE/erreur ; fixture
cross-stack `L_scanner` permet de chercher une ligne au-delà de l'ancien top 20.
Preuve browser desktop/mobile : données réelles de cette fixture, interactions,
absence de débordement, erreurs API/contrat/réseau et requêtes GET uniquement.

U3a certifie la source seulement. Pas de déploiement, VPS, restart Advisor,
mutation PPL/FIN/epoch/config/risk/sizing/Watchdog/exchange. #286 reste ACTIVE.
Aucun retrait ou arrêt du dashboard. Il reste à prouver la disponibilité
runtime, les consommateurs et la parité LMI U3b. Un retrait exige une mission
séparée, preuve consommateurs et rollback de service/transport documenté.
Rollback source : revert de la PR U3a ; schema 1.0.0 inchangé, anciens artifacts
compatibles. Ce rollback source n'autorise aucune intervention runtime.
