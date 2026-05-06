# ⚡ QUICKSTART — Optimization Stack

## Installation (30 secondes)

```bash
cd crypto_ai_terminal
pip install -r requirements.txt
```

---

## Utilisation Immédiate (1 minute)

### Option 1: Démarrage optimisé (recommandé)

**Modifiez votre `main.py` ou `advisor_loop.py`:**

```python
from bootstrap_integration import bootstrap_system

# Au début de votre app:
system = bootstrap_system(enable_monitoring=True)

# Maintenant tout est optimisé:
# ✅ Démarrage -50% plus rapide
# ✅ Circuit breaker actif (protège le système)
# ✅ Snapshots salvegardés automatiquement
# ✅ Rapports journaliers générés

# Votre code continue...
from advisors import run_trading_loop
run_trading_loop()
```

---

### Option 2: Quick test

```bash
# Validez que tout fonctionne:
python test_optimization_stack.py
# ✅ 7/7 tests PASSED

# Consultez le rapport:
cat INTEGRATION_REPORT.md
```

---

## 📊 Vérifier l'état du système

```bash
# Boot performance
python bootstrap_integration.py --health-check

# Daily report
python daily_analyzer.py

# Cache stats
python startup_cache.py

# Circuit breaker test (30s)
python circuit_breaker.py
```

### Windows: Tracker scheduler helper

```powershell
# Start periodic tracker refresh
.\tracker_scheduler.ps1 start -IntervalSeconds 300 -LogFile tracker_system/logs/auto_update.log

# Check current status
.\tracker_scheduler.ps1 status

# Check current status as JSON for scripts
.\tracker_scheduler.ps1 status -Json

# Restart scheduler
.\tracker_scheduler.ps1 restart -IntervalSeconds 300 -NoOptimizer

# Run exactly one foreground cycle without optimizer
.\tracker_scheduler.ps1 once -NoOptimizer

# Run exactly one foreground cycle with optimizer
.\tracker_scheduler.ps1 once -Optimizer

# Read last scheduler log lines
.\tracker_scheduler.ps1 logs -Tail 30

# Purge pid file and truncate scheduler log
.\tracker_scheduler.ps1 clean -Force

# Purge pid/log and return a JSON summary
.\tracker_scheduler.ps1 clean -Force -Json

# Stop scheduler
.\tracker_scheduler.ps1 stop

# Stop scheduler and return before/after status as JSON
.\tracker_scheduler.ps1 stop -Json

# Automated helper smoke test
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test_tracker_scheduler_helper.ps1
```

JSON payloads returned by `status -Json`, `stop -Json`, and `clean -Json` are documented in `TRACKER_SCHEDULER_WINDOWS_README.md`.

---

## 📈 Gains immédiats

| Avant | Après | Gain |
|-------|-------|------|
| Démarrage: 8-10s | 160ms (cache) | **-98%** |
| Crash recovery: manual | Auto (5min) | ✅ Auto |
| Learning persist: ✗ | ✓ SQLite | ✅ Enabled |
| Monitoring: logs | Daily reports | ✅ Automated |

---

## 🔥 3 Commandes Essentielles

```bash
# 1. Vérifier startup time
python warm_boot.py
# → logs/boot_report.json

# 2. Voir rapport du jour
python daily_analyzer.py
# → 🟢 STABLE / 🟡 DRIFT / 🔴 INCIDENT

# 3. Tester le circuit breaker
python circuit_breaker.py
# → 30s live monitoring
```

---

## 🎯 Cas d'usage courants

### ✅ Après crash → restart rapide
```python
system = bootstrap_system()
# Auto-reprend checkpoint + best genomes (160ms!)
```

### ✅ Surveiller la santé
```python
report = analyzer.generate_daily_report()
print(analyzer.format_report_text(report))
# Affiche: 🟢 STABLE (ou 🟡 DRIFT / 🔴 INCIDENT)
```

### ✅ Protéger contre dégradations
```python
breaker = enable_circuit_breaker(on_critical=pause_trading)
# Si memory > 90% → automatiquement PAUSE
# Quand recovery → automatiquement RESUME
```

---

## 📚 Documentation Complète

- **OPTIMIZATION_GUIDE.md** — API détaillée + examples
- **INTEGRATION_REPORT.md** — Rapport complet + benchmarks
- **test_optimization_stack.py** — Tests + validation

---

## ⚠️ Problèmes courants

**Q: Erreur "ModuleNotFoundError: No module named 'psutil'"**  
A: `pip install psutil`

**Q: Cache corrompu**  
A: `rm -rf cache/` (rebuilds automatiquement)

**Q: Circuit breaker toujours OPEN**  
A: 
```python
from circuit_breaker import get_circuit_breaker, CircuitState
breaker = get_circuit_breaker()
breaker.reset()  # Force CLOSED
```

---

## 🚀 Prêt à partir!

```python
# C'est tout ce qu'il faut:
from bootstrap_integration import bootstrap_system
system = bootstrap_system(enable_monitoring=True)

# ✅ Démarrage rapide
# ✅ Monitoring activé  
# ✅ Protection active
# ✅ Apprentissage persistant
```

**Gain temps démarrage: 160ms vs 8-10s avant!** ⚡

---

Pour plus de détails → **OPTIMIZATION_GUIDE.md**
