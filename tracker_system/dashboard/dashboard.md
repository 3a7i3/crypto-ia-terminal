# Dashboard Intelligence

_Last update: 2026-05-12T23:19:47.291666+00:00_

## Performance
- Trades: 36
- Total PnL: -1.25
- Winrate: 94.44%
- Expectancy: 0.0389

## Surveillance (Drift & Dégradation)
- Score drift: z=0.00 (stable) ✅
  baseline=0.0000 | recent=0.0000 | n_baseline=39 | n_recent=10
- Winrate rolling 20: 90.0% ✅

## Robustesse (KPIs fiables production)
> ⚠️ ALERTE asymétrie : winrate=94.4% mais PnL=-1.25$ — les pertes coûtent trop cher par rapport aux gains. Vérifier avg_loss vs avg_win.

- Profit factor: 23.9419 ✅
- Avg win/loss ratio: 1.4083 ⚠️
- Worst trade: -3.12% (-1.56$)
- Drawdown normalisé: 0.30% (ref capital: 1000$) ✅
  _(normalisé sur capital de référence — fiable en production)_
- Rolling 20 trades: 20 trades | winrate=90.00% | expectancy=0.0420

## Trade Quality
- Avg MFE: 4.08%
- Avg MAE: -0.20%
- Efficiency: 99.32%

## Equity Curve
> ⚠️ Drawdown ci-dessous calculé sur courbe PnL réalisé (exploratoire). Voir "Drawdown normalisé" ci-dessus pour le KPI fiable.
- Last equity: -1.82
- Peak equity: 0.73
- Current drawdown: 2.55
- Max drawdown: 3.05 (419.97%)
- Points: 30

```mermaid
xychart-beta
    title "Realized Equity Curve"
    x-axis [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30]
    y-axis "PnL USD" -2.32 --> 0.73
    line [0.0030, 0.0130, 0.0160, 0.0260, 0.0760, 0.1260, 0.1760, 0.2260, 0.2760, 0.3260, 0.3760, 0.4260, 0.4760, 0.5260, 0.5760, 0.6260, 0.6760, 0.7260, -0.8330, -2.3230, -2.2730, -2.2230, -2.1730, -2.1230, -2.0730, -2.0230, -1.9730, -1.9230, -1.8730, -1.8230]
```


## Regime State
- bull_trend: 33 trades | winrate=100.00% | avg pnl=4.39%
- bullish: 1 trades | winrate=100.00% | avg pnl=1.00%
- sideways: 2 trades | winrate=0.00% | avg pnl=-3.05%

## Optimizer State
### bull_trend
- TP: 0.012
- SL: 0.008
- Trailing: 0.004
- Score: 0.043939
- Winrate: 100.00%
### bullish
- TP: 0.012
- SL: 0.008
- Trailing: 0.004
- Score: 0.020000
- Winrate: 100.00%
### sideways
- TP: 0.012
- SL: 0.008
- Trailing: 0.004
- Score: -0.000000
- Winrate: 0.00%
