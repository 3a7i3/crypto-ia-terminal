# Design — Scanner 500-1000 paires (paliers 2-3 de l'ADR-0017)

**Statut : spécification préparatoire** (demande opérateur 2026-07-16 —
« prépare aussi le chantier des +500 paires : refonte du scanner,
screening batch → analyse fine du top-K, ou websockets »).
Aucune implémentation avant l'activation du palier 1 (ADR-0017) et sa
validation en charge.

## 1. État actuel et pourquoi il plafonne

Le moteur (`core/advisor_loop.py`) traite les paires **séquentiellement**
dans chaque cycle de 300 s : pour chaque paire, `fetch_ohlcv` multi-timeframe
(~3 appels), features, scoring, gates. Mesuré : ~28 paires ≈ 60-90 s/cycle.

Extrapolation linéaire :
| Univers | Temps de cycle estimé | Verdict |
|---|---|---|
| 28 (actuel) | 60-90 s | OK |
| 100-200 (palier 1) | 4-8 min | limite — étalement requis (T4 ADR-0017) |
| 500 | 15-25 min | impossible en cycle 300 s |
| 1000 | 30-50 min | impossible |

Contraintes : rate limit MEXC (~20 req/s, marge OK), CPU 2 vCPU (large marge,
load actuel 0.04), RAM 8 Go (moteur ~1 Go à 28 paires — les bougies par paire
sont le poste qui croît).

## 2. Architecture cible — pipeline à deux étages

### Étage A — Screening batch (déjà en production, ADR-0016)

Le pouls (2 `fetch_tickers`, 15 min, 3200 paires) + le radar R1 (shortlist
200) + R2 (horizons) constituent l'étage de screening : ils désignent en
continu QUELLES paires méritent l'analyse fine. Coût : 2 appels/15 min.

### Étage B — Analyse fine sur rotation top-K (option recommandée, palier 2)

Le moteur n'analyse en profondeur que **K paires par cycle** (K ≈ 60-80),
choisies par priorité :
1. paires avec position ouverte (toujours) ;
2. paires « chaudes » du screening (mouvement/volume récent au-dessus du
   percentile configuré) ;
3. rotation round-robin du reste de l'univers (chaque paire revisitée au
   moins toutes les N minutes).

Propriétés : aucune refonte du pipeline d'analyse (on change l'ordonnanceur,
pas l'analyse) ; dégradation linéaire contrôlée ; univers 500-1000 couvert
avec une latence de revisite bornée et mesurable. **C'est l'option à
implémenter d'abord** — réversible, testable, sans nouvelle dépendance.

Chiffrage : K=70 × 3 TF = ~210 appels OHLCV/cycle ≈ 1,2 appel/s — trivial
pour le rate limit. Revisite complète d'un univers de 500 en ~7 cycles
(35 min) hors paires chaudes, prioritaires à chaque cycle.

### Étage C — Websockets (option palier 3, si nécessaire)

Flux klines/tickers temps réel (ccxt.pro ou WS MEXC natif) alimentant un
cache de bougies en mémoire ; l'analyse devient événementielle (déclenchée
par mouvement) au lieu de cyclique. Gains : latence de détection ; coûts :
nouvelle dépendance, gestion de reconnexion, RAM (~bougies de 1000 paires
en mémoire ≈ 1-2 Go), complexité de test. **Ne se justifie que si la
revisite bornée de l'étage B se révèle insuffisante, mesures à l'appui.**

## 3. Ce que ça NE change pas

- Les seuils par régime, les gates, le sizing : identiques (ADR-0017 §3).
- L'épinglage : l'univers du palier reste une liste fixe décidée par ADR.
- La passivité des observateurs (ADR-0007) : le screening désigne des
  candidats à ANALYSER, il n'autorise aucun trade — le pipeline de décision
  complet s'applique à chaque candidat.

## 4. Pré-requis et jalons

1. Palier 1 (100-200, ADR-0017) actif et stable ≥ 1 semaine — mesure T4
   réelle du coût par paire.
2. Implémentation étage B derrière un flag (`SCANNER_TOPK_ENABLED`),
   dry-run comparatif (mêmes décisions que le scanner séquentiel sur
   l'univers courant — test d'équivalence).
3. Activation palier 2 (500) par révision ADR-0017, époque inchangée
   (V4 continue — l'univers ne change que par palier acté).
4. Étage C : décision séparée, uniquement sur mesures de l'étage B.

## 5. Points ouverts

- MEXC ne fournit pas d'OHLCV batch : l'étage B reste du fetch par paire
  (étalé) ; vérifier si `fetch_ohlcv` swap et spot ont des limites
  différentes.
- Mémoire des features par paire : purge des caches pour les paires hors
  rotation depuis > X h.
- Telegram : les agrégats T5 (ADR-0017) doivent tenir à 1000 paires
  (compteurs par régime uniquement, top fixe).
