# RFC-001 — MarketScanner V2 : Plateforme de Données de Marché

**Statut :** DRAFT  
**Auteur :** Projet crypto_ai_terminal  
**Date :** 2026-06-20  
**Révision :** 0.1  
**Périmètre :** Architecture et contrats — aucune implémentation

---

## Table des matières

1. [Contexte et motivation](#1-contexte-et-motivation)
2. [Objectifs](#2-objectifs)
3. [Non-objectifs](#3-non-objectifs)
4. [Contraintes](#4-contraintes)
5. [Terminologie](#5-terminologie)
6. [Architecture générale](#6-architecture-générale)
7. [Entité centrale : MarketSnapshot](#7-entité-centrale--marketsnapshot)
8. [Contrats par composant](#8-contrats-par-composant)
9. [États du système](#9-états-du-système)
10. [Invariants](#10-invariants)
11. [Budgets de performance](#11-budgets-de-performance)
12. [SLA internes](#12-sla-internes)
13. [Matrice des pannes](#13-matrice-des-pannes)
14. [Contrat de qualité (SnapshotQuality)](#14-contrat-de-qualité-snapshotquality)
15. [Observabilité](#15-observabilité)
16. [Scalabilité chiffrée](#16-scalabilité-chiffrée)
17. [Stratégie de migration V1 → V2](#17-stratégie-de-migration-v1--v2)
18. [Critères d'acceptation](#18-critères-dacceptation)
19. [Roadmap](#19-roadmap)
20. [Annexes](#20-annexes)

---

## 1. Contexte et motivation

### 1.1 Situation actuelle (V1)

Le MarketScanner V1 est un composant monolithique intégré directement dans `advisor_loop.py`. Il assume simultanément :

- La gestion des sessions exchange (authentification, reconnexion)
- La collecte des données de marché (OHLCV, orderbook, ticker)
- La construction des snapshots
- Le rate limiting et les retries
- La publication vers le Decision Engine

Cette architecture a permis de livrer rapidement les premières phases du projet et d'accumuler 153+ trades paper avec un système stable. Elle atteint aujourd'hui ses limites structurelles.

### 1.2 Limites observées pendant le burn-in

Les audits et le monitoring de production ont mis en évidence :

| Limite | Impact observé |
|---|---|
| Couplage I/O ↔ Décision | Le Decision Engine subit la latence réseau |
| Snapshot non contractualisé | Cohérence temporelle non garantie |
| Pas de qualité de snapshot | HOLD impossible sans connaissance du Collector |
| Absence d'état explicite | Mode dégradé non détectable automatiquement |
| Rate limiter interne au scan | Pas d'isolation entre collecte et décision |
| Pas de métriques Collector | Impossible de détecter une dérive de latence |

### 1.3 Déclencheur de V2

L'objectif de passer de 50 à 500–1000 actifs impose une refonte architecturale. Un composant monolithique ne peut pas absorber cette charge sans devenir un point de contention unique qui dégrade simultanément la collecte et la prise de décision.

### 1.4 Décision stratégique

Le MarketScanner cesse d'être un **module** et devient un **service de données** avec ses propres contrats, métriques et objectifs de performance. Le Decision Engine ne fera plus jamais d'I/O réseau.

---

## 2. Objectifs

**O-01** — Isoler complètement le Decision Engine de toute opération réseau.

**O-02** — Définir `MarketSnapshot` comme entité contractuelle officielle, seule interface entre Collector et Decision Engine.

**O-03** — Garantir la cohérence temporelle des snapshots (skew maximal défini et mesuré).

**O-04** — Permettre la montée en charge de 50 à 1000 actifs sans refactoring architectural.

**O-05** — Rendre le mode dégradé détectable, gérable et réversible automatiquement.

**O-06** — Produire des métriques d'observabilité suffisantes pour opérer le système en production sans accès aux logs.

**O-07** — Permettre la migration V1 → V2 sans interruption de service et sans perte de comparabilité des données.

**O-08** — Définir des contrats d'entrée/sortie suffisamment précis pour permettre un développement indépendant des composants.

---

## 3. Non-objectifs

**NO-01** — Cette RFC ne spécifie aucune implémentation Python, aucun algorithme, aucune dépendance.

**NO-02** — La stratégie de scoring et le Decision Engine ne font pas partie de ce périmètre.

**NO-03** — L'intégration d'exchanges supplémentaires (Binance, Bybit) n'est pas dans V2. L'architecture doit le permettre, pas le livrer.

**NO-04** — La persistance longue durée des snapshots (time series database) est hors périmètre. V2 ne fait que du cache opérationnel.

**NO-05** — Le back-testing et la simulation ne font pas partie de V2. L'architecture doit garantir que V2 peut alimenter un back-testeur, sans le construire.

---

## 4. Contraintes

**C-01 — Gel du code pendant le burn-in.** RFC-001 est un document de conception. Aucune ligne de code ne sera produite avant que le burn-in F-01 ait rendu son verdict.

**C-02 — Rétrocompatibilité des trades.** Le format `paper_trades.jsonl` (schema v3) ne doit pas être rompu. Toute évolution de schema doit être additive.

**C-03 — Single exchange (MEXC).** V2 doit supporter MEXC en premier. L'abstraction doit permettre l'ajout d'autres exchanges sans refactoring du Collector.

**C-04 — VPS monocœur / mémoire limitée.** L'architecture doit fonctionner sur un VPS entrée de gamme (2 vCPU, 4 GB RAM). Le parallélisme doit être contrôlé.

**C-05 — Gouvernance des paramètres.** Toute modification de paramètre critique doit passer par `parameter_audit.py` et produire un `change_id`. Cette contrainte héritée de `230bff4` s'applique à V2.

**C-06 — Pas de base de données supplémentaire.** V2 utilise le système de fichiers (JSONL, JSON) comme V1. Pas de Redis, pas de SQLite pour le cache snapshot.

---

## 5. Terminologie

| Terme | Définition |
|---|---|
| **Exchange** | Plateforme de trading (MEXC en V2) |
| **Universe** | Ensemble des symboles surveillés (50 en V2, extensible à 1000) |
| **OHLCV** | Open/High/Low/Close/Volume — données de chandelier |
| **Snapshot** | Capture cohérente de l'état du marché à un instant T |
| **Collector** | Composant responsable de la collecte des données brutes |
| **SnapshotBuilder** | Composant responsable de l'assemblage d'un Snapshot à partir des données brutes |
| **SnapshotCache** | Stockage en mémoire du dernier Snapshot valide par symbole |
| **Decision Engine** | Composant de scoring et de décision de trade — ne fait jamais d'I/O réseau |
| **Skew** | Écart temporel maximal entre les timestamps des données d'un même Snapshot |
| **collector_generation** | Entier incrémental identifiant chaque redémarrage du Collector |
| **SLA** | Service Level Agreement interne — engagement de disponibilité d'un composant |

---

## 6. Architecture générale

### 6.1 Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────┐
│                    COUCHE COLLECTE                           │
│                                                             │
│  Exchange ──► ExchangeSessionManager ──► ExchangeHandle     │
│                                               │             │
│                                               ▼             │
│                                      MarketCollector        │
│                                               │             │
│                                        OHLCVStream          │
│                                               │             │
│                                               ▼             │
│                                      SnapshotBuilder        │
│                                               │             │
│                                          MarketSnapshot     │
│                                               │             │
│                                               ▼             │
│                                       SnapshotCache         │
└───────────────────────────────────────────────┬─────────────┘
                                                │
                          ┌─────────────────────┘
                          │  lecture seule, pas d'I/O réseau
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    COUCHE DÉCISION                           │
│                                                             │
│                    Decision Engine                          │
│              (scoring, signaux, ordres)                     │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 Principe fondamental

La frontière entre les deux couches est **absolue** :

- La couche Collecte ne connaît pas les stratégies.
- La couche Décision ne connaît pas les exchanges.
- Toute communication entre les deux passe par `MarketSnapshot`.

### 6.3 Flux de données

```
ExchangeSessionManager
        │
        │ ExchangeHandle (session valide)
        ▼
MarketCollector
        │
        │ OHLCVStream (données brutes par symbole)
        ▼
SnapshotBuilder
        │
        │ MarketSnapshot (entité complète et cohérente)
        ▼
SnapshotCache
        │
        │ MarketSnapshot (lecture seule, dernier valide)
        ▼
Decision Engine
        │
        │ Signal(symbol, direction, score, config_version)
        ▼
  Execution Layer
```

---

## 7. Entité centrale : MarketSnapshot

`MarketSnapshot` est l'entité contractuelle la plus importante de V2. Elle est la **seule** interface entre le Collector et le Decision Engine.

### 7.1 Schéma

```
MarketSnapshot
──────────────────────────────────────────────────────
snapshot_id          : str     — identifiant unique (UUID4)
created_at           : float   — timestamp Unix UTC de création
universe             : list[str] — liste des symboles attendus
symbols_received     : list[str] — symboles effectivement présents
ohlcv                : dict[str, OHLCVFrame] — données par symbole
quality              : SnapshotQuality — indicateurs de qualité
latency              : SnapshotLatency — mesures de performance
version              : int     — version du schéma snapshot
collector_generation : int     — redémarrage du Collector (detect reset)
config_version       : str     — CFG-YYYYMMDD-NNNN (lien gouvernance)
```

### 7.2 OHLCVFrame (par symbole)

```
OHLCVFrame
──────────────────────────────────────────────────────
symbol     : str
timestamp  : float   — timestamp de la dernière bougie
open       : float
high       : float
low        : float
close      : float
volume     : float
source     : str     — "live" | "cache" | "synthetic"
age_s      : float   — âge en secondes au moment de l'assemblage
```

### 7.3 SnapshotLatency

```
SnapshotLatency
──────────────────────────────────────────────────────
fetch_ms    : float  — durée totale de la collecte réseau
build_ms    : float  — durée de l'assemblage du snapshot
skew_ms     : float  — max(timestamp) - min(timestamp) en ms
total_ms    : float  — fetch_ms + build_ms
```

### 7.4 Règles d'intégrité

1. Un `MarketSnapshot` ne peut pas être partiel. Si un symbole de l'Universe est absent et qu'aucune donnée cache n'est disponible, le snapshot est `INVALID` et ne doit pas atteindre le Decision Engine.
2. `created_at` est le timestamp de fin de l'assemblage, pas du début de la collecte.
3. `collector_generation` doit être comparé par le Decision Engine. Une discontinuité indique un redémarrage du Collector : les positions ouvertes doivent être réconciliées.
4. `config_version` est lu depuis `databases/runtime_config.json` au moment de la création du snapshot.

---

## 8. Contrats par composant

### 8.1 ExchangeSessionManager

**Responsabilité unique :** Maintenir une session valide vers un exchange.

```
Entrée :
  ExchangeConfig {
    exchange_id   : str       — identifiant exchange ("mexc")
    api_key       : str
    api_secret    : str
    testnet       : bool
    heartbeat_s   : int       — intervalle de ping
    timeout_ms    : int       — timeout par requête
  }

Sortie :
  ExchangeHandle {
    session       : object    — client exchange authentifié
    exchange_id   : str
    connected_at  : float
    generation    : int
  }

Garanties :
  — La session retournée est valide au moment de l'appel
  — Reconnexion automatique en cas de coupure (max 3 tentatives)
  — TTL de session respecté (renouvellement avant expiration)
  — Chaque reconnexion incrémente `generation`

Ne fait jamais :
  — Collecte de données de marché
  — Cache
  — Décision
  — Exposition de credentials hors du composant
```

### 8.2 MarketCollector

**Responsabilité unique :** Récupérer les données brutes pour un Universe donné.

```
Entrée :
  ExchangeHandle
  Universe : list[str]    — symboles à collecter
  Timeframe : str         — "1m" | "5m" | "15m"
  Limit : int             — nombre de bougies par symbole

Sortie :
  OHLCVStream {
    data       : dict[str, list[OHLCVBar]]  — données brutes par symbole
    fetched_at : float                       — timestamp de fin de collecte
    errors     : dict[str, str]              — symboles en erreur + raison
    duration_ms : float
  }

Garanties :
  — Rate limiting respecté (jamais plus de N requêtes / seconde)
  — Retry automatique (max 2 tentatives par symbole avant erreur)
  — Circuit breaker : si >20% de symboles en erreur, émettre DEGRADED
  — Timeout par symbole (configurable, défaut 2000ms)

Ne fait jamais :
  — Scoring
  — Décision
  — Modification du cache
  — Construction de snapshot
  — Connaissance des stratégies
```

### 8.3 SnapshotBuilder

**Responsabilité unique :** Assembler un `MarketSnapshot` cohérent.

```
Entrée :
  OHLCVStream
  SnapshotCache     — pour résolution des données manquantes
  Universe          — liste de référence pour détecter les absences

Sortie :
  MarketSnapshot    — entité complète (voir section 7)

Algorithme de résolution (par ordre de priorité) :
  1. Données "live" issues du stream
  2. Données "cache" issues du SnapshotCache (si âge < MAX_CACHE_AGE_S)
  3. Données "synthetic" (interpolation linéaire, flaggées)
  4. Symbole absent → snapshot INVALID si > MISSING_THRESHOLD

Garanties :
  — skew_ms < SKW_MAX_MS (défaut : 5000ms)
  — Chaque OHLCVFrame porte sa source ("live"|"cache"|"synthetic")
  — Snapshot invalide jamais transmis au Decision Engine

Ne fait jamais :
  — Requête réseau
  — Scoring
  — Modification de l'Universe
```

### 8.4 SnapshotCache

**Responsabilité unique :** Stocker et exposer le dernier Snapshot valide.

```
Entrée (écriture) :
  MarketSnapshot    — valide uniquement

Sortie (lecture) :
  MarketSnapshot | None

Garanties :
  — Thread-safe (lecture concurrent sans verrou si possible)
  — Écriture atomique (jamais de snapshot partiel lisible)
  — TTL par entrée (symbole expiré = None)
  — Jamais de snapshot INVALID en cache

Ne fait jamais :
  — Requête réseau
  — Calcul de features
  — Décision
```

### 8.5 Decision Engine

**Responsabilité unique :** Produire des signaux de trading à partir d'un Snapshot.

```
Entrée :
  MarketSnapshot

Sortie :
  list[Signal] {
    symbol              : str
    direction           : "BUY" | "SELL" | "HOLD"
    score               : int       — 0-100
    regime              : str
    config_version      : str       — hérité du snapshot
    snapshot_id         : str
    snapshot_age_ms     : float     — âge du snapshot au moment du scoring
  }

Garanties :
  — Temps d'exécution < 10ms pour 1000 symboles
  — Résultat déterministe pour un Snapshot identique
  — Jamais de HOLD silencieux : chaque HOLD a une raison

Interdit absolument :
  — HTTP / WebSocket / REST
  — sleep() / retry()
  — Accès réseau de toute nature
  — Modification du Snapshot entrant
  — Connaissance de l'ExchangeHandle
```

---

## 9. États du système

### 9.1 Machine d'états

```
                    ┌──────────────┐
                    │ INITIALIZING │
                    └──────┬───────┘
                           │ session ok + premier snapshot valide
                           ▼
                    ┌──────────────┐
               ┌───│   COLLECTING │◄──────────────┐
               │   └──────┬───────┘               │
               │          │ quality < QUALITY_MIN  │ quality >= QUALITY_MIN
               │          ▼                        │ ET recovering_cycles >= N
               │   ┌──────────────┐                │
               │   │   DEGRADED   │────────────────┘
               │   └──────┬───────┘
               │          │ erreurs critiques consécutives >= CIRCUIT_BREAKER_N
               │          ▼
               │   ┌──────────────┐
               │   │   HALTED     │
               │   └──────┬───────┘
               │          │ intervention manuelle uniquement
               │          │
               └──────────┼──────────────────────────────►
                          │ signal /shutdown ou SIGTERM
                          ▼
                    ┌──────────────┐
                    │   SHUTDOWN   │
                    └──────────────┘
```

### 9.2 Transitions et conditions

| De → Vers | Condition de déclenchement |
|---|---|
| INITIALIZING → COLLECTING | Session valide ET premier snapshot quality >= QUALITY_MIN |
| COLLECTING → DEGRADED | quality < QUALITY_MIN sur N cycles consécutifs (défaut N=3) |
| DEGRADED → COLLECTING | quality >= QUALITY_MIN sur M cycles consécutifs (défaut M=5) |
| DEGRADED → HALTED | erreurs critiques >= CIRCUIT_BREAKER_N (défaut 10) |
| HALTED → COLLECTING | Intervention manuelle via `/resume` Telegram uniquement |
| ANY → SHUTDOWN | Signal SIGTERM ou commande `/shutdown` |

### 9.3 Comportement du Decision Engine par état

| État Collector | Comportement Decision Engine |
|---|---|
| INITIALIZING | HOLD sur tous les symboles (pas de snapshot disponible) |
| COLLECTING | Normal |
| DEGRADED | Signaux autorisés si quality.real_ratio >= DEGRADED_MIN_REAL (défaut 0.7) |
| HALTED | HOLD sur tous les symboles, alerte Telegram immédiate |
| SHUTDOWN | Arrêt des signaux, fermeture des positions ouvertes |

---

## 10. Invariants

Les invariants sont des propriétés qui doivent être vraies à tout moment. Une violation est un bug, pas une situation de dégradation.

### 10.1 Invariants du Collector

```
INV-COL-01 : Jamais plus de RATE_LIMIT_MAX_RPS requêtes par seconde vers l'exchange.

INV-COL-02 : Un symbole en erreur n'interrompt pas la collecte des autres symboles.

INV-COL-03 : collector_generation est strictement croissant sur la durée de vie du processus.

INV-COL-04 : Les credentials d'API ne transitent jamais hors de ExchangeSessionManager.
```

### 10.2 Invariants du SnapshotBuilder

```
INV-SNP-01 : Aucun snapshot incomplet n'atteint le SnapshotCache ou le Decision Engine.

INV-SNP-02 : skew_ms est toujours calculé et présent dans SnapshotLatency.

INV-SNP-03 : Chaque OHLCVFrame indique sa source ("live"|"cache"|"synthetic").

INV-SNP-04 : created_at est toujours >= max(timestamp de tous les OHLCVFrame).
```

### 10.3 Invariants du Decision Engine

```
INV-DEC-01 : Aucun appel réseau, socket, ou I/O bloquant.

INV-DEC-02 : Résultat déterministe : même Snapshot → mêmes Signaux.

INV-DEC-03 : snapshot_age_ms dans chaque Signal est la durée réelle entre
             snapshot.created_at et le moment du scoring.

INV-DEC-04 : config_version dans chaque Signal est identique à celui du Snapshot entrant.
```

### 10.4 Invariants transversaux

```
INV-SYS-01 : Toute modification de paramètre critique produit une entrée dans
             runtime_parameter_audit.jsonl (hérité de 230bff4).

INV-SYS-02 : Tout trade OPEN embarque runtime_config_version (hérité de 230bff4).

INV-SYS-03 : Le système ne peut pas passer de DEGRADED à COLLECTING sans avoir
             produit N snapshots valides consécutifs.

INV-SYS-04 : Un snapshot dont quality.real_ratio = 0 (100% cache ou synthetic)
             ne déclenche jamais d'ordre. Il peut déclencher des HOLD explicites.
```

---

## 11. Budgets de performance

### 11.1 Budget par couche (cible : 50 actifs, P95)

| Couche | Budget | Métrique |
|---|---|---|
| ExchangeSessionManager (reconnexion) | < 2 000 ms | p95 |
| MarketCollector (fetch OHLCV 50 sym) | < 100 ms | p95 |
| SnapshotBuilder (assemblage) | < 50 ms | p95 |
| SnapshotCache (lecture) | < 1 ms | p99 |
| Decision Engine (scoring 50 sym) | < 10 ms | p99 |
| **Total cycle (collecte → signal)** | **< 250 ms** | **p95** |

### 11.2 Règle de composition

Le budget total est la somme des budgets couche par couche **plus** une marge de 20% pour le scheduling OS et les opérations transversales (logging, audit).

---

## 12. SLA internes

### 12.1 Disponibilité cible par composant

| Composant | SLA | Signification |
|---|---|---|
| ExchangeSessionManager | 99.90% | Session valide |
| MarketCollector | 99.95% | Collecte réussie (hors pannes exchange) |
| SnapshotBuilder | 99.99% | Snapshot valide produit si données disponibles |
| SnapshotCache | 99.999% | Lecture disponible |
| Decision Engine | 99.999% | Signal produit si snapshot disponible |

### 12.2 Latence par composant

| Composant | P50 | P95 | P99 | Worst Case |
|---|---|---|---|---|
| Collector (fetch 50 sym) | 60 ms | 100 ms | 200 ms | 2 000 ms |
| SnapshotBuilder | 10 ms | 50 ms | 100 ms | 500 ms |
| SnapshotCache read | < 0.5 ms | 1 ms | 2 ms | 10 ms |
| Decision Engine | 2 ms | 10 ms | 20 ms | 100 ms |
| **Cycle total** | **< 100 ms** | **< 250 ms** | **< 400 ms** | **< 3 000 ms** |

### 12.3 Définition du Worst Case

Le Worst Case correspond à une reconnexion simultanée à l'exchange et à un rebuilding complet du cache. Il doit rester en dessous du timeout de fermeture de position (configurable, défaut 30 000 ms).

---

## 13. Matrice des pannes

La matrice des pannes définit le comportement attendu du système pour chaque scénario de défaillance. Elle est la référence pour les runbooks opérationnels.

| # | Scénario | Détection | Comportement attendu | Sortie de crise |
|---|---|---|---|---|
| F-01 | Exchange HTTP HS (timeout) | Collector: timeout > 2s sur > 50% symboles | Utiliser SnapshotCache (source = "cache"). État → DEGRADED si N cycles consécutifs | Reconnexion automatique via ExchangeSessionManager |
| F-02 | WebSocket coupé | ExchangeSessionManager: ping timeout | Basculer sur REST polling. Alerte Telegram. collector_generation++ | Reconnexion WS automatique (max 3 tentatives) puis REST stable |
| F-03 | REST coupé (WebSocket OK) | Collector: erreurs HTTP sur > 80% symboles | Utiliser snapshot précédent pour les symboles manquants. source = "cache" | Retry automatique avec backoff exponentiel |
| F-04 | Exchange HS complet | ExchangeSessionManager: tous modes échouent | État → HALTED. HOLD sur tous signaux. Alerte Telegram critique | Intervention manuelle `/resume` après rétablissement exchange |
| F-05 | Snapshot incomplet (< MISSING_THRESHOLD) | SnapshotBuilder: symbols_missing > threshold | Snapshot non transmis. Utiliser dernier snapshot valide du cache | Prochain cycle de collecte |
| F-06 | Snapshot incomplet (> MISSING_THRESHOLD) | SnapshotBuilder: symbols_missing >> threshold | État → DEGRADED. Decision Engine reçoit signal quality.real_ratio bas | Prochain cycle avec données live |
| F-07 | Cache corrompu ou vide | SnapshotCache: lecture retourne None | SnapshotBuilder marque snapshot INVALID. Decision Engine → HOLD | Reconstruction au prochain cycle de collecte réussie |
| F-08 | Collector arrêté / crash | Decision Engine: absence de snapshot > MAX_SNAPSHOT_AGE_S | Decision Engine → HOLD automatique. Alerte Telegram. Watchdog redémarre Collector | Watchdog (processus externe) |
| F-09 | skew_ms > SKW_MAX_MS | SnapshotBuilder: écart temporel > seuil | Snapshot produit avec flag quality.skew_exceeded = True. Decision Engine peut choisir HOLD | Prochain cycle de collecte synchronisé |
| F-10 | Rate limit exchange déclenché | Collector: HTTP 429 reçu | Pause Collector X secondes (backoff). Utiliser cache. Incrémenter rate_limit_hits | Reprise automatique après fenêtre de rate limit |

---

## 14. Contrat de qualité (SnapshotQuality)

`SnapshotQuality` est l'interface par laquelle le Decision Engine évalue la fiabilité d'un Snapshot sans avoir connaissance de l'état interne du Collector.

### 14.1 Schéma

```
SnapshotQuality
──────────────────────────────────────────────────────
real_ratio       : float  — fraction de symboles avec données live [0.0, 1.0]
cached_ratio     : float  — fraction de symboles depuis le cache [0.0, 1.0]
synthetic_ratio  : float  — fraction de symboles interpolés [0.0, 1.0]
missing_ratio    : float  — fraction de symboles absents [0.0, 1.0]
skew_ms          : float  — max(ts) - min(ts) en millisecondes
age_s            : float  — âge du snapshot au moment de la lecture (Decision Engine)
missing_symbols  : list[str] — symboles absents
retry_count      : int    — nombre de retries pendant la collecte
skew_exceeded    : bool   — True si skew_ms > SKW_MAX_MS
is_valid         : bool   — False si snapshot ne doit pas déclencher d'ordre
```

### 14.2 Invariants de SnapshotQuality

```
real_ratio + cached_ratio + synthetic_ratio + missing_ratio = 1.0  (± 1e-6)
```

### 14.3 Règles de décision du Decision Engine

Le Decision Engine doit appliquer ces règles dans l'ordre, sans connaissance de l'état interne du Collector :

| Condition | Action Decision Engine |
|---|---|
| `is_valid = False` | HOLD sur tous symboles. Ne pas logger comme opportunité manquée. |
| `real_ratio < 0.50` | HOLD sur tous symboles. Logger "snapshot_quality_too_low". |
| `missing_ratio > 0.20` | Exclure les symboles manquants. Continuer sur le reste. |
| `skew_exceeded = True` | HOLD sur symboles dont `age_s > AGE_THRESHOLD_S`. |
| `age_s > MAX_SNAPSHOT_AGE_S` | HOLD sur tous symboles. Logger "snapshot_stale". |
| `synthetic_ratio > 0.30` | Réduire la conviction de tous les signaux. |
| Sinon | Normal. |

### 14.4 Seuils recommandés (configurables)

| Paramètre | Valeur défaut | Description |
|---|---|---|
| `QUALITY_MIN` | 0.85 | real_ratio minimum pour état COLLECTING |
| `DEGRADED_MIN_REAL` | 0.70 | real_ratio minimum pour signaux en mode DEGRADED |
| `SKW_MAX_MS` | 5 000 | skew maximal acceptable en ms |
| `MAX_SNAPSHOT_AGE_S` | 120 | âge maximal d'un snapshot pour le Decision Engine |
| `MISSING_THRESHOLD` | 0.20 | fraction manquante déclenchant DEGRADED |
| `AGE_THRESHOLD_S` | 60 | âge par symbole au-delà duquel HOLD sur ce symbole |

---

## 15. Observabilité

### 15.1 Métriques officielles (API V2)

Ces métriques sont des **contrats**, pas des détails d'implémentation. Chaque composant est tenu de les exposer.

#### Collector

| Métrique | Type | Description |
|---|---|---|
| `collector_fetch_ms` | histogram | Durée collecte complète par cycle |
| `collector_symbols_ok` | counter | Symboles collectés avec succès |
| `collector_symbols_error` | counter | Symboles en erreur |
| `collector_rate_limit_hits` | counter | HTTP 429 reçus |
| `collector_retries` | counter | Tentatives de retry |
| `collector_ws_reconnects` | counter | Reconnexions WebSocket |
| `collector_generation` | gauge | Génération courante du Collector |
| `collector_queue_depth` | gauge | Profondeur de la file d'attente interne |

#### SnapshotBuilder

| Métrique | Type | Description |
|---|---|---|
| `snapshot_build_ms` | histogram | Durée d'assemblage d'un snapshot |
| `snapshot_skew_ms` | histogram | Skew temporel par snapshot |
| `snapshot_real_ratio` | histogram | Fraction live par snapshot |
| `snapshot_cached_ratio` | histogram | Fraction cache par snapshot |
| `snapshot_synthetic_ratio` | histogram | Fraction synthétique par snapshot |
| `snapshot_missing_symbols` | counter | Symboles absents cumulés |
| `snapshot_invalid_count` | counter | Snapshots invalides (non transmis) |
| `snapshot_frequency_hz` | gauge | Fréquence de production de snapshots |

#### SnapshotCache

| Métrique | Type | Description |
|---|---|---|
| `cache_hit_ratio` | gauge | Fraction des lectures satisfaites par le cache |
| `cache_miss_count` | counter | Lectures sans résultat |
| `cache_entries` | gauge | Nombre d'entrées courantes |
| `cache_eviction_count` | counter | Entrées expirées/évincées |

#### Decision Engine

| Métrique | Type | Description |
|---|---|---|
| `decision_age_ms` | histogram | Âge du snapshot au moment du scoring |
| `decision_cycle_ms` | histogram | Durée totale d'un cycle de décision |
| `decision_signals_total` | counter | Signaux produits (par direction) |
| `decision_hold_quality` | counter | HOLD dus à une qualité insuffisante |
| `decision_hold_stale` | counter | HOLD dus à un snapshot trop vieux |

#### Cycle global

| Métrique | Type | Description |
|---|---|---|
| `scan_wall_ms` | histogram | Durée totale d'un cycle complet |
| `snapshot_age_at_decision_ms` | histogram | Âge du snapshot quand le Decision Engine l'utilise |
| `lock_wait_ms` | histogram | Temps d'attente sur les verrous partagés |

### 15.2 Alertes obligatoires

| Condition | Sévérité | Canal |
|---|---|---|
| État → HALTED | CRITICAL | Telegram immédiat |
| État → DEGRADED (> 10 min) | HIGH | Telegram |
| `snapshot_age_at_decision_ms` > 60 000ms | HIGH | Log + Telegram |
| `collector_rate_limit_hits` > 10 / heure | MEDIUM | Log |
| `snapshot_invalid_count` > 5 / heure | MEDIUM | Log |
| `collector_ws_reconnects` > 3 / heure | LOW | Log |

---

## 16. Scalabilité chiffrée

### 16.1 Objectifs de latence par volume d'actifs

| Actifs | Budget cycle (P95) | Budget décision (P99) |
|---:|---:|---:|
| 50 | < 250 ms | < 10 ms |
| 100 | < 400 ms | < 15 ms |
| 250 | < 600 ms | < 25 ms |
| 500 | < 800 ms | < 40 ms |
| 1 000 | < 1 000 ms | < 80 ms |

Ces chiffres supposent un VPS 2 vCPU / 4 GB RAM. Un VPS 4 vCPU permettrait de diviser par 1.5 les budgets collecte.

### 16.2 Points de contention identifiés

| Actifs | Goulot d'étranglement probable |
|---:|---|
| 50–100 | Rate limiting exchange (HTTP) |
| 100–250 | Assemblage SnapshotBuilder (CPU séquentiel) |
| 250–500 | Mémoire (OHLCVStream non compressé) |
| 500–1000 | GIL Python (parallélisation à prévoir) |

### 16.3 Stratégies de mitigation par palier

| Palier | Mitigation |
|---|---|
| 50–100 | Architecture V2 de base (aucune mitigation supplémentaire) |
| 100–250 | Parallélisation collecte par batch (ThreadPoolExecutor contrôlé) |
| 250–500 | Compression mémoire OHLCVStream (numpy arrays vs dict) |
| 500–1000 | Multiprocessing pour SnapshotBuilder ou WebSocket natif |

---

## 17. Stratégie de migration V1 → V2

### 17.1 Phases

```
Phase 0 — Préparation
        │ Tests sur V1 au vert. Métriques baseline V1 documentées.
        │ RFC-001 approuvée. Aucun changement de comportement.
        ▼
Phase 1 — Dual Collector
        │ V2 tourne en parallèle de V1. Les deux collectent.
        │ V2 ne transmet PAS au Decision Engine.
        │ Comparaison automatique : V1_snapshot vs V2_snapshot.
        ▼
Phase 2 — Shadow Mode
        │ V2 alimente un Decision Engine shadow (pas d'ordres réels).
        │ V1 continue d'alimenter le Decision Engine de production.
        │ Comparaison des signaux V1 vs V2.
        ▼
Phase 3 — Switch
        │ V2 devient la source principale du Decision Engine.
        │ V1 tourne encore 48h en lecture seule (fallback).
        ▼
Phase 4 — Suppression V1
        │ V1 retiré après 48h sans incident.
        │ Post-mortem migration documenté.
        ▼
Phase 5 — Stabilisation
        │ 7 jours d'observation sur V2 seul.
        │ Métriques comparées avec baseline V1.
```

### 17.2 Critères de sortie par phase

| Phase | Critères de sortie |
|---|---|
| 0 → 1 | RFC approuvée. Tests V1 ≥ 95% verts. Métriques baseline documentées. |
| 1 → 2 | V2 produit des snapshots valides (real_ratio ≥ 0.85) pendant 48h consécutives. Skew V2 ≤ skew V1. |
| 2 → 3 | Taux de concordance signaux V1 vs V2 ≥ 95% sur 7 jours. Aucun signal HALTED non prévu. |
| 3 → 4 | 48h sans incident en production V2. Aucune alerte CRITICAL. |
| 4 → 5 | Suppression V1 sans régression. Métriques V2 dans les budgets. |

### 17.3 Plan de rollback

À toute phase, le retour à la phase précédente doit être possible en moins de 5 minutes par redémarrage de configuration.

Interdit : migration directe V1 → production V2 sans Dual Run et Shadow.

---

## 18. Critères d'acceptation

### 18.1 Fonctionnels

| ID | Critère | Priorité |
|---|---|---|
| AC-F-01 | Le Decision Engine ne fait aucun appel réseau. Vérifiable par mock total de network. | BLOQUANT |
| AC-F-02 | Un snapshot invalide ne déclenche aucun ordre. | BLOQUANT |
| AC-F-03 | La perte d'un symbole n'interrompt pas la collecte des autres. | BLOQUANT |
| AC-F-04 | collector_generation est incrémenté à chaque redémarrage. | BLOQUANT |
| AC-F-05 | Chaque OHLCVFrame indique sa source. | BLOQUANT |
| AC-F-06 | Un changement de paramètre via Telegram produit une entrée dans l'audit. | BLOQUANT (hérité 230bff4) |
| AC-F-07 | Chaque signal produit embarque snapshot_id, snapshot_age_ms, config_version. | BLOQUANT |

### 18.2 Performance

| ID | Critère | Priorité |
|---|---|---|
| AC-P-01 | Cycle complet < 250ms P95 avec 50 actifs. | BLOQUANT |
| AC-P-02 | Decision Engine < 10ms P99 avec 50 actifs. | BLOQUANT |
| AC-P-03 | Cycle complet < 400ms P95 avec 100 actifs. | FORTEMENT RECOMMANDÉ |
| AC-P-04 | Aucune dégradation des métriques V1 après migration. | FORTEMENT RECOMMANDÉ |

### 18.3 Résilience

| ID | Critère | Priorité |
|---|---|---|
| AC-R-01 | Panne exchange complète → HALTED en < 30s. | BLOQUANT |
| AC-R-02 | Reconnexion automatique WebSocket sans intervention manuelle. | BLOQUANT |
| AC-R-03 | Cache corrompu → rebuild au cycle suivant sans crash. | BLOQUANT |
| AC-R-04 | HALTED → COLLECTING uniquement via `/resume` Telegram. | BLOQUANT |

### 18.4 Observabilité

| ID | Critère | Priorité |
|---|---|---|
| AC-O-01 | Toutes les métriques de la section 15 sont exposées. | BLOQUANT |
| AC-O-02 | Alerte Telegram en < 60s pour état HALTED. | BLOQUANT |
| AC-O-03 | `scan_wall_ms` disponible dans chaque rapport Telegram. | FORTEMENT RECOMMANDÉ |

---

## 19. Roadmap

### 19.1 Pré-conditions avant implémentation

- [ ] Burn-in F-01 verdict rendu (GO / NO-GO)
- [ ] RFC-001 approuvée par révision
- [ ] Tests unitaires V1 existants tous au vert
- [ ] Métriques baseline V1 documentées (latence, qualité snapshot, taux erreur)

### 19.2 Phases d'implémentation

| Phase | Contenu | Durée estimée | Critère d'entrée |
|---|---|---|---|
| **P1 — Fondations** | ExchangeSessionManager + contrat MarketSnapshot + SnapshotQuality | 1 semaine | RFC approuvée |
| **P2 — Collector** | MarketCollector + rate limiter + circuit breaker + métriques | 1 semaine | P1 tests verts |
| **P3 — SnapshotBuilder** | Assemblage + résolution fallback + invariants | 1 semaine | P2 tests verts |
| **P4 — Cache + Engine** | SnapshotCache + isolation Decision Engine | 1 semaine | P3 tests verts |
| **P5 — Migration** | Dual Run + Shadow + Switch + Suppression V1 | 2 semaines | P4 tests verts + critères migration |
| **P6 — Scalabilité** | Batch 100–250 actifs + métriques avancées | 1 semaine | P5 stable 7j |

### 19.3 Ce que V2 ouvre après livraison

- Multi-exchange (Binance, Bybit) par ajout d'un ExchangeConfig
- Back-testeur alimenté par SnapshotCache replay
- Détection de divergence entre exchanges (arbitrage observationnel)
- Montée à 500–1000 actifs par itération sur la couche Collector

---

## 20. Annexes

### Annexe A — Décisions architecturales rejetées

**A.1 — Redis comme SnapshotCache**

Rejeté : dépendance externe, latence réseau interne, complexité opérationnelle sur VPS. La contrainte C-06 (pas de base de données supplémentaire) s'applique.

**A.2 — Kafka / message queue entre Collector et Decision Engine**

Rejeté : latence non déterministe, complexité infra, hors budget VPS. Le contrat synchrone via SnapshotCache est suffisant pour V2.

**A.3 — Snapshot stocké en base de données**

Rejeté : non-objectif NO-04. Le cache opérationnel en mémoire est suffisant. La persistance longue durée est une évolution future.

**A.4 — Multiprocessing dès V2**

Rejeté : complexité de synchronisation, problème de partage mémoire. Réservé à V3 si la scalabilité l'exige. Le palier 500–1000 actifs est une amélioration future, pas un objectif V2.

### Annexe B — Questions ouvertes

| # | Question | Impact | Décision requise avant |
|---|---|---|---|
| Q-01 | Faut-il exposer les métriques via HTTP (Prometheus) ou seulement en JSONL ? | Moyen | Phase P1 |
| Q-02 | Le SnapshotCache doit-il supporter plusieurs Timeframes simultanés ? | Haut | Phase P3 |
| Q-03 | Le Decision Engine doit-il recevoir l'historique des snapshots ou seulement le dernier ? | Haut | Phase P4 |
| Q-04 | Comment gérer les symboles ajoutés/retirés de l'Universe en cours de run ? | Moyen | Phase P2 |

### Annexe C — Liens avec les ADR existants

| ADR | Relation |
|---|---|
| ADR-0001 (architecture 4 couches) | V2 renforce la séparation Collecte / Décision déjà posée |
| ADR-0002 (domain objects SSoT) | MarketSnapshot est le domain object central de V2 |
| 230bff4 (parameter audit) | INV-SYS-01 et INV-SYS-02 héritent directement |

---

*RFC-001 — Révision 0.1 — 2026-06-20 — DRAFT*  
*Prochain jalon : révision institutionnelle avant implémentation.*
