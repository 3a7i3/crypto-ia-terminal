# CAT-DATA-01 — Inventaire lecture seule avant S4-b (2026-11-25)

Règle CAT-DATA-01 (opérateur, 2026-11-25 20:47Z) : avant toute implémentation, inventorier en
lecture seule les producteurs, collecteurs et timers, publications, routes et consommateurs
frontend, désigner le propriétaire de chaque donnée, réutiliser l'existant compatible et refuser
toute duplication injustifiée.

**Portée et limite.** Cet inventaire est fait sur la **source** (`main@a2ec703`, toutes branches
distantes pour les recherches d'historique). L'état **réellement servi** sur `crypto-restore-01`
n'est pas observé ici : voir le rapport CAT-PREPROD-01 et le script
`deploy/preprod/cat_prod_inventory_readonly.sh`. SOURCE PROOF ≠ RUNTIME PROOF. Aucun service ni
fichier n'a été supprimé ou modifié.

## 1. Domaine Scanner / Radar scientifique (concerné par S4-b)

| Donnée | Propriétaire (producteur) | Collecte / timer | Publication | Route | Consommateur frontend |
|---|---|---|---|---|---|
| Catalogues bruts MEXC/Kraken (4 marchés) | `observability/scanner_universe/collect.py` | `cat-scanner-universe.timer`, 15 min, VPS (déploiement `deploy/scanner_universe/`) | `/var/lib/cat-scanner-universe/runs/<id>/*.json` + `manifest.json` (24 relevés gardés) | aucune | aucun |
| Univers commun Scanner `scanner-universe/1.1.0` | `scanner_universe.universe.compute_universe` (même producteur) | même timer | `/var/lib/cat-scanner-universe/scanner-universe.json` | `GET /scanner-universe` (`ScannerUniverseReader`) | `scannerUniverseClient.ts`, `ScannerUniverse.tsx`, `ScannerAssetList.tsx` |
| Évaluation Radar `radar-evaluation/1.2.0` | moteur `observability/radar_selection` (commande `export`) | **aucun** timer, hors ligne | aucune publication de production ; fixtures R0 et lot R1-B dans le dépôt | aucune avant S4-b | aucun |
| Projection vérifiée `radar-projection/1.0.0` | `observability/radar_projection` (S4-a, vérificateur seul) | aucun | aucune (calculée à la lecture) | **S4-b : `GET /radar-projection`** | aucun avant S4-c |
| Historique BBO composite | `observability/radar_composite` | pilotes bornés (#585) | fichier configuré `OPERATOR_BBO_HISTORY_PATH` | `GET /bbo-composite-history` | `bboHistoryClient.ts`, `BboCompositeHistory.tsx` |

**Décision S4-b (réutilisation, aucune duplication) :**
- le service lit **l'export** déjà produit par le moteur ; il n'appelle pas le moteur ;
- la vérification et la projection sont celles de S4-a (`project_bytes`), sans seconde implémentation ;
- E1 lit la publication Scanner par le **`ScannerUniverseReader` existant**, via la même instance
  que la route `/scanner-universe` : même fichier, mêmes règles de validation et de fraîcheur ;
- aucun nouveau collecteur, timer, stockage ou calcul de score.

## 2. Autres producteurs et publications « marché » (hors S4-b, inventoriés pour les doublons)

| Donnée | Producteur | Timer (unité dans le dépôt) | Publication | Route | Frontend |
|---|---|---|---|---|---|
| Pouls marché MEXC (~3 200 paires) | `observation/market_observer.py` | `crypto-market-observer.timer` 15 min | `databases/observation/market_pulse_*.jsonl.gz`, `latest_tick.json` | aucune | aucun |
| Shortlist « radar marché global R1 » (ADR-0016) | `observation/market_radar.py` | `crypto-market-radar.timer` 06:00 UTC | `radar_shortlist_<jour>.json` | aucune | aucun |
| Horizons R2 | `observation/horizon_evaluator.py` | `crypto-market-horizons.timer` 06:15 UTC | `horizon_eval_<jour>.json` | aucune | aucun |
| Instantané CryptoRadar (WEB-01 MARKET) | `observability/market_radar_snapshot.py` | `crypto-market-snapshot.service`, intervalle 30 s | `databases/cryptoradar_market_snapshot.json` | `GET /market` | `marketClient.ts`, `MarketScanner.tsx`, `DirectionOverview.tsx` |
| Spot Radar D1-RC1 (`spot-radar/1.0.0`) | **absent de main** (service séparé, port 18906) | inconnu | inconnu | proxy web `/api/operator/v1/spot-radar/*` | `spotRadarClient.ts`, `SymbolScanner.tsx`, `SpotRadarMap.tsx` |
| Comparaison des plateformes | `observability/market_venues` | publication passive | `OPERATOR_VENUE_COMPARISON_PATH` | `GET /venue-comparison` | `venueComparisonClient.ts` |
| Market Flow | `observability/market_flow` | artefact configuré | `OPERATOR_MARKET_FLOW_PATH` | `GET /market-flow` | `marketFlowClient.ts` |
| Microstructure | lecteur `market_microstructure_reader` | publication passive | chemin par défaut du lecteur | `GET /market-microstructure` | `marketMicrostructureClient.ts` |
| Intraday, indicateurs de signaux | **absents de main** (préproduction Intraday du laboratoire) | inconnu | inconnu | `/intraday/*`, `/signals-indicators` (non servis par l'API de main) | `intradayClient.ts`, `SignalsRadar.tsx` |

## 3. Routes de l'API de `main` (25 GET) et routes vues hors de `main`

Routes de `observability/operator_api/app.py` : `healthz`, `snapshot`, `portfolio`,
`decision-pipeline`, `system-health`, `ppl-comparison`, `ppl-accounting-history`,
`financial-reconciliation`, `market-microstructure`, `agent-invocations/{id}` (+ `history`,
`schedule`), `runtime-service`, `burn-in` (+ `statistics`), `market`, `research-strategies`,
`research-lab`, `venue-comparison`, `market-flow`, `bbo-composite-history`, `scanner-universe`,
`storage`, `events`, et **`radar-projection` (S4-b)**.

Routes appelées par les scripts de déploiement ou le frontend mais **absentes de `main`** :
`storage-inventory` et `lab-experiments` (scripts `deploy/scanner_universe/*`), `spot-radar/*`,
`intraday/*`, `signals-indicators`, `paper-balance-history` (servie par le serveur web lui-même).
`storage-inventory` et `lab-experiments` n'apparaissent dans **aucun commit** des 453 branches
distantes (`git log --all -S`) : la production contient du code qui n'est pas dans GitHub.

## 4. Doublons potentiels relevés (aucun n'est créé par S4-b)

| # | Constat | Risque | Proposition (non exécutée) |
|---|---|---|---|
| D1 | **Trois « radars » à score** : `observation/market_radar.py` (liquidité 40, spread 30, activité 20, fiabilité 10 ; MEXC), `radar_selection` (continuité 30, spread 25, activité 20, L2 15, coût 10 ; MEXC × Kraken), Spot Radar D1-RC1 | confusion de nom et de verdict ; deux classements concurrents | désigner un propriétaire par usage ; ne jamais afficher les deux scores comme un même « Radar » ; décision opérateur |
| D2 | Deux lectures des catalogues MEXC : `market_observer` (tickers MEXC complets) et Scanner (catalogues 4 marchés) | collecte réseau en double sur MEXC | vérifier sur le VPS si les deux tournent ; mutualisation éventuelle = chantier distinct |
| D3 | Lecture bornée de fichier dupliquée dans 4 lecteurs (`market_flow`, `scanner_universe`, `bbo_history`, `venue_comparison`) | divergence de règles de sécurité | S4-b factorise dans `bounded_file.py` pour son seul usage ; migration des anciens lecteurs = lot séparé, sur GO |
| D4 | Code servi en production absent de GitHub (`storage-inventory`, `lab-experiments`, blocs DPA `8872f635` et Market Observer `ea6d077a` hors `main`) | une fusion depuis `main` ferait régresser la production | inventaire runtime (CAT-PREPROD-01), réintégration source sous GO |
| D5 | Instantané CryptoRadar (`/market`) et univers Scanner (`/scanner-universe`) décrivent tous deux un « marché courant » | double vérité affichée | conserver les deux, libellés distincts (déjà le cas dans Marché → Scanner) |

## 5. Propriétaires désignés pour S4-b

| Donnée | Propriétaire unique |
|---|---|
| Octets des catalogues | producteur Scanner (`cat-scanner-universe`) |
| Univers commun | producteur Scanner |
| Admissibilité, scores, candidats | moteur Radar (`radar_selection`), hors ligne |
| Vérification et projection | `radar_projection` (S4-a) |
| Fraîcheur de publication, relation E1 | enveloppe de service S4-b |
| Affichage | frontend S4-c (non commencé) |
