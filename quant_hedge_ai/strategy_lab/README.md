# Strategy Lab — Exemples d'utilisation

## Génération, backtest et ranking

```python
from strategy_lab.generator import StrategyGenerator
from strategy_lab.parameter_space import ParameterSpace
from strategy_lab.templates import StrategyTemplate
from strategy_lab.signal_builder import SignalBuilder
from strategy_lab.backtest_launcher import BacktestLauncher
from strategy_lab.ranker import StrategyRanker
from strategy_lab.strategy_db import StrategyDatabase

# Génération de stratégies
features = ['momentum_14']
templates = ['momentum']
generator = StrategyGenerator(features, templates)
combos = generator.generate()

# Paramètres
param_space = ParameterSpace('momentum')
grid = param_space.get_grid()

# Template
logic = 'IF momentum_14 > {threshold}: BUY ELSE: HOLD'
template = StrategyTemplate('momentum', logic)

# Signal, backtest, DB
db = StrategyDatabase()
for params in grid:
    sb = SignalBuilder(template, params)
    data = {'momentum_14': [0.01, 0.04, 0.03, 0.05]}
    bl = BacktestLauncher(None)
    metrics = bl.run(sb, data)
    score = metrics['n_buy'] - metrics['n_hold']
    db.save(f"strat_{params['threshold']}", params, metrics, -score)

# Top stratégies
top = db.top_strategies(1)
print(top)
```

## Parallélisation

```python
from strategy_lab.parallel_engine import ParallelEngine
def square(x): return x * x
engine = ParallelEngine(n_jobs=2)
results = engine.run_joblib([1,2,3,4], square)
print(results)
```
