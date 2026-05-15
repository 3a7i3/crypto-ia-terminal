# Tracker System — Phase 1-7 Complete

**Status:** Production ready

## What is this?

Un système de trading **modulaire et auto-apprenant** qui:
1. Ouvre/gère/ferme positions
2. Applique des règles d'exit intelligentes
3. Mesure la performance
4. Optimise les paramètres
5. Apprend du passé
6. Adapte les décisions automatiquement

## Architecture

```
DATA FLOW:
Price Update
    ↓
update_positions()
    ↓
check_exit() via ExitEngine
    ↓
Log to JSONL
    ↓
compute_metrics()
    ↓
auto_backtester()
    ↓
MetaLearner learns
    ↓
Next trade uses learned params
```

## Key Components

### 1. Trade Tracker (Phase 1)
```python
from tracker_system.core.trade_tracker import open_position, update_positions

# Open
pos = open_position("BTCUSDT", "BUY", 50000, 0.1, regime="bull_trend")

# Update prices
closed = update_positions({"BTCUSDT": 51000})
```

### 2. Exit Engine (Phase 2)
Automatically selects best exit based on regime:
- **bull_trend**: TP=3%, SL=1.5%, Trailing=0.7%
- **range**: TP=1.2%, SL=0.8%, Trailing=0.4%
- **bear_trend**: TP=2%, SL=1.2%, Trailing=0.6%

### 3. Metrics (Phase 3)
```python
from tracker_system.analytics.metrics import compute_all_metrics

m = compute_all_metrics()
# {
#   "trades": 100,
#   "winrate": 0.58,
#   "expectancy": 0.0045,
#   "pnl_total": 450,
#   "mfe_avg": 0.025,
#   "mae_avg": 0.010
# }
```

### 4. Auto Backtester (Phase 4)
```python
from tracker_system.backtesting.auto_backtester import run_backtest

optimizer = run_backtest()
# Saves to logs/optimizer.json
# Finds best TP/SL combinations per regime
```

### 5. Meta Learning (Phase 6)
```python
from meta_learning.learner import MetaLearner

learner = MetaLearner()
learner.learn_from_trade(
    context={"regime": "bull_trend", "volatility": 0.02},
    decision={"tp": 0.03, "sl": 0.015},
    pnl_pct=0.025
)

# Later: find best decision for similar context
best = learner.find_best_decision(similar_context)
```

### 6. Decision Engine (Phase 7)
```python
from meta_learning.decision_engine import DecisionEngine

engine = DecisionEngine(meta_learner)
decision = engine.get_exit_decision(context)
# Uses: meta_learned > config > default
```

## Data Flow

### Entry
```json
{
  "type": "entry",
  "symbol": "BTCUSDT",
  "side": "BUY",
  "entry_price": 50000.0,
  "size": 0.1,
  "regime": "bull_trend",
  "confidence": 0.85,
  "timestamp": "2026-05-05T..."
}
```

### Exit
```json
{
  "type": "exit",
  "symbol": "BTCUSDT",
  "entry_price": 50000.0,
  "exit_price": 51500.0,
  "pnl_pct": 0.03,
  "pnl_usd": 150.0,
  "mfe": 0.035,
  "mae": 0.005,
  "exit_reason": "TP @ 51500.00000000",
  "regime": "bull_trend",
  "duration_min": 5.2
}
```

## Files & Folders

```
tracker_system/
  core/           # open/update/close positions
  engine/         # exit rules & factory
  config/         # regime parameters
  analytics/      # metrics & analysis
  backtesting/    # optimization
  storage/        # JSONL load/save

meta_learning/
  memory.py       # stores decisions + performance
  similarity.py   # finds similar contexts
  learner.py      # finds best past decision
  decision_engine.py # intelligent selection

scripts/
  test_phase*.py  # validation tests
  quickstart.py   # usage examples
  
logs/
  trades.jsonl    # all entry/exit events
  optimizer.json  # best params per regime
  meta_memory.jsonl # learning history
```

## Usage Examples

### Run Trade
```python
from tracker_system.core.trade_tracker import open_position, update_positions

# Entry
pos = open_position("ETHUSDT", "BUY", 2000, 1.0, regime="bull_trend", confidence=0.8)

# Price update
closed = update_positions({"ETHUSDT": 2050})  # +2.5% profit
```

### Check Performance
```python
from tracker_system.analytics.metrics import compute_all_metrics

metrics = compute_all_metrics()
print(f"Winrate: {metrics['winrate']:.2%}")
print(f"Expectancy: {metrics['expectancy']:.6f}")
```

### Optimize
```python
from tracker_system.backtesting.auto_backtester import run_backtest

run_backtest()  # generates optimizer.json
```

### Use Meta Learning
```python
from meta_learning.decision_engine import DecisionEngine

engine = DecisionEngine()
decision = engine.get_exit_decision({
    "regime": "bull_trend",
    "volatility": 0.02,
    "confidence": 0.8
})
print(f"TP: {decision['tp']}, SL: {decision['sl']}")
```

## Tests

All phases tested:
```bash
python scripts/test_phase1_tracker.py        # entry/exit/logs
python scripts/test_phase3_metrics.py        # metrics
python scripts/test_phase4_backtester.py     # optimizer
python scripts/test_phase6_meta_learning.py  # learning
python scripts/test_phase7_decision_engine.py # integration
python scripts/test_integration_full.py      # FULL PIPELINE
```

## Clean Structure Entrypoint

Use the structured package entrypoint when you want a clean operational surface:

```bash
python tracker_system/main.py --bootstrap
python tracker_system/main.py --status
python tracker_system/main.py --prices '{"BTC/USDT": 64000}'
python tracker_system/main.py --prices '{"BTC/USDT": 64000}' --optimizer
```

What each mode does:
- `--bootstrap`: creates the runtime files needed for the tracker MVP.
- `--status`: prints the effective structure and the role of each tracker block.
- default run: sync trades, update positions, compute metrics, update dashboard.

## Production Checklist

- [x] Tracker opens/closes positions correctly
- [x] Exit rules fire at correct prices
- [x] JSONL logs are clean
- [x] Metrics are accurate
- [x] Backtester finds optimal params
- [x] Meta learner retains decisions
- [x] Decision engine selects intelligently
- [x] No hardcoded values
- [x] All tests pass
- [x] Zero external dependencies (JSON only)

## KPIs — Statut de fiabilité en production (2026-05-11)

| Métrique | Fiable prod ? | Note |
|----------|--------------|------|
| Winrate global | ✅ Oui | Mais trompeur seul — toujours croiser avec avg_loss |
| Expectancy | ✅ Oui | Indicateur synthétique sain |
| PnL total | ✅ Oui | Référence réalisée |
| Performance par régime | ✅ Oui | Sortie produit principale |
| Drawdown % actuel | ⚠️ Exploratoire | Calculé sur PnL réalisé, pas normalisé sur capital |
| avg_win / avg_loss | ❌ Manquant | À implémenter — P0 |
| Profit factor | ❌ Manquant | À implémenter — P0 |
| Worst trade | ❌ Manquant | À implémenter — P0 |
| Rolling 20 trades | ❌ Manquant | À implémenter — P1 |
| Score stability | ❌ Manquant | À implémenter — P1 |

## Garde-fous régime (à implémenter)

- **sideways/range faible** : no-trade gate requis (0 % winrate observé, -3,05 % avg PnL)
- Taille de position sideways ≤ 0,3× du sizing normal si profit factor < 1
- Alerte si winrate ≥ 85 % ET PnL négatif (signe de pertes asymétriques)

## Next Steps (Phase 8-9)

### Phase 8: Dashboard
- Real-time metrics view
- Learning evolution chart
- Best decisions heatmap
- Performance by regime

### Phase 9: Audit Engine
- Trade replay with trace
- Decision explanations
- Error analysis
- Counterfactual "what-if"

## Support

Each module is independent and testable.
See test files for examples.
