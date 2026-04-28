# 📚 Documentation enrichie et guides d’utilisation

Pour une prise en main rapide, une documentation professionnelle et des exemples d’utilisation prêts à copier, consultez :

- [README_CONSOLIDATED.md](README_CONSOLIDATED.md) — Guide d’installation, configuration, lancement rapide, FAQ, bonnes pratiques
- [DASHBOARD_USAGE_TEMPLATES.md](DASHBOARD_USAGE_TEMPLATES.md) — Exemples d’utilisation pour chaque dashboard (Panel/Streamlit)
- [ACTION_PLAN_CHECKLIST.md](ACTION_PLAN_CHECKLIST.md) — Plan d’action détaillé pour finaliser et maintenir le système

**Conseil :** Commencez par le README_CONSOLIDATED.md pour une vue d’ensemble, puis utilisez les templates et le plan d’action pour accélérer votre onboarding ou vos évolutions.

---

## English quick orientation

For a professional onboarding, usage examples, and a step-by-step action plan, see:
- [README_CONSOLIDATED.md](README_CONSOLIDATED.md)
- [DASHBOARD_USAGE_TEMPLATES.md](DASHBOARD_USAGE_TEMPLATES.md)
- [ACTION_PLAN_CHECKLIST.md](ACTION_PLAN_CHECKLIST.md)

---
# ⚡ QUICK START - V9.1 Autonomous Quant Lab

## 🎯 5-Minute Setup

### Step 1: Activate Environment
```powershell
cd c:\Users\WINDOWS\crypto_ai_terminal
.\.venv\Scripts\Activate.ps1
```

### Step 2: Navigate to V9.1
```powershell
cd quant-hedge-ai
```

```{dropdown} 🚀 Démarrage rapide V9.1
```

```{dropdown} 1. Prérequis
- Python 3.11+ (recommandé 3.12)
- Windows 10/11 ou Linux
- 4GB RAM min
- 2GB disque libre
```

```{dropdown} 2. Installation
```

```{dropdown} a) Cloner le dépôt
```powershell
git clone https://github.com/<OWNER>/<REPO>.git
cd <REPO>
```
```

```{dropdown} b) Créer un environnement virtuel
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
```

```{dropdown} c) Installer les dépendances
```powershell
pip install -r requirements.txt
```
```

```{dropdown} 3. Lancer le laboratoire quantitatif
```powershell
cd quant-hedge-ai
python main_v91.py
```
```

```{dropdown} 4. Lancer le dashboard (optionnel)
```powershell
panel serve dashboard/dashboard_panel.py --port 5010 --show
```
```

```{dropdown} 5. Exécuter les tests (optionnel)
```powershell
python run_all_tests.py
```
```

```{dropdown} 6. Ressources utiles
- [Documentation complète](DOCUMENTATION_AUTOMATIQUE.md)
- [FAQ](FAQ_EVOLUTION_DASHBOARD_FR.md)
- [Configuration avancée](CONFIG_REFERENCE_V91.md)
```
  strat_1: 13.70%
  strat_2: 12.10%
  strat_3: 11.36%
  strat_5: 8.70%
  Kelly Fraction: 0.2500               ← Max Kelly risk
  Vol Target: 0.4342                   ← Volatility adjustment
  Max Position: 30.00%                 ← Max single-strategy cap

⚡ EXECUTION DECISION
  Should Trade: NO                     ← Trade recommendation
  Reason: Market conditions unfavorable ← Why blocked
  Risk Limits:
    Max Position: 0.0461               ← Max allowed position
    Stop Loss: 0.0400                  ← Risk limit
    Take Profit: 0.0800                ← Profit target

❤️  SYSTEM HEALTH
  Status: running
  Agents Active: 20                    ← Number of agents
  Strategies Generated: 300            ← Strategies tried this cycle
  Backtests Completed: 300             ← Tests run
  Model Version: 1                     ← ML model version

================================================================================

📊 MonteCarlo Results: {'median_terminal': 0.7426, 'p05_terminal': 0.1793, 'p95_terminal': 3.0357}
💰 Paper Trading State: {'balance': 100000.0, 'positions': {}}
```

---

## 🔍 UNDERSTANDING THE OUTPUT

### Market Regime Section
```
WHAT IT MEANS:
- high_volatility_regime  = Market is choppy, good for vol harvesting
- bull_trend              = Strong uptrend, momentum following recommended
- bear_trend              = Downtrend, short strategies make sense
- sideways                = Range-bound, mean reversion works
- flash_crash             = Extreme, trading blocked (too dangerous)

WHAT TO DO:
1. Note the regime
2. Check suggested strategy type
3. Look at momentum & volatility numbers
4. Use to validate AI's decision
```

### Whale Radar Section
```
THREAT LEVELS:
- LOW       = Normal trading activity, safe to trade
- MEDIUM    = Some anomalies detected, proceed cautiously
- HIGH      = Major whale activity, consider reducing size
- CRITICAL  = Extreme activity, trading BLOCKED

WHAT TO WATCH:
- WHALE_BUY = Large buy pressure (could pump)
- WHALE_SELL = Large sell pressure (could dump)
- INFLOW_TO_EXCHANGE = Selling pressure coming
- OUTFLOW_FROM_EXCHANGE = HODLing detected, accumulation
```

### Best Strategy Section
```
✅ GOOD SIGNALS:
- Sharpe > 10  = Strong risk-adjusted returns
- Drawdown < 3% = Well-controlled downside
- Win Rate > 65% = More hits than misses
- PnL > 30%  = Good profit potential

⚠️ RED FLAGS:
- Sharpe < 5  = Weak signal, risky
- Drawdown > 15% = High downside risk
- Win Rate < 50% = More losses than gains
```

### Execution Decision Section
```
TRADING RULES:
✅ Trade IF:
- Best Sharpe > 2.0
- Drawdown < 10%
- Regime != flash_crash
- Whale alerts <= 2

❌ Block IF:
- Sharpe is weak
- Drawdown too high
- Whale threat level HIGH
- Market in crash regime
```

---

## 📈 WHAT EACH COMPONENT DOES

### 1. Intelligence Layer
```python
# Analyzes market microstructure
momentum = 0.0234        # Price momentum
vol = 0.045             # Volatility
volume_trend = 1.2      # Volume spike
trend_strength = 0.78   # Uptrend strength
```
💡 **Result**: Better understanding of market conditions

### 2. Whale Radar
```python
# Scans for large transactions
whale_buy_1M = True     # Detected 1M+ USD buy
threat_level = "MEDIUM" # Classified as medium risk
```
💡 **Result**: Protects from getting caught in whale moves

### 3. AI Portfolio Brain
```python
# Allocates capital using Kelly criterion
kelly_fraction = (bp - q) / b = 0.25
position_size = capital * kelly_fraction
adjusts for current volatility
```
💡 **Result**: Optimal position sizing that adapts to risk

### 4. Decision Engine
```python
# Ranks strategies and decides if trading is good
composite_score = (Sharpe/DD) * (1 + WR*0.1)
best_strategy = max(scores)
should_trade = (sharpe > 2.0) AND (dd < 0.1)
```
💡 **Result**: Intelligent trade filtering

---

## 🎯 INTERPRETING RESULTS

### Green Light (Trade!)
```
✅ Sharpe: 14.1399      (Very strong)
✅ Drawdown: 0.0189     (Very low risk)
✅ Win Rate: 0.75       (75% wins)
✅ Whale Threat: LOW
✅ Regime: bull_trend
✅ Should Trade: YES

→ System ready to execute trades
```

### Yellow Light (Be Careful)
```
⚠️  Sharpe: 8.5234      (Moderate)
⚠️  Drawdown: 0.0845    (Acceptable)
⚠️  Win Rate: 0.55      (Just above 50%)
⚠️  Whale Threat: MEDIUM
⚠️  Regime: sideways
⚠️  Should Trade: YES (with reduced size)

→ System still trades but with smaller positions
```

### Red Light (Don't Trade)
```
❌ Sharpe: 2.1234       (Weak)
❌ Drawdown: 0.1845     (High)
❌ Win Rate: 0.48       (Below 50%)
❌ Whale Threat: HIGH
❌ Regime: flash_crash
❌ Should Trade: NO

→ System BLOCKS trading - too risky
```

---

## 🚀 RUNNING DIFFERENT SCENARIOS

### Scenario 1: Test Run (validate it works)
```powershell
$env:V9_MAX_CYCLES="1"
$env:V9_POPULATION="100"
python main_v91.py
```
**Takes:** ~5 seconds  
**Tests:** 100 strategies  
**Use:** Check everything is working

---

### Scenario 2: Research Run (gather data)
```powershell
$env:V9_MAX_CYCLES="10"
$env:V9_POPULATION="300"
python main_v91.py
```
**Takes:** ~30 seconds  
**Tests:** 3,000 strategies total  
**Use:** Get meaningful statistics

---

### Scenario 3: Extended Run (overnight)
```powershell
$env:V9_MAX_CYCLES="0"
$env:V9_POPULATION="500"
$env:V9_SLEEP_SECONDS="1"
# Let it run for hours...
```
**Takes:** Hours  
**Tests:** Thousands of strategies  
**Use:** Build comprehensive strategy database

---

## 📊 MONITORING OUTPUT FILES

After running V9.1, check:

```
quant-hedge-ai/
├── data/
│   ├── market_snapshots.jsonl        ← Market history
│   ├── best_strategies.json          ← Top strategies
│   └── strategy_scoreboard.json      ← Leaderboard
├── logs/
│   └── v91_cycle_X.log              ← Execution logs
```

### Reading Market Snapshots
```json
{
  "candles": [
    {"symbol": "BTCUSDT", "open": 42000, "close": 42100, "volume": 250000, ...},
    {"symbol": "ETHUSDT", "open": 2300, "close": 2320, "volume": 150000, ...}
  ]
}
```

### Reading Strategy Scoreboard
```json
[
  {
    "strategy": {"entry_indicator": "RSI", "exit_indicator": "MACD", "period": 29},
    "metrics": {"sharpe": 14.1399, "drawdown": 0.0189, "pnl": 50.7497, "cycle": 1}
  },
  ...
]
```

---

## 🆘 TROUBLESHOOTING

### Issue: "ModuleNotFoundError: No module named 'agents.intelligence'"

**Solution:**
```powershell
# Ensure you're in the right directory
cd quant-hedge-ai

# Check Python path
python -c "import sys; print(sys.path)"

# Run with explicit path
$env:PYTHONPATH="."
python main_v91.py
```

---

### Issue: "Connection refused" (Whale Radar)

**Solution:** Whale Radar is synthetic (doesn't connect to real APIs). This is normal.

---

### Issue: "JSON decode error" in Scoreboard

**Solution:**
```powershell
# Delete corrupted scoreboard
Remove-Item databases\strategy_scoreboard.json

# Restart - will create fresh
python main_v91.py
```

---

## 📚 NEXT READING

After running V9.1, read these in order:

1. **README_V91.md** - Feature overview
2. **V91_COMPLETE_SUMMARY.md** - Deep dive into each module
3. **ROADMAP_V9_V10_V11.md** - Vision for future versions
4. **RAPPORT_GLOBAL_V9.md** - Full system documentation

---

## 🎓 LEARNING RESOURCES

### Understanding the Concepts

**Kelly Criterion**
- Formula: `f = (bp - q) / b`
- Why: Optimal position sizing
- Read: "The Kelly Criterion in Betting & Trading"

**Volatility Targeting**
- Formula: `scale = target_vol / realized_vol`
- Why: Adapt to market conditions
- Read: "Risk Parity Fundamentals"

**Sharpe Ratio**
- Formula: `(mean_return - rf) / std_dev`
- Why: Risk-adjusted return metric
- Read: "Portfolio Selection" by Markowitz

**Genetic Algorithms**
- Process: Generate → Evaluate → Select → Mutate → Repeat
- Why: Evolve strategies naturally
- Read: "An Introduction to Genetic Algorithms"

---

## 💡 PRO TIPS

### Tip 1: Custom Population Size
```powershell
# More strategies = better exploration
$env:V9_POPULATION="1000"
# Fewer = faster iteration
$env:V9_POPULATION="100"
```

### Tip 2: Monitor in Real-time
```powershell
# In one terminal
python main_v91.py > log.txt

# In another terminal
Get-Content -Path log.txt -Wait
```

### Tip 3: Save Results
```powershell
# Append output to file
python main_v91.py >> results_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt
```

### Tip 4: Compare Runs
```powershell
# Run multiple times and compare scoreboard
python main_v91.py
# Check databases\strategy_scoreboard.json
```

---

## ✅ CHECKLIST BEFORE PRODUCTION

- [ ] Can run V9.1 without errors
- [ ] Understand the Control Center output
- [ ] Know what each metric means
- [ ] Read all documentation
- [ ] Run at least 3 cycles successfully
- [ ] Check strategy scoreboard database
- [ ] Review backtest quality
- [ ] Plan V10 upgrade

---

## 🚀 YOU'RE READY!

V9.1 is **complete and tested**. Now:

1. ✅ Run V9.1 to see it work
2. ✅ Study the output metrics
3. ✅ Understand the decision logic
4. ✅ Plan your next steps
5. ✅ Consider V10 upgrade when ready

---

**Happy Trading! 🎯**
