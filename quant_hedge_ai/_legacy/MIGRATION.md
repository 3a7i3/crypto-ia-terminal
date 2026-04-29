---
title: Migration Guide — Legacy Archive
description: How to migrate code that imported archived modules
---

# Migration Guide

If you have code importing from archived modules, use these alternatives:

## research/* → ai_evolution + agents.quant

**Old:**
```python
from quant_hedge_ai.agents.research.feature_engineer import extract_features
from quant_hedge_ai.agents.research.model_builder import build_model
```

**New:**
```python
# For feature extraction: use indicators from backtest_lab
from quant_hedge_ai.agents.quant.backtest_lab import _ema, _rsi, _bollinger

# For model building / optimization: use genetic algorithms
from quant_hedge_ai.ai_evolution.evolution_engine import EvolutionEngine
```

## intelligence/* → agents.market

**Old:**
```python
from quant_hedge_ai.agents.intelligence.regime_detector import detect_regime
```

**New:**
```python
# Use volatility agents or backtest analysis instead
from quant_hedge_ai.agents.market.volatility_agent import VolatilityAgent
# Or detect via backtest Sharpe ratios (stability indicator)
```

## liquidity_map/* → agents.execution

**Old:**
```python
from quant_hedge_ai.liquidity_map.flow_analyzer import analyze_flow
```

**New:**
```python
# Use execution engine's liquidity agent
from quant_hedge_ai.agents.execution.liquidity_agent import LiquidityAgent
```

## massive_backtest_engine/* → agents.quant.backtest_lab

**Old:**
```python
from quant_hedge_ai.massive_backtest_engine import run_backtest_batch
```

**New:**
```python
# Modern backtest with walk-forward validation
from quant_hedge_ai.agents.quant.backtest_lab import BacktestLab
from quant_hedge_ai.agents.quant.walk_forward import WalkForwardValidator

lab = BacktestLab()
result = lab.run_backtest(strategy, candles, timeframe="1h")

validator = WalkForwardValidator(train_ratio=0.7)
verdict = validator.validate(strategy, candles)
```

## market_radar/* → agents.market

**Old:**
```python
from quant_hedge_ai.market_radar.whale_tracker import track_whales
from quant_hedge_ai.market_radar.token_scanner import scan_tokens
```

**New:**
```python
# Use market scanner for OHLCV data
from quant_hedge_ai.agents.market.market_scanner import MarketScanner

scanner = MarketScanner(symbols=["BTCUSDT"], timeframe="1h")
result = scanner.scan()  # Returns {'candles': [...], 'history': {...}}
```

## data/* → strategy_lab

**Old:**
```python
from quant_hedge_ai.data.strategy_database import StrategyDatabase
from quant_hedge_ai.data.market_database import MarketDatabase
```

**New:**
```python
# Use strategy_lab implementations
from quant_hedge_ai.strategy_lab.strategy_db import StrategyDatabase
from quant_hedge_ai.strategy_lab.market_db import MarketDatabase

db = MarketDatabase(db_path="databases/market_data.sqlite", max_age_days=30)
db.save_snapshot(market)
history = db.get_history("BTCUSDT", limit=200)
```

## Removing Imports

**Step 1:** Find all imports:
```bash
grep -r "from quant_hedge_ai.agents.research\|from quant_hedge_ai.market_radar" . --include="*.py"
```

**Step 2:** Replace with new imports (use migration guide above)

**Step 3:** Test:
```bash
python -m pytest -xvs tests/
```

## If an Import is Needed

If you absolutely need the archived code:

1. **Restore temporarily:**
   ```bash
   git checkout HEAD -- quant_hedge_ai/agents/research/
   ```

2. **Write tests** for the module (required before reintegrating)

3. **Open an issue** explaining why the module is needed again

4. **Plan reintegration** into active codebase with full test coverage

---

*Last updated: 2026-04-28*
