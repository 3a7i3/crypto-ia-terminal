# ADR-001 — Architecture cible du Market Scanner Quant

**Statut :** DRAFT — en attente de validation post burn-in  
**Date :** 2026-06-16  
**Auteur :** Mathieu (architecture) / Claude Sonnet 4.6 (rédaction)  
**Contexte :** Système en burn-in. Ce document est exclusivement prospectif. Aucune modification de code n'est proposée.

---

## Table des matières

1. [Audit de l'architecture actuelle](#1-audit-de-larchitecture-actuelle)
2. [Limites de l'architecture actuelle](#2-limites-de-larchitecture-actuelle)
3. [Architecture cible](#3-architecture-cible)
4. [Pipeline de données](#4-pipeline-de-données)
5. [Stratégie de concurrence](#5-stratégie-de-concurrence)
6. [Gestion des données](#6-gestion-des-données)
7. [Thread Safety](#7-thread-safety)
8. [Observabilité](#8-observabilité)
9. [Plan de migration](#9-plan-de-migration)
10. [Registre des risques](#10-registre-des-risques)
11. [Décisions d'architecture](#11-décisions-darchitecture)
12. [Recommandation finale](#12-recommandation-finale)

---

## 1. Audit de l'architecture actuelle

### 1.1 Vue d'ensemble

Le système est un pipeline de trading algorithmique organisé en **6 couches séquentielles**, orchestrées par une boucle principale (`advisor_loop.py`) qui s'exécute toutes les **300 secondes** (5 minutes).

Le cycle complet pour 50 symboles s'exécute en **700 ms à 2 000 ms**, selon l'état du cache.

---

### 1.2 Composants et dépendances

| Couche | Composant | Fichier | Lignes | Rôle |
|--------|-----------|---------|--------|------|
| Signal | `MarketScanner` | `agents/market/market_scanner.py` | 827 | Fetch OHLCV via REST CCXT |
| Signal | `MultiTimeframeScanner` | `agents/market/multi_timeframe_scanner.py` | 146 | Fetch parallèle 1m/15m/4h/1d |
| Cache | `StartupCache` | `infra/startup_cache.py` | 172 | Cache bootstrap JSON/pickle |
| Intelligence | `LiveSignalEngine` | `agents/execution/live_signal_engine.py` | 608 | Scoring MTF + régime + mémoire |
| Intelligence | `AIAdvisor` | `agents/intelligence/ai_advisor.py` | ~250 | Génération de conseil textuel |
| Exécution | `ExecutionEngine` | `agents/execution/execution_engine.py` | 524 | Ordres CCXT + dedup + garde |
| Apprentissage | `MistakeMemory` | `agents/intelligence/mistake_memory.py` | 642 | Blocage pré-trade + analyse post-trade |
| Orchestration | `advisor_loop.main()` | `core/advisor_loop.py` | **6 381** | Boucle principale + coordination |
| Orchestration | `advisor_main` (P10-B) | `runtime/advisor_main.py` | ~428 | Remplacement strangler (en cours) |

---

### 1.3 Pipeline complet (flux d'exécution)

```
DÉMARRAGE (2-3 secondes)
├── SessionPrimer (background thread)     → création CCXT + load_markets()     ~100 ms
├── MarketScanner init (×N symboles)      → allocations mémoire                ~200 ms
├── PrewarmCache (ThreadPoolExecutor)     → fetch 1h en parallèle              ~1-2 s
└── ExecutionEngine + RiskGates init                                            ~500 ms

CYCLE (toutes les 300 secondes)
├── Kill Switch check
├── POUR CHAQUE SYMBOLE (séquentiel) :
│   ├── [1] SCAN         — MarketScanner.scan()          → REST CCXT + cache   50-300 ms
│   ├── [2] MTF MERGE    — MultiTimeframeScanner         → ThreadPoolExecutor  100-400 ms
│   ├── [3] FEATURES     — calcul RSI/MACD/EMA/ATR       → CPU pur             5-15 ms
│   ├── [4] RÉGIME       — AdvancedRegimeDetector        → CPU pur             3-8 ms
│   ├── [5] SIGNAL       — LiveSignalEngine.evaluate()   → CPU pur             5-15 ms
│   ├── [6] BLOCAGE      — MistakeMemory.check()         → JSONL read          1-3 ms
│   ├── [7] CONSEIL      — AIAdvisor.generate()          → LM Studio ou règles 10-100 ms
│   ├── [8] RISQUE       — GlobalRiskGate.validate()     → CPU pur             5-15 ms
│   └── [9] EXÉCUTION    — ExecutionEngine.execute()     → REST CCXT           50-500 ms
├── [10] APPRENTISSAGE   — MistakeMemory.record()        → JSONL write         1-5 ms
├── [11] REPORTING       — Telegram                      → HTTP                 50-200 ms
└── SLEEP (temps restant jusqu'à 300 s)
```

---

### 1.4 Modèle de concurrence actuel

```
advisor_loop (thread principal)
│
├── SessionPrimer            → threading.Thread (background, cycle 1 only)
├── PrewarmCache             → ThreadPoolExecutor (background, boot only)
├── MultiTimeframeScanner    → ThreadPoolExecutor (FIRST_COMPLETED per TF)
└── MarketScanner.pool       → threading.Lock (protection pool CCXT partagé)

Boucle principale : BLOQUANTE-SYNCHRONE
Fetch OHLCV : REST polling (pas de WebSocket)
Feature calc : CPU séquentiel
Écriture JSONL : append-only séquentiel
```

---

### 1.5 I/O par composant

| Composant | Type I/O | Fréquence | Latence estimée |
|-----------|----------|-----------|-----------------|
| MarketScanner | HTTP REST (CCXT) | Par symbole par cycle | 50-300 ms (cold) / 0 ms (cache) |
| MultiTimeframeScanner | HTTP REST (CCXT ×TF) | Tous les 12 cycles | 100-400 ms |
| ExecutionEngine | HTTP REST (CCXT) | Sur signal actionnable | 50-500 ms |
| AIAdvisor | HTTP (LM Studio :1234) | Sur signal ≥ 70 | 10-100 ms |
| MistakeMemory | Fichier JSONL | Post-trade | 1-5 ms |
| StartupCache | Fichier JSON/pickle | Boot + snapshots | 1-10 ms |
| Telegram | HTTP | Tous les 3 cycles | 50-200 ms |
| SQLite (TradeLogger) | Fichier | Par ordre exécuté | 1-5 ms |

---

### 1.6 Temps de cycle mesuré

| Phase | Cycle froid (cache vide) | Cycle chaud (cache actif) |
|-------|--------------------------|--------------------------|
| Signal (50 symboles) | ~500 ms | ~50 ms |
| Intelligence (50 symboles) | ~1 000 ms | ~500 ms |
| Décision + Risque | ~60 ms | ~60 ms |
| Exécution (si ordre) | ~100 ms | ~100 ms |
| Apprentissage | ~5 ms | ~5 ms |
| **Total** | **~1 700-2 000 ms** | **~700-800 ms** |

---

### 1.7 Diagramme de flux simplifié

```
┌────────────────────────────────────────────────────────────────────┐
│ advisor_loop (thread principal, cycle 5 min)                       │
│                                                                    │
│  SYMBOLE[0] ──► SCAN ──► MTF ──► FEATURE ──► RÉGIME ──► SIGNAL  │
│  SYMBOLE[1] ──► SCAN ──► MTF ──► FEATURE ──► RÉGIME ──► SIGNAL  │
│  ...                                                               │
│  SYMBOLE[N] ──► SCAN ──► MTF ──► FEATURE ──► RÉGIME ──► SIGNAL  │
│                                                    │               │
│                                             SÉLECTION (meilleur)  │
│                                                    │               │
│                                          CHECK MistakeMemory       │
│                                                    │               │
│                                          GlobalRiskGate            │
│                                                    │               │
│                                          ExecutionEngine ──► CCXT │
│                                                    │               │
│                                      MistakeMemory.record()        │
│                                                    │               │
│                                         Telegram report            │
│                                                    │               │
│                                           SLEEP (reste 300s)       │
└────────────────────────────────────────────────────────────────────┘

          MarketScanner pool     MultiTF ThreadPool
          ──────────────────     ──────────────────
          threading.Lock          ThreadPoolExecutor
          (partagé entre         (parallèle par TF,
           instanciations)        FIRST_COMPLETED)
```

---

## 2. Limites de l'architecture actuelle

### 2.1 Tableau des limites

| # | Limite | Domaine | Sévérité | Justification |
|---|--------|---------|----------|---------------|
| L-01 | Boucle principale synchrone / séquentielle | Scalabilité | **Critique** | Temps de scan croît linéairement avec le nombre de symboles. 200 symboles = 4× plus lent. |
| L-02 | REST polling (pas de WebSocket) | Latence | **Critique** | Chaque fetch = une connexion HTTP. Latence irréductible ~50 ms. Impossible d'atteindre < 100 ms par cycle avec REST. |
| L-03 | Pas de cache centralisé OHLCV | Architecture | **Moyenne** | Chaque MarketScanner a son propre cache en mémoire. Duplication des données si N instances. |
| L-04 | advisor_loop.py 6 381 lignes | Maintenabilité | **Critique** | Fichier monolithique. Toute modification est à haut risque. Refactoring actif via strangler (P10-B). |
| L-05 | Feature engineering séquentiel | Débit | **Moyenne** | RSI/MACD/EMA calculés symbole par symbole. Vectorisation NumPy permettrait un gain de 5-10×. |
| L-06 | MistakeMemory sans mutex | Thread Safety | **Faible** | Latente aujourd'hui (un seul thread). Deviendra critique lors de la parallélisation. |
| L-07 | Pas de backpressure | Résilience | **Moyenne** | Si CCXT ralentit (rate limit, réseau), le cycle dépasse 300 s sans signalement structuré. |
| L-08 | SQLite non protégé en écriture concurrent | Thread Safety | **Faible** | Latente. SQLite supporte les écritures séquentielles mais pas les écritures concurrentes sans WAL. |
| L-09 | AIAdvisor dépend de LM Studio externe | Résilience | **Faible** | Si LM Studio est down, fallback deterministic. Latence HTTP non bornée (pas de timeout strict). |
| L-10 | Pas de séparation entre processus data et processus décision | Architecture | **Moyenne** | Un seul processus Python combine I/O réseau, CPU calcul, I/O fichier. GIL Python limite l'efficacité des threads CPU. |
| L-11 | Aucune file de messages entre couches | Couplage | **Moyenne** | Les couches s'appellent directement. Pas de découplage temporel. Un composant lent bloque tout le pipeline. |
| L-12 | Mémoire OHLCV non bornée explicitement | Mémoire | **Faible** | Cache en mémoire sans limite maximale explicite. Pour 200 symboles × 4 TF × 200 candles, charge mémoire ~40-80 MB. Acceptable mais non surveillé. |

### 2.2 Résumé des limites critiques

```
Critique (3) :
  L-01 — Scalabilité : séquentiel → bloque à 50+ symboles
  L-02 — Latence : REST polling → impossible de descendre < 100 ms
  L-04 — Maintenabilité : fichier monolithique → risque élevé de régression

Moyenne (5) :
  L-03 — Cache distribué manquant
  L-05 — Feature engineering non vectorisé
  L-07 — Pas de backpressure
  L-10 — Pas de séparation des processus
  L-11 — Couplage fort entre couches

Faible (4) :
  L-06 — Thread safety MistakeMemory
  L-08 — SQLite concurrence
  L-09 — LM Studio sans timeout strict
  L-12 — Mémoire OHLCV non surveillée
```

---

## 3. Architecture cible

### 3.1 Principes directeurs

1. **Séparation des responsabilités** — un processus, un rôle.
2. **Découplage temporel** — les couches communiquent via une file, pas par appel direct.
3. **Dégradation gracieuse** — chaque composant a un fallback défini.
4. **Observabilité native** — chaque composant expose des métriques sans instrumentation externe.
5. **Migration progressive** — chaque phase est déployable sans interrompre le système.

---

### 3.2 Vue d'ensemble des composants

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        ARCHITECTURE CIBLE                               │
│                                                                         │
│  ┌──────────────────┐     ┌──────────────────┐                         │
│  │  Market Data     │     │  Cache Layer      │                         │
│  │  Layer           │────►│  (OHLCV Store)    │                         │
│  │                  │     │                   │                         │
│  │  WebSocket feed  │     │  TTL par TF       │                         │
│  │  REST fallback   │     │  Validation       │                         │
│  │  Circuit breaker │     │  Invalidation     │                         │
│  └──────────────────┘     └────────┬──────────┘                         │
│                                    │                                     │
│                            ┌───────▼──────────┐                         │
│                            │  Event Bus        │                         │
│                            │  (OHLCV_UPDATED)  │                         │
│                            └───────┬──────────┘                         │
│                                    │                                     │
│              ┌─────────────────────▼──────────────────────┐            │
│              │           Feature & Ranking Engine          │            │
│              │                                             │            │
│              │  Feature Extractor  │  Regime Detector      │            │
│              │  (vectorisé NumPy)  │  (par symbole)        │            │
│              │                     │                       │            │
│              │      Signal Engine  │  Universe Ranker      │            │
│              └─────────────────────┬──────────────────────┘            │
│                                    │                                     │
│                            ┌───────▼──────────┐                         │
│                            │  Event Bus        │                         │
│                            │  (SIGNAL_READY)   │                         │
│                            └───────┬──────────┘                         │
│                                    │                                     │
│              ┌─────────────────────▼──────────────────────┐            │
│              │           Decision Intelligence             │            │
│              │                                             │            │
│              │  MistakeMemory  │  GlobalRiskGate          │            │
│              │  Portfolio Brain │  Order Sizer             │            │
│              └─────────────────────┬──────────────────────┘            │
│                                    │                                     │
│                            ┌───────▼──────────┐                         │
│                            │  Execution Layer  │                         │
│                            │                   │                         │
│                            │  ExecutionEngine  │                         │
│                            │  OrderDedup       │                         │
│                            │  SessionGuard     │                         │
│                            └───────┬──────────┘                         │
│                                    │                                     │
│              ┌─────────────────────▼──────────────────────┐            │
│              │           Observability Layer               │            │
│              │                                             │            │
│              │  MetricsCollector  │  TradeLogger (SQLite)  │            │
│              │  Telegram Reporter │  MistakeMemory JSONL   │            │
│              └────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 3.3 Description des composants

#### Market Data Layer
- **Rôle :** source unique de vérité pour les données OHLCV.
- **Entrées :** WebSocket MEXC (primary) + REST CCXT (fallback).
- **Sorties :** événements `OHLCV_UPDATED(symbol, timeframe, candles)` publiés sur l'Event Bus.
- **Responsabilités :** connexion, reconnexion, validation, normalisation, backpressure.
- **Isolation :** processus séparé ou `asyncio` loop dédiée.

#### Cache Layer (OHLCV Store)
- **Rôle :** cache centralisé et partagé pour toutes les données de marché.
- **Structure :** `dict[symbol][timeframe] = (candles, timestamp, ttl)`.
- **TTL par timeframe :** 1m=30s, 15m=5min, 1h=60s, 4h=10min, 1d=1h.
- **Invalidation :** à la réception d'un événement `OHLCV_UPDATED`.
- **Protection :** `threading.RLock` ou structure immutable (copy-on-write).

#### Event Bus
- **Rôle :** découplage temporel entre les couches.
- **Implémentation cible :** `asyncio.Queue` ou `queue.Queue` (threading).
- **Topics :** `OHLCV_UPDATED`, `SIGNAL_READY`, `ORDER_EXECUTED`, `TRADE_CLOSED`.
- **Backpressure :** `maxsize` configuré par topic.

#### Feature & Ranking Engine
- **Rôle :** calcul vectorisé des indicateurs + scoring de l'univers.
- **Feature Extractor :** RSI/MACD/EMA/ATR/BB calculés en batch NumPy sur l'ensemble des symboles.
- **Regime Detector :** classification bull/bear/sideways/volatile par symbole.
- **Signal Engine :** score composite 0-100 (MTF 40 + Régime 25 + Data 15 + Mémoire 20).
- **Universe Ranker :** tri des symboles par score, filtrage par régime.

#### Decision Intelligence
- **Rôle :** décision finale trade / no-trade.
- **Entrées :** `SignalResult` du ranking engine.
- **Composants :** `MistakeMemory.check()`, `GlobalRiskGate.validate()`, `PortfolioBrain.allocate()`, `OrderSizer.compute()`.
- **Invariant :** ne connaît pas les détails d'exécution (prix, slippage).

#### Execution Layer
- **Rôle :** envoi des ordres et gestion des confirmations.
- **Composants :** `ExecutionEngine`, `OrderDeduplicator`, `SessionGuard`.
- **Isolation :** appels CCXT dans un `ThreadPoolExecutor` (ou `asyncio` avec ccxt.async).
- **Audit :** chaque ordre enregistré en SQLite avec HMAC signature.

#### Observability Layer
- **Rôle :** collecte et exposition des métriques, alertes.
- **Composants :** `MetricsCollector`, `TelegramReporter`, `TradeLogger`, `MistakeMemory.record()`.
- **Principe :** passif — réagit aux événements, ne bloque jamais le pipeline.

---

### 3.4 Schéma complet avec flux de données

```
MEXC WebSocket ──────────────────────────────────────────────────────┐
                                                                      │
REST CCXT (fallback) ─────────────────────────────────────────────┐  │
                                                                   ▼  ▼
                                                         ┌─────────────────┐
                                                         │ Market Data Layer│
                                                         │ (connexion +    │
                                                         │  validation +   │
                                                         │  normalisation) │
                                                         └────────┬────────┘
                                                                  │ OHLCV_UPDATED
                                                         ┌────────▼────────┐
                                                         │  Cache Layer     │
                                                         │  (TTL par TF)   │
                                                         └────────┬────────┘
                                                                  │ lecture
                                        ┌─────────────────────────▼───────────────────────┐
                                        │           Feature & Ranking Engine               │
                                        │                                                   │
                                        │   [vectorisé, batch sur 200 symboles]            │
                                        │                                                   │
                                        │   Feature Extractor ──► Regime Detector          │
                                        │         │                     │                   │
                                        │   Signal Engine ◄────────────┘                   │
                                        │         │                                         │
                                        │   Universe Ranker (Top N par score)               │
                                        └──────────────────┬──────────────────────────────┘
                                                           │ SIGNAL_READY (Top 3-5 symboles)
                                        ┌──────────────────▼──────────────────────────────┐
                                        │           Decision Intelligence                  │
                                        │                                                   │
                                        │   MistakeMemory.check() → BLOCKED / OK           │
                                        │   GlobalRiskGate.validate() → REJECTED / OK      │
                                        │   PortfolioBrain.allocate() → taille position    │
                                        │   OrderSizer.compute() → montant USD             │
                                        └──────────────────┬──────────────────────────────┘
                                                           │ ORDER_DECISION
                                        ┌──────────────────▼──────────────────────────────┐
                                        │           Execution Layer                        │
                                        │                                                   │
                                        │   OrderDeduplicator → déjà envoyé ?              │
                                        │   SessionGuard → limites session ?               │
                                        │   ExecutionEngine → CCXT create_order()         │
                                        └──────────────────┬──────────────────────────────┘
                                                           │ ORDER_EXECUTED / TRADE_CLOSED
                                        ┌──────────────────▼──────────────────────────────┐
                                        │           Observability Layer (passif)           │
                                        │                                                   │
                                        │   TradeLogger → SQLite                           │
                                        │   MistakeMemory.record() → JSONL                │
                                        │   TelegramReporter → alerte                     │
                                        │   MetricsCollector → compteurs cycle             │
                                        └────────────────────────────────────────────────┘
```

---

## 4. Pipeline de données

### 4.1 Flux complet avec interfaces

```
[1] Market Data
    Source : WebSocket MEXC / REST CCXT
    Format : list[dict] OHLCV brut
    Interface : MarketDataProvider.subscribe(symbol, timeframe) → AsyncIterator[OHLCVBatch]
    │
    ▼
[2] Validation
    Règles : timestamp cohérent, prix > 0, volume >= 0, pas de NaN, pas de doublon
    Interface : validate(raw: list[dict]) → ValidationResult(valid, rejected_count, reason)
    Sortie : list[dict] épuré
    │
    ▼
[3] Normalisation
    Règles : colonnes canoniques (open/high/low/close/volume/timestamp), unités homogènes
    Interface : normalize(validated: list[dict]) → pd.DataFrame (colonnes fixes)
    Sortie : DataFrame structuré
    │
    ▼
[4] Cache
    Clé : (symbol, timeframe)
    TTL : 30s (1m), 60s (1h), 600s (4h), 3600s (1d)
    Interface : CacheStore.put(key, df, ttl) / CacheStore.get(key) → Optional[CachedItem]
    Invariant : lecture toujours possible (retourne None si absent, jamais d'exception)
    │
    ▼
[5] Feature Extraction
    Input : dict[symbol] → DataFrame
    Calcul : vectorisé NumPy sur l'ensemble des symboles simultanément
    Features : RSI(14), MACD(12/26/9), EMA(20/50/200), ATR(14), BB(20), volume_ratio
    Interface : FeatureExtractor.compute(candles_dict) → dict[symbol, FeatureVector]
    │
    ▼
[6] Ranking
    Input : dict[symbol, FeatureVector]
    Calcul : score 0-100 par symbole, tri décroissant
    Filtre : exclure score < 60, régimes blacklistés, symboles bloqués par MistakeMemory
    Interface : Ranker.rank(features) → list[RankedSignal] (ordonnée par score desc)
    │
    ▼
[7] Signal (sélection)
    Input : list[RankedSignal]
    Sélection : premier signal BUY/SELL non bloqué
    Interface : SignalSelector.select(ranked) → Optional[SignalResult]
    Sortie : SignalResult ou None (no-trade)
    │
    ▼
[8] Risk
    Input : SignalResult + état portefeuille
    Vérifications : MistakeMemory, GlobalRiskGate, corrélation, exposition max
    Interface : RiskLayer.validate(signal, portfolio) → RiskDecision(approved, reason)
    │
    ▼
[9] Portfolio
    Input : RiskDecision + capital disponible
    Calcul : taille de position (Kelly / fraction fixe), montant USD
    Interface : PortfolioBrain.allocate(decision) → OrderSpec(symbol, side, size_usd)
    │
    ▼
[10] Execution
    Input : OrderSpec
    Action : create_order via CCXT
    Interface : ExecutionEngine.execute(spec) → OrderResult(id, filled, price, timestamp)
    │
    ▼
[11] Logging
    Input : OrderResult + SignalResult
    Actions : SQLite append, Telegram alert si score >= 75
    Interface : ObservabilityBus.emit(event: TradeEvent)
    │
    ▼
[12] Learning
    Input : TradeEvent (TRADE_CLOSED)
    Actions : classification erreur, persist JSONL, génération règle si N erreurs répétées
    Interface : MistakeMemory.record_trade_result(...)
    Sortie : MistakeMemory.rules mis à jour (utilisés au prochain cycle étape 6)
```

---

### 4.2 Interfaces entre composants (résumé)

| Interface | Producteur | Consommateur | Format |
|-----------|-----------|--------------|--------|
| `OHLCVBatch` | MarketDataLayer | CacheStore | `{symbol, timeframe, candles: list[dict], received_at: float}` |
| `CachedItem` | CacheStore | FeatureExtractor | `{df: DataFrame, cached_at: float, ttl: int}` |
| `FeatureVector` | FeatureExtractor | Ranker | `{rsi, macd, ema20, atr, volume_ratio, regime, score_components}` |
| `RankedSignal` | Ranker | SignalSelector | `{symbol, score, signal, regime, strength, confirmed, features}` |
| `SignalResult` | SignalSelector | RiskLayer | `{symbol, score, signal, regime, timestamp, components}` |
| `RiskDecision` | RiskLayer | PortfolioBrain | `{approved: bool, reason: str, constraints: dict}` |
| `OrderSpec` | PortfolioBrain | ExecutionEngine | `{symbol, side, size_usd, max_slippage, time_in_force}` |
| `OrderResult` | ExecutionEngine | ObservabilityBus | `{order_id, filled, avg_price, fees, timestamp}` |
| `TradeEvent` | ObservabilityBus | MistakeMemory / Logger | `{type, symbol, pnl_pct, regime, signal, score, context}` |

---

## 5. Stratégie de concurrence

### 5.1 Comparaison des modèles

#### Modèle A — Séquentiel (architecture actuelle)

```python
for symbol in symbols:
    candles = scanner.scan(symbol)
    signal = engine.evaluate(symbol, candles)
    if signal.actionable:
        execution.execute(signal)
```

| Critère | Évaluation |
|---------|-----------|
| Avantages | Simple, débogage trivial, pas de race condition, comportement déterministe |
| Inconvénients | Temps de cycle = N × coût_symbole. 200 symboles × 100 ms = 20 s |
| Risques | Inutilisable au-delà de 50 symboles avec cycle 300 s |
| Mémoire | Minimale (un contexte à la fois) |
| Complexité | Très faible |
| Maintenabilité | Excellent |
| **Verdict** | Acceptable pour ≤ 30 symboles. **Bloquant au-delà.** |

---

#### Modèle B — `asyncio` (recommandé pour I/O)

```python
async def scan_all(symbols):
    tasks = [scan_one(s) for s in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

| Critère | Évaluation |
|---------|-----------|
| Avantages | Idéal pour I/O réseau (fetch OHLCV). 200 fetches simultanés ≈ coût d'un seul. GIL non problématique pour I/O. CCXT supporte ccxt.async_support |
| Inconvénients | Feature calculation reste bloquante dans une coroutine. Nécessite refactoring de la boucle principale |
| Risques | Erreurs silencieuses si exceptions mal propagées. Debugging plus difficile |
| Mémoire | 200 coroutines actives : ~2-5 MB overhead (négligeable) |
| Complexité | Moyenne |
| Maintenabilité | Bonne si bien structuré |
| **Verdict** | **Recommandé pour la couche Market Data** (I/O dominant). Ne pas utiliser pour le calcul de features. |

---

#### Modèle C — `ThreadPoolExecutor` (pour I/O avec code synchrone)

```python
with ThreadPoolExecutor(max_workers=20) as pool:
    futures = [pool.submit(scan_one, s) for s in symbols]
    results = [f.result() for f in futures]
```

| Critère | Évaluation |
|---------|-----------|
| Avantages | Compatible avec code CCXT synchrone existant. Pas de refactoring majeur. Parallélisme réel pour les appels HTTP (I/O release GIL) |
| Inconvénients | GIL bloque pour CPU-bound. Overhead de threads (mémoire par thread ~1-8 MB). Risques de race condition sur état partagé |
| Risques | Thread safety de MistakeMemory (L-06), SQLite (L-08). Pool mal configuré → épuisement de ressources |
| Mémoire | 20 threads × 2 MB ≈ 40 MB overhead |
| Complexité | Faible à moyenne |
| Maintenabilité | Bonne |
| **Verdict** | **Solution de transition acceptable** pendant la migration asyncio. Déjà utilisé pour MultiTimeframeScanner. |

---

#### Modèle D — `ProcessPoolExecutor` (pour CPU-bound)

```python
with ProcessPoolExecutor(max_workers=cpu_count()) as pool:
    features = pool.map(compute_features, symbol_batches)
```

| Critère | Évaluation |
|---------|-----------|
| Avantages | Contourne le GIL. Vrai parallélisme CPU. Idéal pour feature extraction vectorisée |
| Inconvénients | Sérialisation des données entre processus (pickle overhead). Pas adapté à I/O réseau. Complexité de gestion des erreurs inter-processus |
| Risques | Overhead de sérialisation peut annuler le gain pour des calculs rapides (<10 ms) |
| Mémoire | N processus × taille du processus. Potentiellement 200-500 MB pour 4-8 workers |
| Complexité | Haute |
| Maintenabilité | Difficile |
| **Verdict** | **Réservé au Feature Engine** si le calcul vectorisé NumPy reste insuffisant. Non prioritaire. |

---

#### Modèle E — Architecture hybride (recommandation finale)

```
Processus 1 : Market Data (asyncio)
  └─ asyncio.gather() sur 200 WebSocket / REST
  └─ publie sur Event Bus (asyncio.Queue)

Processus 2 : Feature Engine (threading + NumPy)
  └─ ThreadPoolExecutor pour I/O Cache
  └─ NumPy batch pour calcul features (libère GIL)
  └─ Séquentiel pour Ranking (léger)

Processus 3 : Decision + Execution (threading)
  └─ Séquentiel pour Decision (critique, pas de concurrence)
  └─ ThreadPoolExecutor pour ordres si multi-exchange

Processus partagé : Observability (asyncio ou threading)
  └─ Queue non-bloquante
  └─ Writes asynchrones vers JSONL / SQLite / Telegram
```

| Critère | Évaluation |
|---------|-----------|
| Avantages | Chaque processus utilise le modèle optimal pour son type de travail. I/O → asyncio. CPU → NumPy batch. Décision → séquentiel (déterministe). |
| Inconvénients | Complexité de l'orchestration inter-processus. Nécessite un protocole de communication (IPC ou queue). |
| Risques | Latence additionnelle de l'IPC. Cohérence des données entre processus. |
| Mémoire | 3 processus × ~50-100 MB ≈ 150-300 MB total |
| Complexité | Haute |
| Maintenabilité | Bonne si les interfaces sont stables |
| **Verdict** | **Architecture cible finale**. À atteindre en Phase D/E de migration. |

---

### 5.2 Recommandation

```
Phase B (10 paires)  → Modèle C (ThreadPoolExecutor pour scan)
Phase C (30 paires)  → Modèle C + NumPy batch features
Phase D (50 paires)  → Modèle B (asyncio pour Market Data)
Phase E (100 paires) → Modèle E (hybride complet)
```

---

## 6. Gestion des données

### 6.1 Cache OHLCV

#### Structure actuelle
- Cache en mémoire par instance `MarketScanner` (dict privé `_history[symbol]`)
- TTL unique : 60 secondes
- Pas de limite de taille explicite

#### Structure cible

```python
class OHLCVCache:
    # {(symbol, timeframe): CachedItem}
    _store: dict[tuple, CachedItem]

    TTL = {
        "1m":  30,      # 30 secondes
        "15m": 300,     # 5 minutes
        "1h":  60,      # 60 secondes
        "4h":  600,     # 10 minutes
        "1d":  3600,    # 1 heure
    }

    MAX_SYMBOLS = 250
    MAX_CANDLES_PER_SYMBOL = 500
```

#### Invalidation
- **Passive** : à la lecture, vérifier `(now - cached_at) > ttl`.
- **Active** : événement `OHLCV_UPDATED` invalide immédiatement l'entrée.
- **Fallback** : si la donnée est expirée ET le fetch échoue, retourner la dernière donnée connue avec `is_stale=True`.

---

### 6.2 WebSocket

#### Connexion cible (MEXC)

```
Connexion WebSocket MEXC : wss://wbs.mexc.com/ws
Souscription par symbole+timeframe : {"method": "SUBSCRIPTION", "params": ["spot@public.kline.v3.api@BTC_USDT@Min1"]}
Heartbeat : ping toutes les 20 secondes
Reconnexion : exponentielle (1s, 2s, 4s, 8s, max 60s) + jitter
```

#### Gestion des états de connexion

```
DISCONNECTED → [connexion] → CONNECTING → [succès] → CONNECTED
                                        → [échec]  → RECONNECTING (backoff)
CONNECTED → [ping timeout] → STALE → [reconnexion] → CONNECTING
CONNECTED → [erreur fatale] → DISCONNECTED
```

#### REST fallback

- Si WebSocket STALE depuis > `ws_stale_threshold` (défaut 120 s), basculer silencieusement sur REST.
- Ré-établir WebSocket en arrière-plan.
- Log métriques : `ws_reconnections_total`, `ws_stale_duration_ms`, `rest_fallback_total`.

---

### 6.3 Backpressure

```
Market Data Layer produit des événements OHLCV_UPDATED.
Feature Engine consomme ces événements.

Si Feature Engine est lent :
  → Queue pleine (maxsize=100)
  → Market Data Layer reçoit une exception QueueFull
  → Stratégie : DROP_OLDEST (supprimer le plus ancien événement)
  → Incrémenter compteur : events_dropped_total

Seuil d'alerte : events_dropped_total > 10 par cycle → log WARNING
Seuil critique : events_dropped_total > 50 → log ERROR + Telegram alert
```

---

### 6.4 Circuit Breaker (évolution)

Architecture actuelle : circuit breaker par composant dans `MarketScanner`.

Architecture cible : circuit breaker centralisé et configurable.

```
CircuitBreaker(
    name="mexc_rest",
    failure_threshold=3,       # N erreurs consécutives → OPEN
    reset_timeout=60,          # secondes avant tentative HALF_OPEN
    half_open_max_calls=1      # appels autorisés en HALF_OPEN
)

États : CLOSED (normal) → OPEN (bloqué) → HALF_OPEN (test) → CLOSED
```

Un circuit breaker par composant externe : `mexc_ws`, `mexc_rest`, `lm_studio`, `telegram`.

---

### 6.5 Retry Policy (uniformisation)

Uniformiser la policy de retry à travers tous les composants :

```python
@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 1.0          # secondes
    multiplier: float = 2.0
    max_delay: float = 30.0
    jitter: bool = True
    retryable_exceptions: tuple = (NetworkError, TimeoutError)
```

Actuellement, chaque composant définit ses propres délais. Standardiser réduit les bugs et simplifie la configuration.

---

## 7. Thread Safety

### 7.1 Inventaire des composants nécessitant une synchronisation

| Composant | Risque | Type de synchronisation | Priorité |
|-----------|--------|------------------------|----------|
| `MarketScanner._history` (cache OHLCV) | Lecture/écriture concurrente si multi-thread | `threading.RLock` | Haute (lors de la parallélisation) |
| `MistakeMemory._save()` (JSONL write) | Écriture concurrente → corruption fichier | `threading.Lock` | **Haute (avant tout parallélisme)** |
| `MistakeMemory._rules` (liste en mémoire) | Lecture/écriture concurrente | `threading.RLock` ou copie immutable | Haute |
| `ExecutionEngine` (CCXT par exchange) | Appels concurrents sur même exchange | `threading.Lock` par exchange (actuel) | Stable |
| `OHLCVCache` (architecture cible) | Lecture/écriture concurrente | `threading.RLock` ou `asyncio.Lock` | Haute (nouveau composant) |
| `MetricsCollector` (compteurs) | Incréments concurrents | `threading.Lock` ou `collections.Counter` atomique | Moyenne |
| `SQLite TradeLogger` | Écritures concurrentes | WAL mode + `threading.Lock` | Moyenne |
| `StartupCache` (JSON/pickle) | Écriture pendant lecture | Écriture atomique (fichier temp + rename) | Faible |
| `Event Bus (Queue)` | Producteur/consommateur concurrents | `queue.Queue` (thread-safe natif) | Stable |

---

### 7.2 Justification par type de synchronisation

#### `threading.Lock` — usage exclusif
Pour les composants où une seule opération est autorisée à la fois :
- `MistakeMemory._save()` : une seule écriture JSONL à la fois.
- `ExecutionEngine` par exchange : un seul ordre en cours par exchange.

#### `threading.RLock` — réentrant
Pour les composants dont les méthodes s'appellent mutuellement :
- `OHLCVCache` : `get()` peut appeler `refresh()` qui modifie `_store`.

#### Écriture atomique (write-then-rename)
Pour les fichiers lus par des processus externes ou lors du redémarrage :
- `StartupCache` : écrire dans `file.tmp`, puis `os.replace(file.tmp, file)`.
- Évite les fichiers partiellement écrits lisibles lors d'un crash.

#### SQLite WAL mode
Pour `TradeLogger` lors de la migration vers écritures concurrentes :
```sql
PRAGMA journal_mode=WAL;
```
WAL permet les lectures concurrentes pendant une écriture.

#### Immutable state (copy-on-write)
Pour `MistakeMemory._rules` : les règles sont copiées à chaque lecture, modifiées atomiquement lors d'un ajout.
```python
new_rules = self._rules.copy()
new_rules.append(rule)
self._rules = new_rules  # assignment atomique en Python
```

---

## 8. Observabilité

### 8.1 Métriques à collecter

#### Métriques de latence (en ms)

| Métrique | Source | Alerte seuil |
|---------|--------|-------------|
| `scan_duration_ms` | MarketScanner.scan() | > 500 ms |
| `fetch_http_ms` | CCXT fetch_ohlcv() | > 300 ms |
| `feature_compute_ms` | FeatureExtractor | > 200 ms |
| `ranking_duration_ms` | Ranker | > 100 ms |
| `signal_duration_ms` | LiveSignalEngine | > 100 ms |
| `risk_check_duration_ms` | GlobalRiskGate | > 50 ms |
| `execution_duration_ms` | ExecutionEngine | > 1 000 ms |
| `cycle_total_ms` | advisor_loop | > 4 000 ms |
| `ws_reconnect_duration_ms` | MarketDataLayer | > 5 000 ms |

#### Métriques de débit et d'état

| Métrique | Source | Alerte seuil |
|---------|--------|-------------|
| `symbols_scanned_per_cycle` | advisor_loop | < N configuré |
| `signals_generated_per_cycle` | LiveSignalEngine | 0 pendant > 5 cycles |
| `signals_blocked_by_mistake_memory` | MistakeMemory | |
| `signals_rejected_by_risk_gate` | GlobalRiskGate | |
| `orders_executed_per_session` | ExecutionEngine | |
| `ws_reconnections_total` | MarketDataLayer | > 5/heure |
| `events_dropped_total` | Event Bus | > 0 |
| `cache_hit_rate` | OHLCVCache | < 80% |
| `circuit_breaker_open_count` | CircuitBreaker | > 0 |
| `mistake_memory_rules_count` | MistakeMemory | |

#### Métriques ressources

| Métrique | Source | Alerte seuil |
|---------|--------|-------------|
| `memory_rss_mb` | processus | > 500 MB |
| `cpu_percent` | processus | > 80% sur 5 cycles |
| `thread_count` | threading | > 50 |
| `open_file_handles` | processus | > 100 |

---

### 8.2 Tableau de bord proposé (Telegram summary)

```
═══════ CYCLE REPORT ═══════
Cycle      : #342 | 14:35:02
Duration   : 823 ms (SLO: <4000 ms) ✓

SCAN
  Symbols  : 50/50 scanned
  Cache    : 94% hit rate
  Errors   : 0

SIGNAL
  Generated: 7 signals
  Blocked  : 2 (MistakeMemory)
  Rejected : 1 (RiskGate)
  Selected : 1 → BTCUSDT BUY 72.3

EXECUTION
  Orders   : 1 executed
  Avg fill : 67,234 USDT (+0.1% slip)

RESOURCES
  Memory   : 142 MB
  Threads  : 12
  WS       : CONNECTED (0 reconnects)

POSITIONS
  Open     : 2
  PnL day  : +0.34%
════════════════════════════
```

---

## 9. Plan de migration

### 9.1 Principes de migration

1. **Zéro interruption** — chaque phase déployable sans arrêter le système.
2. **Rollback en un commit** — chaque phase réversible sans migration de données.
3. **Critères GO/NO GO mesurables** — pas de décision subjective.
4. **Tests de régression obligatoires** avant chaque passage de phase.

---

### 9.2 Phase A — Architecture actuelle (référence)

**Description :** système actuel, 10 à 30 symboles, cycle séquentiel.

**État :** en production, burn-in en cours.

**Critères de sortie (GO Phase B) :**
- 100 trades fermés avec PF ≥ 1.0
- Aucun crash sur 7 jours consécutifs
- Temps de cycle moyen < 2 000 ms pour 30 symboles
- MistakeMemory : 0 corruption JSONL

**Rollback :** N/A (phase de référence).

---

### 9.3 Phase B — ThreadPoolExecutor pour le scan (10 paires max)

**Modifications :**
1. Extraire la boucle de scan de `advisor_loop` dans un `ScanCoordinator`.
2. `ScanCoordinator` utilise `ThreadPoolExecutor(max_workers=10)` pour les fetches OHLCV.
3. Ajouter `threading.Lock` sur `MistakeMemory._save()` et `_rules`.
4. Activer WAL mode sur SQLite `trade_log.sqlite`.
5. Ajouter `MetricsCollector` basique (compteurs temps de cycle par phase).

**Risques :**
- Race condition sur cache OHLCV → mitigé par `threading.RLock` sur `_history`.
- Ordre de traitement non-déterministe → mitigé par ranking centralisé post-scan.

**Critères GO Phase C :**
- Temps de scan 10 symboles < 200 ms (vs ~500 ms séquentiel)
- 0 corruption données (JSONL, SQLite)
- Tests de régression 100% verts (suite existante)
- 5 jours sans crash

**Rollback :** supprimer `ScanCoordinator`, rétablir boucle séquentielle dans `advisor_loop`.

---

### 9.4 Phase C — Vectorisation features + OHLCVCache centralisé (30 paires)

**Modifications :**
1. Extraire `FeatureExtractor` en classe indépendante avec API batch : `compute(dict[symbol, DataFrame]) → dict[symbol, FeatureVector]`.
2. Remplacer les boucles `for symbol` de calcul NumPy par des opérations matricielles.
3. Implémenter `OHLCVCache` centralisé (partagé entre `ScanCoordinator` et `MultiTimeframeScanner`).
4. Ajouter TTL par timeframe dans le cache.

**Risques :**
- Résultats numériques légèrement différents (floating-point) → comparer avant/après sur 50 cycles.
- OHLCVCache partagé → RLock obligatoire.

**Critères GO Phase D :**
- Temps de feature extraction 30 symboles < 100 ms
- Pas de divergence de signal vs Phase A (même symbole, même données → même score ± 0.01)
- 10 jours sans crash
- Couverture de tests feature engine ≥ 95%

**Rollback :** réactiver `FeatureExtractor` ancien, supprimer cache centralisé.

---

### 9.5 Phase D — asyncio pour Market Data (50 paires)

**Modifications :**
1. Créer `MarketDataService` basé sur `asyncio` + `ccxt.async_support`.
2. `asyncio.gather()` sur 50 fetches OHLCV simultanés.
3. `MarketDataService` publie sur `asyncio.Queue` → `OHLCVCache`.
4. Intégrer WebSocket MEXC (souscription `spot@public.kline.v3.api`).
5. REST reste disponible comme fallback automatique.
6. Implémenter circuit breaker centralisé (`mexc_ws`, `mexc_rest`).

**Risques :**
- `ccxt.async_support` peut avoir un comportement différent du sync → tests d'intégration dédiés.
- WebSocket MEXC peut couper sur inactivité → heartbeat 20 s.
- Gestion des erreurs async plus complexe → chaque coroutine doit capturer ses exceptions.

**Critères GO Phase E :**
- Temps de scan 50 symboles < 500 ms (vs ~1 500 ms séquentiel)
- WebSocket MEXC stable sur 7 jours (< 5 reconnexions/heure)
- REST fallback testé et validé
- 14 jours sans crash

**Rollback :** désactiver `MarketDataService`, rétablir `MarketScanner` REST sync dans `ScanCoordinator`.

---

### 9.6 Phase E — Architecture hybride complète (100 paires)

**Modifications :**
1. Séparer en 3 processus distincts (`multiprocessing`) ou goroutines asyncio dédiées :
   - Processus 1 : `MarketDataService` (asyncio)
   - Processus 2 : `FeatureEngine` + `Ranker` (threading + NumPy)
   - Processus 3 : `DecisionEngine` + `ExecutionEngine` (séquentiel)
2. Communication via `multiprocessing.Queue` ou socket IPC.
3. `ObservabilityBus` centralisé (Processus 4 ou thread dédié).
4. Dashoard métriques temps réel (Telegram structured report).

**Risques :**
- Latence IPC inter-processus (1-5 ms additionnel) → acceptable pour cycle 300 s.
- Complexité de déploiement (gestion de 3 processus sur VPS) → systemd services séparés.
- Cohérence des données entre processus → protocole de versioning des snapshots.

**Critères de production-grade (Phase E complète) :**
- Temps de cycle complet 100 symboles < 1 000 ms
- Cache hit rate > 90%
- 0 corruption de données sur 30 jours
- 30 jours sans crash non planifié
- WS uptime > 99.5%
- Rollback < 5 minutes en cas d'incident

---

### 9.7 Résumé visuel

```
Phase A (actuel)    Phase B            Phase C            Phase D            Phase E
─────────────────   ────────────────   ────────────────   ────────────────   ────────────────
10-30 symboles      10 symboles max    30 symboles max    50 symboles max    100 symboles
Séquentiel          ThreadPoolExecutor NumPy batch        asyncio + WS       3 processus
REST sync           Lock MM + SQLite   OHLCVCache centralisé Circuit breakers IPC Queue
In-memory cache     MetricsCollector   TTL par TF         REST fallback      ObservabilityBus
~2000 ms cycle      ~800 ms cycle      ~500 ms cycle      ~300 ms cycle      <200 ms cycle
```

---

## 10. Registre des risques

| # | Risque | Probabilité | Impact | Détectabilité | Mitigation |
|---|--------|------------|--------|---------------|------------|
| R-01 | WebSocket MEXC coupe pendant une nuit → positions non surveillées | Haute | Critique | Faible (silent) | Heartbeat 20 s + REST fallback automatique + alerte Telegram si STALE > 120 s |
| R-02 | Race condition sur `MistakeMemory` lors du passage multi-thread | Moyenne | Haute | Faible | `threading.Lock` avant Phase B |
| R-03 | Surcharge mémoire avec 200 symboles × 4 TF × 500 candles | Faible | Moyenne | Moyenne | OHLCVCache avec limite MAX_SYMBOLS, monitoring RSS |
| R-04 | Résultats numériques divergents après vectorisation NumPy | Faible | Haute | Haute | Comparaison before/after sur 50 cycles avant Phase C |
| R-05 | IPC inter-processus ajoute de la latence > SLO | Faible | Haute | Haute | Benchmark IPC avant Phase E |
| R-06 | MEXC modifie son API WebSocket → déconnexion permanente | Faible | Critique | Haute | Circuit breaker + REST fallback permanent |
| R-07 | `ccxt.async_support` diverge du comportement sync | Faible | Haute | Moyenne | Tests d'intégration dédiés async vs sync sur mêmes données |
| R-08 | Épuisement des handles de fichiers (SQLite + JSONL + logs) | Faible | Haute | Faible | Monitoring `open_file_handles`, rotation JSONL |
| R-09 | Corruption SQLite pendant migration WAL | Très faible | Critique | Faible | Backup avant activation WAL, test sur copie |
| R-10 | Régression signal après refactoring FeatureExtractor | Moyenne | Haute | Haute | Tests de non-régression signal (même data → même score) |
| R-11 | GIL Python annule le gain ThreadPoolExecutor sur CPU-bound | Haute | Moyenne | Haute | Profiler avant déploiement, basculer sur NumPy batch |
| R-12 | advisor_loop.py 6 381 lignes → régression lors du refactoring | Haute | Haute | Haute | Strangler pattern P10-B déjà en cours, ne pas toucher au-delà du strangler |

---

## 11. Décisions d'architecture

### DA-01 — REST polling vs WebSocket pour la collecte OHLCV

**Contexte :** Le cycle actuel est de 5 minutes. Les données nécessaires sont des chandeliers OHLCV agrégés (pas de tick data).

**Problème :** REST polling introduit une latence de 50-300 ms par appel et consomme des quotas API. WebSocket fournirait des mises à jour en temps réel mais introduit une complexité de gestion de connexion.

**Options étudiées :**
1. REST exclusif (état actuel)
2. WebSocket exclusif
3. WebSocket primary + REST fallback

**Décision retenue :** Option 3 — WebSocket primary + REST fallback, à partir de la Phase D.

**Justification :** Pour un cycle de 5 minutes, REST est suffisant jusqu'à 30 symboles. Au-delà, WebSocket est nécessaire pour maintenir le temps de cycle < 500 ms. Le fallback REST garantit la résilience sans dépendance unique.

**Conséquences :** Complexité accrue (gestion de deux sources), mais résilience améliorée. Le fallback REST existant dans `MarketScanner` constitue une base solide pour cette architecture.

---

### DA-02 — asyncio vs ThreadPoolExecutor pour la concurrence I/O

**Contexte :** Python 3.x avec GIL. Les appels CCXT existants sont synchrones.

**Problème :** Pour scanner 100-200 symboles en < 500 ms, les appels réseau doivent être parallélisés.

**Options étudiées :**
1. ThreadPoolExecutor (compatible code sync existant)
2. asyncio + ccxt.async_support (refactoring nécessaire)
3. ProcessPoolExecutor (contourne GIL mais overhead IPC)

**Décision retenue :** ThreadPoolExecutor en Phase B/C, migration asyncio en Phase D uniquement pour `MarketDataService`.

**Justification :** Le GIL n'est pas un problème pour l'I/O réseau (GIL est relâché pendant les syscalls). ThreadPoolExecutor préserve le code synchrone existant. asyncio est plus efficace mais nécessite un refactoring complet. La migration progressive réduit le risque de régression.

**Conséquences :** Deux modèles de concurrence coexistants en Phase D. Nécessite une interface claire entre le `MarketDataService` asyncio et le reste du pipeline synchrone.

---

### DA-03 — Cache centralisé vs cache distribué par instance

**Contexte :** Chaque `MarketScanner` a son propre cache en mémoire. À mesure que le nombre de symboles et de timeframes augmente, des instances multiples peuvent dupliquer les mêmes données.

**Problème :** Avec 200 symboles × 4 TF, la duplication de cache entre instances représente un gaspillage de mémoire et peut créer des incohérences si des données différentes sont utilisées par deux composants.

**Décision retenue :** `OHLCVCache` centralisé, partagé par tous les composants, en Phase C.

**Justification :** Source unique de vérité, cohérence garantie, réduction de la mémoire. Le `RLock` protège les accès concurrents.

**Conséquences :** `MarketScanner` devient un lecteur du cache, non plus propriétaire. Nécessite une interface `CacheStore` claire.

---

### DA-04 — Séquentialité de la couche de décision

**Contexte :** La décision de trading (MistakeMemory + RiskGate + PortfolioBrain) pourrait théoriquement être parallélisée sur plusieurs symboles.

**Problème :** La décision implique un état partagé (capital disponible, positions ouvertes, règles MistakeMemory). La paralléliser sans coordination pourrait mener à des décisions incohérentes (ex : allouer deux fois le même capital).

**Décision retenue :** La couche de décision reste **strictement séquentielle**, même en Phase E.

**Justification :** La cohérence du capital et des positions est non-négociable. Les gains de performance potentiels (< 50 ms) ne justifient pas le risque d'incohérence. La décision ne traite que le top-N (3-5) symboles après ranking, donc la latence séquentielle est négligeable.

**Conséquences :** Aucune. La séquentialité est une propriété de sécurité, pas une contrainte de performance.

---

### DA-05 — Monolithique vs strangler pattern pour la migration de advisor_loop.py

**Contexte :** `advisor_loop.py` fait 6 381 lignes et concentre toute la logique d'orchestration.

**Problème :** Réécrire intégralement présente un risque de régression trop élevé. Modifier le fichier directement est risqué par sa taille.

**Décision retenue :** Continuer le pattern strangler (P10-B `runtime/advisor_main.py`) — extraire progressivement les composants sans modifier le core de `advisor_loop.py`.

**Justification :** Le strangler pattern permet de valider chaque extraction indépendamment. `advisor_main.py` est déjà en place comme point d'entrée alternatif. La migration est réversible à tout moment.

**Conséquences :** Coexistence temporaire de deux chemins de code. Risque de divergence entre les deux si `advisor_loop.py` évolue. Nécessite une discipline stricte : toute nouvelle fonctionnalité va dans `advisor_main.py`, pas dans `advisor_loop.py`.

---

## 12. Recommandation finale

### 12.1 Architecture recommandée

L'architecture cible est un **pipeline hybride en 3 zones** :

```
Zone A : Données (asyncio + WebSocket)
Zone B : Intelligence (threading + NumPy batch)
Zone C : Décision + Exécution (séquentiel, synchrone)
```

Cette séparation correspond naturellement aux types de travail :
- Zone A : I/O bound → asyncio est optimal.
- Zone B : CPU bound → NumPy batch libère le GIL, ThreadPoolExecutor gère la coordination.
- Zone C : logique critique → le séquentiel garantit la cohérence.

---

### 12.2 Éléments à conserver

| Élément | Raison |
|---------|--------|
| `MarketScanner` (avec ses retries/circuit breaker) | Fault tolerance éprouvée. À intégrer dans Zone A. |
| `LiveSignalEngine` (scoring 0-100) | Stable, interprétable, extensible. |
| `MistakeMemory` (JSONL + règles auto-générées) | Valeur prouvée en burn-in. Thread safety à ajouter. |
| `GlobalRiskGate` | Gardes invariants du portefeuille. Séquentiel par design. |
| `OrderDeduplicator` + `SessionGuard` | Sécurité d'exécution non-négociable. |
| Circuit breaker pattern | À généraliser et centraliser. |
| Strangler pattern (P10-B) | Continuer la migration via `advisor_main.py`. |

---

### 12.3 Éléments à supprimer / remplacer

| Élément | Action | Raison |
|---------|--------|--------|
| Boucle `for symbol` dans `advisor_loop` | Remplacer par `ScanCoordinator` | Scalabilité bloquée |
| Cache privé par instance `MarketScanner._history` | Remplacer par `OHLCVCache` centralisé (Phase C) | Duplication mémoire, incohérence potentielle |
| Feature calc boucle `for symbol` | Vectoriser NumPy batch (Phase C) | Performance 5-10× |
| Appels REST bloquants pour 50+ symboles | asyncio + WebSocket (Phase D) | Latence irréductible du REST polling |

---

### 12.4 Priorités post burn-in

```
Priorité 1 (immédiatement après 100 trades) :
  □ Ajouter threading.Lock sur MistakeMemory._save() et _rules
  □ Activer WAL mode SQLite
  □ Écriture atomique StartupCache (write-then-rename)
  □ Ajouter MetricsCollector basique (temps de cycle par phase)

Priorité 2 (Phase B, semaines 1-2) :
  □ Extraire ScanCoordinator avec ThreadPoolExecutor
  □ Tests de régression signal (non-divergence)
  □ Monitoring RSS mémoire

Priorité 3 (Phase C, semaines 3-6) :
  □ FeatureExtractor vectorisé NumPy
  □ OHLCVCache centralisé avec TTL par TF
  □ Tableau de bord métriques Telegram

Priorité 4 (Phase D, semaines 7-12) :
  □ MarketDataService asyncio + ccxt.async_support
  □ WebSocket MEXC + REST fallback
  □ Circuit breaker centralisé

Priorité 5 (Phase E, mois 4-6) :
  □ Architecture 3 processus
  □ IPC Queue
  □ ObservabilityBus
```

---

### 12.5 Dette technique documentée

| # | Dette | Impact si non traitée | Phase de traitement |
|---|-------|----------------------|---------------------|
| DT-01 | `MistakeMemory` sans mutex | Corruption JSONL si parallélisation | Avant Phase B |
| DT-02 | SQLite sans WAL | Écriture concurrente bloquante | Avant Phase B |
| DT-03 | `advisor_loop.py` 6 381 lignes | Toute modification à haut risque | Ongoing (strangler P10-B) |
| DT-04 | Pas de limite explicite mémoire cache | Fuite mémoire potentielle à 200 symboles | Phase C |
| DT-05 | AIAdvisor sans timeout HTTP strict | Cycle bloqué si LM Studio lent | Phase B |
| DT-06 | Pas de versioning des interfaces entre couches | Rupture silencieuse si un composant change | Phase C |

---

### 12.6 Critères de production-grade pour le scanner

Le scanner sera considéré **production-grade** lorsque les critères suivants seront tous validés simultanément :

```
Performance :
  ✓ 100 symboles scannés en < 500 ms
  ✓ Temps de cycle total < 1 000 ms
  ✓ Cache hit rate > 90%

Résilience :
  ✓ Reconnexion WebSocket automatique < 5 s
  ✓ REST fallback validé sur 7 jours consécutifs
  ✓ Aucun crash non planifié sur 30 jours

Cohérence des données :
  ✓ 0 corruption JSONL sur 30 jours
  ✓ 0 corruption SQLite sur 30 jours
  ✓ Aucune divergence de signal (même data → même score)

Observabilité :
  ✓ Métriques de latence par phase disponibles
  ✓ Alerte automatique si cycle > SLO
  ✓ Dashboard Telegram opérationnel

Opérations :
  ✓ Rollback possible < 5 minutes
  ✓ Démarrage à froid < 5 secondes
  ✓ Drain propre sur SIGTERM (positions non laissées ouvertes sans monitoring)
```

---

*Document généré le 2026-06-16. Révision prévue après clôture du burn-in (100 trades).*  
*Statut suivant : PROPOSED → à valider après Phase A.*
