# Roadmap 2 semaines — à partir du 2026-06-04

> Plan approximatif. L'ordre peut changer selon les signaux du burn-in.
> Règle : ne pas toucher à l'architecture principale avant 100 trades fermés.

---

## Semaine 1 (J1–J7) — Corrections locales + Observation burn-in

### J1–J2 (05-06 juin) — Corrections immédiates

| Tâche | Priorité | Durée est. | Fichier(s) |
|---|---|---|---|
| Spam Telegram : supprimer `_notify()` pour rejets "position deja ouverte" | HAUTE | 30 min | `paper_trading/mexc_simulator.py` |
| Nettoyer `runtime_config.json` : supprimer GATE_MIN_SCORE_OVERRIDE=0 | HAUTE | 15 min | `databases/runtime_config.json` |
| Self-heal exchange : `ExecutionEngine.reconnect()` + retry CCXT 3x | MOYENNE | 2h | `core/advisor_loop.py` |
| Brancher `PaperTradeRecorder` dans `MexcSimulator._fill_market()` + `_close_position()` | MOYENNE | 1h | `paper_trading/mexc_simulator.py` |

### J3–J7 (07-11 juin) — Observation passive burn-in

- Aucun code à écrire sauf bug critique
- Surveiller Telegram @QuantCrpto_bot :
  - Positions fermées (TP/SL déclenché) ?
  - PnL des trades simulés
  - Comportement du simulateur sur différents régimes
- Gate discrepancy (score 59 passe GATE=OK malgré seuil 60) — investiguer origine

**Critère de passage semaine 2 :** ≥ 15 trades fermés OU 7 jours d'observation

---

## Semaine 2 (J8–J14) — Calibration + Début refactor

### J8–J10 (12-14 juin) — Analyse burn-in intermédiaire

| Tâche | Condition | Durée est. |
|---|---|---|
| Rapport intermédiaire burn-in : PnL/régime, WR, expectancy | N ≥ 15 fermés | 1h |
| Investiguer gate discrepancy (score 59 passe malgré seuil 60) | Toujours présent | 1h |
| Ajuster `MEXC_SIM_CAPITAL` si capital épuisé (positions bloquées longtemps) | Capital < $20 | 30 min |
| MistakeMemory anomalie BTC SELL pnl=-672% — nettoyer ou corriger | Toujours présent | 30 min |

### J11–J14 (15-18 juin) — Préparation ExecutionRouter (si burn-in progresse)

> Seulement si : closed_trades ≥ 30 ET pas de bug critique détecté

| Tâche | Fichier | Durée est. |
|---|---|---|
| Créer `src/domain/trade_event.py` | nouveau | 30 min |
| Créer `src/engine/simulator_adapter.py` | nouveau | 1h |
| Étendre `ExecutionRouter` (modes BACKTEST/PAPER/LIVE) | `src/engine/execution_router.py` | 30 min |
| Migrer `BacktestEngine` → `router.close()` (supprimer `router.sim_engine` direct) | `src/backtest/engine.py` | 1h |

→ Plan détaillé : `docs/EXECUTION_ROUTER_PLAN.md`

---

## Gate de décision à J14

```
Si closed_trades >= 100 ET PF >= 0.8 ET Sharpe >= 0  → BURNIN_CALIBRATION_V3
Si closed_trades >= 100 ET PF < 0.8                   → Analyser causes, NE PAS libérer capital
Si closed_trades < 100 à J14                           → Prolonger observation
```

---

## Backlog permanent (après burn-in validé)

| Item | Référence |
|---|---|
| BURNIN_CALIBRATION_V3 complet | `project_alpha_discovery.md` |
| ExecutionRouter 7 étapes | `docs/EXECUTION_ROUTER_PLAN.md` |
| GovernanceAuditor câblé dans boucle | `docs/NEXT_SESSION_ROADMAP.md` B-01 |
| TraceVerifier câblage | `docs/NEXT_SESSION_ROADMAP.md` B-02 |
| Decision Entropy / TRADING_STALLED | `project_decision_entropy.md` |
| MarketUniverseRanker KPIs dynamiques | `docs/NEXT_SESSION_ROADMAP.md` B-05 |
| Capital réel Phase 2 Spot | `project_p13_plan.md` |

---

## Feux courants

| Composant | Statut |
|---|---|
| Gouvernance G0→G8-E | 🟢 VERT |
| Paper trading MEXC | 🟢 ACTIF ($100) |
| Watchdog systemd | 🟢 ACTIF |
| Burn-in 100 trades | 🟡 EN COURS (0/100 fermés) |
| Self-heal exchange | 🟠 DETTE P2 |
| Spam Telegram | 🟠 À CORRIGER |
| ExecutionRouter refactor | 🔴 GELÉ (post burn-in) |
| Capital réel | 🔴 PAS PRÊT |
