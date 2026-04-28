# Documentation — crypto_ai_terminal

> Générée le 2026-04-27 — Python 3.11.8 — branche `chore/safe-archive-legacy-folders`

---

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Lancer les tests](#2-lancer-les-tests)
3. [Inventaire des tests](#3-inventaire-des-tests)
4. [Couverture de code](#4-couverture-de-code)
5. [Référence des modules](#5-référence-des-modules)
   - 5.1 [Pipeline données marché](#51-pipeline-données-marché)
   - 5.2 [Backtesting & validation](#52-backtesting--validation)
   - 5.3 [Sécurité live trading](#53-sécurité-live-trading)
   - 5.4 [Monitoring opérationnel](#54-monitoring-opérationnel)
   - 5.5 [Strategy Lab](#55-strategy-lab)
   - 5.6 [Supervision & alertes](#56-supervision--alertes)
   - 5.7 [Portefeuille & risque](#57-portefeuille--risque)
   - 5.8 [Évolution IA](#58-évolution-ia)
   - 5.9 [Moteur principal](#59-moteur-principal)
6. [Variables d'environnement](#6-variables-denvironnement)
7. [CI/CD — GitHub Actions](#7-cicd--github-actions)
8. [Scripts disponibles](#8-scripts-disponibles)

---

## 1. Vue d'ensemble

```
crypto_ai_terminal/
├── quant_hedge_ai/          # Cœur du système de trading
│   ├── agents/
│   │   ├── market/          # Scan marché, fetch historique, validation OHLCV
│   │   ├── execution/       # Moteur d'exécution, déduplication, log des trades
│   │   ├── risk/            # Guard de session, drawdown, exposition
│   │   ├── quant/           # Backtest, walk-forward, Monte Carlo
│   │   ├── portfolio/       # Kelly, volatility targeting, cerveau portefeuille
│   │   └── monitoring/      # Performance, système, bot doctor
│   ├── strategy_lab/        # Génération, évolution, backtesting des stratégies
│   ├── ai_evolution/        # Moteur d'évolution génétique + mémoire
│   ├── databases/           # Scoreboard des stratégies
│   └── main_v91.py          # Point d'entrée principal (boucle autonome)
├── supervision/             # Alertes, monitoring, bot doctor
│   └── notifications/       # Telegram, Slack, Email, MultiNotifier
├── scripts/                 # Outils CLI (smoke test, validation historique)
├── .github/workflows/       # CI/CD GitHub Actions
├── stream_bus.py            # WebSocket CCXT en fond de tâche
└── global_risk_gate.py      # Circuit breaker systémique
```

**Stack :** Python 3.11 · ccxt · pytest · SQLite · Telegram Bot API

---

## 2. Lancer les tests

### Suite principale (44 tests, ~5 s)
```bash
pytest supervision/test_supervision.py \
       quant_hedge_ai/strategy_lab/test_strategy_lab.py \
       quant_hedge_ai/strategy_lab/test_strategy_lab_errors.py \
       quant_hedge_ai/strategy_lab/test_strategy_lab_integration.py \
       quant_hedge_ai/strategy_lab/test_batch_runner.py \
       quant_hedge_ai/strategy_lab/test_parallel_engine.py \
       quant_hedge_ai/strategy_lab/test_strategy_db_sqlite.py \
       quant_hedge_ai/strategy_lab/test_performance.py \
       -v
```

### Smoke test cross-plateforme (22 checks, ~3 s, zéro réseau)
```bash
python scripts/smoke_test_ci.py
```

### Validation walk-forward (données synthétiques, ~1 s)
```bash
python scripts/validate_historical.py --synthetic --years 1
```

### Validation walk-forward (données réelles Binance)
```bash
# Nécessite BINANCE_API_KEY + BINANCE_API_SECRET dans .env
python scripts/validate_historical.py --symbols BTC/USDT ETH/USDT --years 2
```

### Tous les tests du projet
```bash
pytest -q
# 612 tests collectés — certains nécessitent des dépendances optionnelles
```

### Avec rapport de couverture
```bash
pytest supervision/test_supervision.py quant_hedge_ai/strategy_lab/test_strategy_lab.py \
  --cov=supervision --cov=quant_hedge_ai/agents --cov-report=term-missing
```

---

## 3. Inventaire des tests

### Résultat global : **44 / 44 PASS** ✅

| Fichier | Classe | Tests | Statut | Modules couverts |
|---------|--------|------:|--------|-----------------|
| `supervision/test_supervision.py` | `TestAlert` | 4 | ✅ PASS | `alert_manager.Alert` |
| | `TestAlertManager` | 8 | ✅ PASS | `alert_manager.AlertManager` |
| | `TestMultiNotifier` | 4 | ✅ PASS | `notifications.multi_notifier` |
| | `TestTelegramNotifier` | 3 | ✅ PASS | `notifications.telegram_notifier` |
| `strategy_lab/test_strategy_lab.py` | `TestStrategyLab` | 9 | ✅ PASS | BacktestLauncher, Generator, ParameterSpace, Ranker, SignalBuilder, StrategyDB, Template |
| `strategy_lab/test_strategy_lab_errors.py` | `TestStrategyLabErrors` | 8 | ✅ PASS | Cas limites et erreurs de tous les modules strategy_lab |
| `strategy_lab/test_strategy_lab_integration.py` | `TestStrategyLabIntegration` | 3 | ✅ PASS | Pipeline complet, persistance DB, performance |
| `strategy_lab/test_batch_runner.py` | `TestBatchRunner` | 1 | ✅ PASS | `BatchRunner` |
| `strategy_lab/test_parallel_engine.py` | `TestParallelEngine` | 2 | ✅ PASS | `ParallelEngine` (joblib + multiprocessing) |
| `strategy_lab/test_strategy_db_sqlite.py` | `TestStrategyDatabaseSqlite` | 1 | ✅ PASS | `StrategyDatabase` SQLite |
| `strategy_lab/test_performance.py` | `TestStrategyLabPerformance` | 1 | ✅ PASS | Vitesse pipeline |

### Smoke test — `scripts/smoke_test_ci.py` : **22 / 22 OK** ✅

| Section | Checks | Ce qui est vérifié |
|---------|-------:|--------------------|
| Imports modules | 12 | Tous les modules chantiers 1-4 importables |
| Pipeline données | 2 | `validate_candles` filtre les NaN · `CircuitBreaker` s'ouvre après N échecs |
| Backtest & Walk-Forward | 2 | `BacktestLab.run_backtest` · `WalkForwardValidator.validate` |
| Couche sécurité | 4 | `OrderDeduplicator` · `SessionGuard` halt · `TradeLogger` SQLite · `ExecutionEngine` pipeline complet |
| Monitoring | 2 | `OpsNotifier` silencieux sans token · `OpsWatchdog` staleness detection |

### Détail des tests `TestStrategyLab`

| Test | Ce qu'il vérifie |
|------|-----------------|
| `test_strategy_generator` | `StrategyGenerator.generate_population(n)` retourne n stratégies avec tous les champs requis |
| `test_parameter_space` | `ParameterSpace.sample()` retourne des valeurs dans les bornes définies |
| `test_signal_builder` | `SignalBuilder.build()` produit une liste de signaux de la même longueur que les prix |
| `test_backtest_launcher` | `BacktestLauncher.run()` retourne un dict avec `sharpe`, `pnl`, `drawdown` |
| `test_ranker` | `StrategyRanker.rank()` trie les stratégies par Sharpe décroissant |
| `test_strategy_db` | `StrategyDatabase.save()` + `top()` : persistance et récupération correctes |
| `test_strategy_template` | `StrategyTemplate.to_dict()` + `from_dict()` : sérialisation aller-retour |
| `test_complex_strategy` | Pipeline EMA crossover complet sur série synthétique |
| `test_backward_compatibility` | Stratégies sans tous les champs optionnels sont acceptées |

### Détail des tests `TestStrategyLabErrors`

| Test | Cas limite couvert |
|------|-------------------|
| `test_generator_empty` | `generate_population(0)` retourne liste vide |
| `test_parameter_space_unknown` | Paramètre inconnu retourne valeur par défaut |
| `test_signal_builder_bad_logic` | Signal builder avec règle invalide ne plante pas |
| `test_signal_builder_unexpected_input` | Prix négatif ou vide géré gracieusement |
| `test_backtest_launcher_empty` | Série vide retourne `pnl=0`, `sharpe=0` |
| `test_ranker_missing_metric` | Stratégie sans Sharpe est classée en dernier |
| `test_strategy_db_empty` | `top()` sur DB vide retourne `[]` |
| `test_template_missing_param` | `from_dict()` avec clé manquante ne lève pas d'exception |

---

## 4. Couverture de code

### Modules avec couverture mesurée (suite principale)

| Module | Lignes | Couverture | État |
|--------|-------:|--------:|------|
| `supervision/alert_manager.py` | 40 | **100%** | ✅ |
| `supervision/notifications/multi_notifier.py` | 13 | **100%** | ✅ |
| `supervision/notifications/telegram_notifier.py` | 20 | **100%** | ✅ |

### Modules sans tests dédiés (couverture partielle via smoke test)

| Module | Couverture estimée | Manque |
|--------|:-----------------:|--------|
| `agents/market/ohlcv_validator.py` | ~60% | Tests spike detection, `is_series_fresh` |
| `agents/market/retry_policy.py` | ~50% | Tests HALF_OPEN, jitter |
| `agents/execution/order_deduplicator.py` | ~70% | Tests `_evict_stale` avec mock time |
| `agents/execution/trade_logger.py` | ~50% | Tests `session_pnl`, `stats` |
| `agents/risk/session_guard.py` | ~60% | Tests `reset`, `loss_pct halt` |
| `agents/quant/backtest_lab.py` | ~40% | Tests indicateurs MACD, BOLLINGER, VWAP, ATR |
| `agents/quant/walk_forward.py` | ~55% | Tests `validate_batch`, `summary` |
| `supervision/ops_notifier.py` | ~45% | Tests rate-limiting avec mock |
| `supervision/ops_watchdog.py` | ~40% | Tests `cycle_guard`, heartbeat |

### Objectif couverture CI : **60%** (seuil `--cov-fail-under=60` dans ci.yml)

---

## 5. Référence des modules

---

### 5.1 Pipeline données marché

#### `quant_hedge_ai/agents/market/ohlcv_validator.py`

Valide les bougies OHLCV avant tout traitement. Filtre les données corrompues.

```python
from quant_hedge_ai.agents.market.ohlcv_validator import validate_candles, is_series_fresh

clean, report = validate_candles(candles, symbol="BTC/USDT")
# report.total     — nb bougies entrantes
# report.valid     — nb bougies acceptées
# report.dropped   — nb bougies rejetées
# report.reasons   — {"nan_inf_close": 2, "spike_ratio": 1, ...}
# report.real_ratio — ratio ccxt_live vs synthetic

fresh = is_series_fresh(candles, max_age_seconds=3600.0)
```

**Règles de validation :**
| Règle | Code d'erreur |
|-------|--------------|
| Champ manquant (open/high/low/close/volume) | `missing_field` |
| Valeur non numérique | `non_numeric` |
| NaN ou infini | `nan_inf_{field}` |
| Prix ≤ 0 | `non_positive_{field}` |
| High < max(open, close) | `high_low_inconsistency` |
| Spike > 10× ratio high/low | `spike_ratio` |

---

#### `quant_hedge_ai/agents/market/retry_policy.py`

Retry exponentiel et circuit breaker pour les appels réseau.

```python
from quant_hedge_ai.agents.market.retry_policy import retry_with_backoff, CircuitBreaker

# Retry avec backoff exponentiel
result = retry_with_backoff(
    fn=lambda: exchange.fetch_ohlcv(...),
    max_retries=3,
    base_delay=1.0,     # secondes
    max_delay=30.0,
    jitter=True,        # ±40% aléatoire
    label="fetch BTC",  # pour les logs
)

# Circuit breaker
cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0, label="Binance")
result = cb.call(lambda: some_network_call())
# cb.state      → "CLOSED" | "OPEN" | "HALF_OPEN"
# cb.is_open    → True si bloqué
# cb.is_closed  → True si opérationnel
# cb.reset()    → force retour à CLOSED
```

**États du circuit breaker :**
```
CLOSED ──[3 échecs]──> OPEN ──[60s]──> HALF_OPEN ──[succès]──> CLOSED
                                           └──[échec]──> OPEN
```

---

#### `quant_hedge_ai/agents/market/market_scanner.py`

Scan temps réel via CCXT avec cache TTL, circuit breaker et fallback synthétique.

```python
from quant_hedge_ai.agents.market.market_scanner import MarketScanner

scanner = MarketScanner(
    symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
    timeframe="1h",
    limit=200,
)

market = scanner.scan()
# market["candles"]  → [dernière bougie par symbole]
# market["history"]  → {symbol: [200 bougies]}

quality = scanner.data_quality()
# quality["real_ratio"]    → ratio données réelles (0.0-1.0)
# quality["circuit_state"] → état du circuit breaker
# quality["real"]          → nb fetches réels
# quality["synthetic"]     → nb fallbacks synthétiques
# quality["cached"]        → nb hits cache
```

**Variables d'environnement :**
```
MARKET_SCANNER_EXCHANGE=binance      # exchange CCXT
MARKET_SCANNER_TIMEFRAME=1h          # timeframe
MARKET_SCANNER_LIMIT=200             # bougies par fetch
MARKET_SCANNER_SYNTHETIC=false       # forcer synthétique
MARKET_SCANNER_CACHE_TTL=60          # TTL cache (secondes)
MARKET_SCANNER_CB_RECOVERY=60        # timeout recovery circuit breaker
```

---

#### `quant_hedge_ai/agents/market/historical_fetcher.py`

Téléchargement paginé de plusieurs années de données historiques.

```python
from quant_hedge_ai.agents.market.historical_fetcher import HistoricalDataFetcher

fetcher = HistoricalDataFetcher(exchange_id="binance")

# Télécharger 2 ans de BTC/USDT en 1h
candles = fetcher.fetch("BTC/USDT", timeframe="1h", years=2.0, progress=True)
# → ~17 500 bougies dict {symbol, timestamp, open, high, low, close, volume, source}

# Fetch + sauvegarde SQLite pour plusieurs symboles
saved = fetcher.fetch_and_save(
    symbols=["BTC/USDT", "ETH/USDT"],
    timeframe="1h",
    years=2.0,
    db_path="databases/market_data.sqlite",
)
# → {"BTC/USDT": 17520, "ETH/USDT": 17498}
```

---

### 5.2 Backtesting & validation

#### `quant_hedge_ai/agents/quant/backtest_lab.py`

Backtest sur vraies séries OHLCV avec 6 indicateurs techniques.

```python
from quant_hedge_ai.agents.quant.backtest_lab import BacktestLab

lab = BacktestLab()
result = lab.run_backtest(
    strategy={"entry_indicator": "EMA", "period": 14, "threshold": 1.0},
    data=candles,       # liste de dicts OHLCV, minimum 50 bougies
    timeframe="1h",     # pour l'annualisation du Sharpe
)
# result["pnl"]       → PnL en % (ex: 12.45)
# result["sharpe"]    → ratio de Sharpe annualisé
# result["drawdown"]  → drawdown max (0.0-1.0)
# result["win_rate"]  → taux de trades gagnants
# result["trades"]    → nombre de trades exécutés
# result["bars"]      → nombre de bougies traitées
```

**Indicateurs disponibles (`entry_indicator`) :**
| Valeur | Description |
|--------|-------------|
| `EMA` | Prix > EMA × (1 + band) → long |
| `RSI` | RSI < buy_level → long, RSI > sell_level → short |
| `MACD` | Croisement MACD/Signal |
| `BOLLINGER` | Prix < bande basse → long, > bande haute → short |
| `VWAP` | Prix > VWAP × (1 + band) → long |
| `ATR` | Prix > SMA + threshold × ATR → long |

**Annualisation Sharpe par timeframe :**
| Timeframe | Périodes/an |
|-----------|------------:|
| `1m` | 525 600 |
| `5m` | 105 120 |
| `15m` | 35 040 |
| `1h` | 8 760 |
| `4h` | 2 190 |
| `1d` | 365 |

---

#### `quant_hedge_ai/agents/quant/walk_forward.py`

Validation anti-overfitting par séparation in-sample / out-of-sample.

```python
from quant_hedge_ai.agents.quant.walk_forward import WalkForwardValidator

validator = WalkForwardValidator(
    train_ratio=0.7,        # 70% in-sample
    decay_threshold=0.5,    # Sharpe OOS doit être ≥ 50% du IS
    min_trades_oos=5,       # minimum de trades OOS pour être valide
)

result = validator.validate(strategy, candles)
# result.sharpe_in   / result.sharpe_out   → Sharpe IS vs OOS
# result.pnl_in      / result.pnl_out      → PnL IS vs OOS (%)
# result.drawdown_in / result.drawdown_out → Drawdown IS vs OOS
# result.trades_in   / result.trades_out   → Trades IS vs OOS
# result.is_overfit  → True si score ≥ 0.5
# result.overfit_score → 0.0 (OK) à 1.0 (overfit total)
# result.verdict     → "ROBUSTE" | "ACCEPTABLE" | "SUSPECT" | "OVERFIT"

# Lot de stratégies
results = validator.validate_batch(strategies, candles)
summary = WalkForwardValidator.summary(results)
# summary["overfit_rate"]     → taux de stratégies overfit
# summary["avg_sharpe_in"]    → Sharpe moyen IS
# summary["avg_sharpe_out"]   → Sharpe moyen OOS
# summary["sharpe_decay"]     → ratio dégradation
# summary["best_strategy"]    → meilleure stratégie OOS
```

**Scoring overfitting :**
| Critère | Poids | Condition |
|---------|------:|-----------|
| Dégradation Sharpe | +0.4 | Sharpe OOS/IS < 50% |
| Retournement PnL | +0.3 | PnL IS > 1% et OOS < 0 |
| Trop peu de trades OOS | +0.2 | Trades OOS < 5 |
| Explosion drawdown OOS | +0.1 | Drawdown OOS > 2× IS |

---

### 5.3 Sécurité live trading

#### `quant_hedge_ai/agents/execution/order_deduplicator.py`

Bloque les ordres dupliqués envoyés dans une fenêtre de temps.

```python
from quant_hedge_ai.agents.execution.order_deduplicator import OrderDeduplicator

dedup = OrderDeduplicator(window_seconds=30.0)

if not dedup.is_duplicate("BTC/USDT", "BUY", 0.1):
    # placer l'ordre
    dedup.register("BTC/USDT", "BUY", 0.1)

dedup.reset()  # vider le cache (ex: au redémarrage)
```

La taille est buckétisée à 1 décimale — 0.103 et 0.108 sont considérés identiques.

---

#### `quant_hedge_ai/agents/risk/session_guard.py`

Protection de session — halt automatique si les limites sont franchies.

```python
from quant_hedge_ai.agents.risk.session_guard import (
    SessionGuard, SessionHaltedError, OrderTooLargeError
)

guard = SessionGuard(
    max_session_drawdown=0.05,    # halt si drawdown ≥ 5%
    max_session_loss=0.03,        # halt si perte ≥ 3%
    max_consecutive_losses=3,     # halt après 3 pertes consécutives
    max_order_size_usd=10_000.0,  # rejeter les ordres > 10 000 USD
)
guard.start_session(equity=10_000.0)

# Avant chaque ordre
try:
    guard.check_order("BTC/USDT", "BUY", size_usd=500.0)
except SessionHaltedError as e:
    print(f"Trading arrêté : {e.reason}")
except OrderTooLargeError as e:
    print(f"Ordre trop grand : {e.size_usd} USD")

# Après chaque trade
guard.record_trade(pnl=-50.0, equity=9_950.0)

# État courant
state = guard.state()
# state["drawdown_pct"]        → drawdown actuel en %
# state["loss_pct"]            → perte de session en %
# state["consecutive_losses"]  → streak de pertes
# state["halted"]              → True si arrêté
# state["halt_reason"]         → raison du halt

guard.reset()  # déblocage manuel (opérateur)
```

**Variables d'environnement :**
```
EXEC_MAX_DD=0.05             # drawdown max de session
EXEC_MAX_LOSS=0.03           # perte max de session
EXEC_MAX_CONSEC_LOSSES=3     # pertes consécutives max
EXEC_MAX_ORDER_USD=10000     # taille max d'un ordre en USD
```

---

#### `quant_hedge_ai/agents/execution/trade_logger.py`

Log SQLite de tous les ordres pour audit.

```python
from quant_hedge_ai.agents.execution.trade_logger import TradeLogger

logger = TradeLogger(db_path="databases/trade_log.sqlite")

# Logger un ordre exécuté
logger.log(order_result, status="ok")

# Logger un ordre rejeté
logger.log_rejected("BTC/USDT", "BUY", 0.1, reason="duplicate within 30s")

# Requêtes
trades = logger.recent_trades(n=50)     # N derniers trades
pnl = logger.session_pnl(since_ts=t0)  # PnL depuis timestamp
stats = logger.stats()
# stats["total_trades"]  → total historique
# stats["pnl_sum"]       → PnL cumulé
# stats["win_rate"]      → taux de trades profitables
# stats["rejected"]      → ordres rejetés (sécurité)
```

---

#### `quant_hedge_ai/agents/execution/execution_engine.py`

Point d'entrée unique pour tous les ordres — paper ou live.

```python
from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

# Auto-détection : live si BINANCE_API_KEY présent, paper sinon
eng = ExecutionEngine.from_env()
eng.start_session(equity=100_000.0)

order = eng.create_order("BTC/USDT", "BUY", 0.1)
# order["mode"] → "paper" | "live" | "live_failed" | "rejected"
# order["error"] → raison si rejeté/échoué

status = eng.safety_status()
# status["session"]    → état SessionGuard
# status["trade_log"]  → stats TradeLogger
# status["live_mode"]  → True si live
```

**Pipeline interne de `create_order()` :**
```
1. Validation taille (0 < size < 1e9)
2. SessionGuard.check_order()  → halt / trop grand ?
3. OrderDeduplicator.is_duplicate() → doublon ?
4. Exécution (paper ou live CCXT)
5. Deduplicator.register()
6. TradeLogger.log()
```

**Variables d'environnement :**
```
BINANCE_API_KEY=            # active le mode live si renseigné
BINANCE_API_SECRET=
BINANCE_TESTNET=false       # true = testnet.binance.vision
EXEC_DEDUP_WINDOW=30        # fenêtre déduplication (secondes)
EXEC_TRADE_LOG=databases/trade_log.sqlite
```

---

### 5.4 Monitoring opérationnel

#### `supervision/notifications/ops_notifier.py`

Notifications Telegram typées avec rate-limiting.

```python
from supervision.notifications.ops_notifier import OpsNotifier

notifier = OpsNotifier.from_env()  # lit TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID

notifier.crash("main loop", exc)                              # exception non gérée
notifier.session_halt("drawdown 6%", guard.state())          # halt SessionGuard
notifier.ws_disconnect("BTC/USDT", stale_seconds=90.0)       # données WS obsolètes
notifier.order_rejected("BTC/USDT", "BUY", 0.1, "trop grand")  # ordre rejeté
notifier.live_order_failed("BTC/USDT", "BUY", "InsufficientFunds")  # échec live
notifier.info("message libre", key="ma_cle")                 # alerte générique
```

- **Rate-limiting :** même type d'événement non ré-envoyé avant `OPS_ALERT_COOLDOWN` secondes (défaut : 60s)
- **Mode silencieux :** si `TELEGRAM_BOT_TOKEN` est vide, toutes les méthodes sont des no-ops

---

#### `supervision/ops_watchdog.py`

Hub de monitoring — connecte tous les hooks en un seul objet.

```python
from supervision.ops_watchdog import OpsWatchdog

watchdog = OpsWatchdog.from_env()
watchdog.enable_heartbeat(interval_seconds=3600.0)  # ping "bot vivant" toutes les heures

# Dans la boucle principale :
watchdog.notify_startup(mode="paper", symbols=["BTC/USDT"])

watchdog.on_order_result(order)              # alerte si rejeté/échoué
watchdog.on_session_guard(eng._guard)        # alerte si halt (une seule fois par halt)
watchdog.check_ws_staleness("BTC/USDT", last_ts, threshold_seconds=120.0)
watchdog.tick_heartbeat("cycle=42 pnl=+1.2%")

watchdog.notify_shutdown("arrêt manuel")
```

---

### 5.5 Strategy Lab

#### `quant_hedge_ai/strategy_lab/generator.py` — `StrategyGenerator`
```python
generator = StrategyGenerator()
population = generator.generate_population(n=300)
# → liste de dicts stratégie avec entry_indicator, period, threshold, etc.
```

#### `quant_hedge_ai/strategy_lab/parameter_space.py` — `ParameterSpace`
```python
space = ParameterSpace()
params = space.sample()          # échantillon aléatoire dans l'espace de paramètres
bounds = space.get_bounds("period")  # (min, max) pour un paramètre
```

#### `quant_hedge_ai/strategy_lab/signal_builder.py` — `SignalBuilder`
```python
builder = SignalBuilder()
signals = builder.build(strategy, prices)  # → [1, 0, -1, ...] même longueur que prices
```

#### `quant_hedge_ai/strategy_lab/backtest_launcher.py` — `BacktestLauncher`
```python
launcher = BacktestLauncher()
result = launcher.run(strategy, candles)
# → {"sharpe": ..., "pnl": ..., "drawdown": ..., "win_rate": ..., "trades": ...}
```

#### `quant_hedge_ai/strategy_lab/ranker.py` — `StrategyRanker`
```python
ranker = StrategyRanker()
ranked = ranker.rank(results)   # trie par Sharpe décroissant
top10 = ranker.top(results, n=10)
```

#### `quant_hedge_ai/strategy_lab/strategy_db.py` — `StrategyDatabase`
```python
db = StrategyDatabase(path="databases/strategies.json")
db.save(strategy, metrics)
top = db.top(n=20)              # top N par Sharpe
all_strats = db.all()
```

#### `quant_hedge_ai/strategy_lab/batch_runner.py` — `BatchRunner`
```python
runner = BatchRunner()
results = runner.run_batches(strategies, candles, batch_size=50)
```

#### `quant_hedge_ai/strategy_lab/parallel_engine.py` — `ParallelEngine`
```python
engine = ParallelEngine(n_jobs=4)
results = engine.run(strategies, candles)  # joblib ou multiprocessing
```

#### `quant_hedge_ai/strategy_lab/evolution_engine.py` — `StrategyEvolutionEngine`
```python
evo = StrategyEvolutionEngine()
evolved = evo.evolve(population, candles, generations=5)
```

#### `quant_hedge_ai/strategy_lab/market_db.py` — `MarketDatabase`
```python
db = MarketDatabase(db_path="databases/market_data.sqlite", max_age_days=30)
saved = db.save_snapshot(market)                 # INSERT OR IGNORE
candles = db.get_history("BTC/USDT", limit=200)
snap = db.get_latest_snapshot()
stats = db.get_stats()
# stats["real_ratio"]   → ratio données réelles
# stats["oldest"]       → timestamp le plus ancien
# stats["newest"]       → timestamp le plus récent
# stats["total_candles"]
```

---

### 5.6 Supervision & alertes

#### `supervision/alert_manager.py`

```python
from supervision.alert_manager import Alert, AlertManager

alert = Alert(
    type_="order_size_anomaly",
    severity="critical",     # "info" | "warning" | "critical"
    module="execution",
    message="Taille anormale : 999999",
    context={"symbol": "BTC/USDT", "size": 999999},
)

manager = AlertManager(audit_file="alerts_audit.jsonl")
manager.register_autoheal("execution", lambda a: {"action": "force_size", "new_size": 1.0})
manager.raise_alert(alert)     # écrit dans audit + déclenche autoheal si critical
alerts = manager.get_alerts(filter_func=lambda a: a.severity == "critical")
```

#### `supervision/notifications/telegram_notifier.py`
```python
tg = TelegramNotifier(bot_token="...", chat_id="...")
ok = tg.notify("Message texte")   # True si envoyé, False si erreur
```

#### `supervision/notifications/multi_notifier.py`
```python
multi = MultiNotifier(notifiers=[telegram, slack, email])
multi.notify("Message diffusé à tous")   # continue si un notificateur échoue
```

---

### 5.7 Portefeuille & risque

#### `quant_hedge_ai/agents/portfolio/__init__.py`

```python
from quant_hedge_ai.agents.portfolio import PortfolioBrain

brain = PortfolioBrain()
allocation = brain.compute_allocation(
    strategy_scores=[{"strategy_id": "s1", "sharpe": 2.5, "drawdown": 0.05, "win_rate": 0.6}],
    realized_vol=0.02,
    max_strategy_weight=0.30,
)
state = brain.get_state()
# state["kelly_win_rate"] · state["target_vol"]
```

#### `quant_hedge_ai/agents/risk/drawdown_guard.py`
```python
guard = DrawdownGuard()
size = guard.adjust_position_size(drawdown=0.08, base_size=1.0)
# → réduit la taille proportionnellement au drawdown (facteur 1 - dd×2.5)
```

#### `quant_hedge_ai/agents/risk/risk_monitor.py`
```python
monitor = RiskMonitor(max_drawdown=0.20)
ok = monitor.check(result)   # True si result["drawdown"] ≤ 0.20
```

---

### 5.8 Évolution IA

#### `quant_hedge_ai/ai_evolution/evolution_engine.py`
```python
from quant_hedge_ai.ai_evolution.evolution_engine import EvolutionEngine

engine = EvolutionEngine(population_size=60, memory_seed_ratio=0.3, generations=2)
report = engine.run_cycle(cycle=1, regime="trending", candles=bt_data, doctor_health=100.0)
print(engine.render(report))
```

#### `quant_hedge_ai/ai_evolution/strategy_memory.py`
```python
from quant_hedge_ai.ai_evolution.strategy_memory import StrategyMemoryStore

memory = StrategyMemoryStore()
memory.save_for_regime("trending", top_strategies)
loaded = memory.load_by_regime("trending", limit=20)
```

---

### 5.9 Moteur principal

#### `stream_bus.py` — `StreamBus`

WebSocket CCXT temps réel dans un thread daemon.

```python
from stream_bus import StreamBus

bus = StreamBus(
    symbols=["BTC/USDT", "ETH/USDT"],
    exchange_id="binance",
    whale_threshold_usd=500_000,
)
# Démarrer dans un thread
threading.Thread(target=lambda: asyncio.run(bus.start()), daemon=True).start()

snap = bus.snapshot
price = snap.get_mid_price("BTC/USDT")
imbalance = snap.get_orderbook_imbalance("BTC/USDT", depth=10)
spread = snap.get_spread("BTC/USDT")
age = time.time() - snap.updated_at   # secondes depuis dernière mise à jour
```

#### `global_risk_gate.py` — `GlobalRiskGate`

Circuit breaker systémique — bloque les cycles si les seuils globaux sont franchis.

```python
from global_risk_gate import GlobalRiskGate, RiskLevel, RiskThresholds

gate = GlobalRiskGate(thresholds=RiskThresholds(...), telegram_bot=bot)
snap = await gate.check(portfolio_brain, scoreboard, market_db)

if snap.level == RiskLevel.CRITICAL:
    continue   # skip cycle
elif snap.level == RiskLevel.WARNING:
    execution.set_size_factor(snap.size_factor)   # réduire la taille
```

---

## 6. Variables d'environnement

Copier `.env.example` en `.env` et renseigner les valeurs.

### Binance API (trading live)
| Variable | Défaut | Description |
|----------|--------|-------------|
| `BINANCE_API_KEY` | *(vide)* | Clé API Binance — mode paper si absent |
| `BINANCE_API_SECRET` | *(vide)* | Secret API Binance |
| `BINANCE_TESTNET` | `false` | `true` = testnet.binance.vision (sans argent réel) |

### Scanner marché
| Variable | Défaut | Description |
|----------|--------|-------------|
| `MARKET_SCANNER_EXCHANGE` | `binance` | Exchange CCXT |
| `MARKET_SCANNER_TIMEFRAME` | `1h` | Timeframe OHLCV |
| `MARKET_SCANNER_LIMIT` | `200` | Bougies par fetch |
| `MARKET_SCANNER_SYNTHETIC` | `false` | Forcer données synthétiques (CI/tests) |
| `MARKET_SCANNER_CACHE_TTL` | `60` | TTL cache en secondes |

### Sécurité live trading
| Variable | Défaut | Description |
|----------|--------|-------------|
| `EXEC_DEDUP_WINDOW` | `30` | Fenêtre déduplication ordres (secondes) |
| `EXEC_MAX_DD` | `0.05` | Drawdown max de session (5%) avant halt |
| `EXEC_MAX_LOSS` | `0.03` | Perte max de session (3%) avant halt |
| `EXEC_MAX_CONSEC_LOSSES` | `3` | Pertes consécutives max avant halt |
| `EXEC_MAX_ORDER_USD` | `10000` | Taille max d'un ordre en USD |
| `EXEC_TRADE_LOG` | `databases/trade_log.sqlite` | Chemin du log SQLite |

### Alertes Telegram
| Variable | Défaut | Description |
|----------|--------|-------------|
| `TELEGRAM_BOT_TOKEN` | *(vide)* | Token bot Telegram — pas d'alerte si absent |
| `TELEGRAM_CHAT_ID` | *(vide)* | ID du chat Telegram |
| `OPS_ALERT_COOLDOWN` | `60` | Délai minimum entre deux alertes du même type (secondes) |

---

## 7. CI/CD — GitHub Actions

Fichier : `.github/workflows/ci.yml`

### Jobs et déclencheurs

| Job | Déclenché sur | Durée estimée |
|-----|--------------|--------------|
| `lint` | tous les push/PR | ~30s |
| `smoke` | tous les push/PR (parallèle avec lint) | ~60s |
| `tests` | après lint | ~2 min |
| `validate-strategies` | merge sur `main` uniquement | ~2 min |

### Secrets GitHub à configurer

Settings → Secrets and variables → Actions → New repository secret

| Secret | Obligatoire | Usage |
|--------|:-----------:|-------|
| `BINANCE_API_KEY` | Non | Active le trading live dans CI |
| `BINANCE_API_SECRET` | Non | Idem |
| `TELEGRAM_BOT_TOKEN` | Non | Active les alertes Telegram dans CI |
| `TELEGRAM_CHAT_ID` | Non | Idem |

Sans secrets, le CI tourne en mode **paper** + **données synthétiques** — aucune clé requise pour que le CI passe.

### Seuil de couverture
```
--cov-fail-under=60   (défini dans ci.yml)
```

---

## 8. Scripts disponibles

### `scripts/smoke_test_ci.py`
Vérification rapide de tous les modules (zéro réseau).
```bash
python scripts/smoke_test_ci.py
# Exit 0 = OK, Exit 1 = au moins un module défaillant
```

### `scripts/validate_historical.py`
Validation walk-forward des stratégies sur données historiques.
```bash
python scripts/validate_historical.py --help

# Mode hors-ligne (synthétique)
python scripts/validate_historical.py --synthetic --years 1

# Mode réel (nécessite clé Binance dans .env)
python scripts/validate_historical.py \
  --symbols BTC/USDT ETH/USDT SOL/USDT \
  --timeframe 1h \
  --years 2 \
  --top-n 20 \
  --output databases/walk_forward_results.json
```

Résultat JSON dans `databases/walk_forward_results.json` :
```json
{
  "meta": {"date": "...", "symbols": [...], "synthetic": false},
  "by_symbol": {
    "BTC/USDT": {
      "n_candles": 17520,
      "summary": {"total": 20, "robust": 5, "overfit_rate": 0.10, ...},
      "results": [{"in_sample": {...}, "out_of_sample": {...}, "verdict": "ROBUSTE"}]
    }
  }
}
```

### `quant_hedge_ai/main_v91.py`
Boucle principale autonome.
```bash
python -m quant_hedge_ai.main_v91                   # boucle infinie
python -m quant_hedge_ai.main_v91 --max-cycles 5    # 5 cycles puis arrêt
python -m quant_hedge_ai.main_v91 --dry-run         # valide la config et sort
python -m quant_hedge_ai.main_v91 --radar           # un seul sweep MarketRadar
python -m quant_hedge_ai.main_v91 --dashboard       # active le Director Dashboard
```

---

*Documentation générée automatiquement — mise à jour à chaque évolution majeure.*
