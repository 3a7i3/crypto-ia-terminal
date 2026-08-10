# ROADMAP — Crypto AI Terminal

> Dernière mise à jour : 2026-05-15
> État : P5 livré — Observation Sprint en cours sur VPS

---

## ÉTAT ACTUEL : Phase 5 — Paper Trading Live

### Ce qui est livré et opérationnel

| Couche | Composant | Statut |
|--------|-----------|--------|
| **Marché** | MarketScanner CCXT multi-exchange | ✅ Live |
| **Marché** | MultiTimeframeScanner (1m/15m/4h/1d) | ✅ Live |
| **Marché** | Connecteurs dédiés Binance/MEXC/Hyperliquid | ✅ Live |
| **Marché** | Multi-exchange feed (Binance/Bybit/OKX/MEXC/HL) | ✅ Live |
| **Signal** | LiveSignalEngine (score 0-100, régime, gate) | ✅ Live |
| **Décision** | ConvictionEngine (5 niveaux, sizing) | ✅ Live |
| **Décision** | GlobalRiskGate (7 conditions) | ✅ Live |
| **Décision** | MetaStrategyEngine (personnalité par régime) | ✅ Live |
| **Décision** | NoTradeIntelligence (rejet intelligent) | ✅ Live |
| **Décision** | SelfAwareness (4 niveaux dérive) | ✅ Live |
| **Risque** | HardLimits (MAX_ORDER_USD=200, MAX_DD=20%) | ✅ Frozen |
| **Risque** | PortfolioBrain (8 checks exposition/corrélation) | ✅ Live |
| **Risque** | KillSwitch + SafeMode | ✅ Live |
| **Exécution** | PaperTrading engine (simulation réaliste) | ✅ Live |
| **Exécution** | ExecutionSimulator (slippage/latence/fill) | ✅ Live |
| **Exécution** | OrderValidator (LOT_SIZE, MIN_NOTIONAL) | ✅ Live |
| **Exécution** | RateLimiter (10 ordres/s Binance) | ✅ Live |
| **Audit** | BlackBox JSONL | ✅ Live |
| **Audit** | TradeLogger + PostMortem | ✅ Live |
| **Robustesse** | RobustnessReport (GO/NO-GO, 30 trades) | ✅ Live |
| **Robustesse** | WalkForward (OOS metrics) | ✅ Live |
| **Infrastructure** | VPS GCP (crypto-advisor.service) | ✅ Live |
| **Infrastructure** | API Server FastAPI (crypto-api.service :8000) | ✅ Live |
| **Infrastructure** | Multi-exchange feed (crypto-feed.service) | ✅ Live |
| **Infrastructure** | VPS→PC sync toutes les 30s | ✅ Live |
| **Dashboards** | Dashboard Hub (port 8500) | ✅ Live |
| **Dashboards** | Execution Health / P2 Audit (port 8509) | ✅ Live |
| **Dashboards** | Risk Dashboard (port 8505) | ✅ Live |
| **Dashboards** | Master Dashboard (port 8502) | ✅ Live |
| **Dashboards** | Decision Trace (port 8503) | ✅ Live |
| **Dashboards** | Multi-Exchange Live (port 8510) | ✅ Live |

---

## Architecture de déploiement actuelle

```
VPS GCP (34.171.188.99)
  ├── crypto-advisor.service   advisor_loop.py — cycle 300s
  │     ├── MarketScanner (CCXT Binance testnet)
  │     ├── MultiTimeframeScanner (1m/15m/4h/1d)
  │     ├── LiveSignalEngine → score → gate → conviction
  │     ├── PaperTrading engine
  │     └── BlackBox + audit JSONL
  │
  ├── crypto-api.service       api_server.py :8000
  │     └── /api/raw/* → sert les fichiers locaux
  │
  └── crypto-feed.service      multi_exchange_feed.py
        └── Binance/Bybit/OKX/MEXC/Hyperliquid → 30s

PC local (Windows 11)
  ├── vps_data_sync.py         poll VPS toutes les 30s → fichiers locaux
  ├── Dashboard Hub :8500      lanceur de tous les dashboards
  ├── Execution Health :8509   audit P2 pipeline
  └── [autres dashboards]      lancés à la demande depuis le Hub
```

---

## Arborescence active (modules en production)

```
crypto_ai_terminal/
│
├── ORCHESTRATEURS (racine)
│   ├── advisor_loop.py                ← PRINCIPAL — cycle 300s VPS
│   ├── api_server.py                  ← FastAPI :8000 VPS
│   ├── multi_exchange_feed.py         ← Feed 5 exchanges VPS
│   ├── vps_data_sync.py               ← Sync VPS→PC (30s)
│   └── watchdog_vps.py                ← Watchdog + Telegram alert
│
├── DASHBOARDS (racine)
│   ├── dashboard_hub.py               ← :8500 Hub lanceur
│   ├── dashboard_master.py            ← :8502 Snapshot global
│   ├── dashboard_risk.py              ← :8505 Risk + score
│   ├── dashboard_decision_trace.py    ← :8503 BlackBox decisions
│   ├── dashboard_multi_exchange.py    ← :8510 Multi-exchange live
│   ├── execution_health.py            ← :8509 P2 Audit pipeline
│   ├── dashboard_live.py              ← :8501 Live trading
│   ├── dashboard_positions.py         ← Positions ouvertes
│   ├── dashboard_functions.py         ← Helpers partagés dashboards
│   └── dashboard_compare_multi.py     ← Comparaison multi-sessions
│
├── MODULES SECONDAIRES (racine)
│   ├── evolution_core.py              ← Utilisé par main.py
│   ├── risk_limits.py                 ← Hard limits (frozen)
│   ├── exchange_factory.py            ← Factory exchanges
│   └── main.py                        ← Entry point alternatif
│
├── quant_hedge_ai/                    ← NOYAU IA
│   └── agents/
│       ├── market/
│       │   ├── market_scanner.py
│       │   ├── multi_timeframe_scanner.py
│       │   └── live_signal_engine.py
│       ├── intelligence/
│       │   ├── conviction_engine.py
│       │   ├── meta_strategy_engine.py
│       │   ├── no_trade_intelligence.py
│       │   └── self_awareness.py
│       ├── risk/
│       │   ├── global_risk_gate.py
│       │   ├── portfolio_brain.py
│       │   └── order_sizer.py
│       └── execution/
│           ├── execution_engine.py
│           └── position_manager.py
│
├── market_data/                       ← CONNECTEURS EXCHANGE
│   ├── connectors/
│   │   ├── base.py
│   │   ├── binance.py                 ← WebSocket complet
│   │   ├── mexc.py                    ← REST uniquement
│   │   └── hyperliquid.py             ← Perpétuels USDC
│   ├── metrics/
│   │   ├── flow.py                    ← CVD, sweeps
│   │   └── orderbook.py               ← imbalance, depth
│   ├── models.py
│   └── stream.py                      ← MultiExchangeStream
│
├── exchange_constraints/              ← VALIDATION ORDRES
│   ├── order_validator.py
│   ├── rate_limiter.py
│   └── binance_rules.py
│
├── execution_simulator/               ← SIMULATION RÉALISTE
│   ├── fill_simulator.py
│   ├── slippage.py
│   ├── latency.py
│   └── spread.py
│
├── paper_trading/                     ← PAPER TRADING ENGINE
│   ├── engine.py
│   ├── ledger.py
│   └── sandbox_validator.py
│
├── metrics/                           ← ROBUSTESSE
│   ├── robustness.py                  ← GO/NO-GO
│   ├── oos_metrics.py
│   └── stability_score.py
│
├── walk_forward/                      ← WALK FORWARD
│   ├── engine.py
│   ├── window_splitter.py
│   └── reporter.py
│
├── monitor/                           ← DÉGRADATION
│   └── degradation_tracker.py
│
├── monitoring/                        ← OBSERVABILITÉ
│   ├── logger.py
│   ├── metrics.py
│   └── pipeline_monitor.py
│
├── tracker_system/                    ← SESSIONS & ANALYTICS
│   ├── sessions/
│   │   ├── session_manager.py
│   │   ├── session_analyzer.py
│   │   └── session_validator.py
│   └── analytics/
│       └── score_drift_monitor.py
│
├── core/                              ← MODÈLES PARTAGÉS
│   └── decision_packet.py             ← Modèle DecisionPacket
│
├── dashboard/                         ← HELPERS DASHBOARD
│   └── colors.py                      ← Palette couleurs (lit anara_context/color_system.json)
│
├── anara_context/                     ← DESIGN SYSTEM
│   ├── color_system.json              ← UTILISÉ par dashboard/colors.py
│   └── [17 autres JSON/MD]            ← Documentation système (non-code)
│
├── databases/                         ← DONNÉES RUNTIME (non-git)
│   ├── live_snapshot.json
│   ├── black_box.jsonl
│   ├── cycle_data.jsonl
│   ├── multi_exchange_snapshot.json
│   └── strategy_ranking.json
│
├── logs/                              ← LOGS RUNTIME (non-git)
│   ├── advisor_loop.log
│   ├── trades.jsonl
│   └── execution_audit/audit.jsonl
│
├── deploy/                            ← DÉPLOIEMENT VPS
│   ├── deploy.sh
│   └── setup_vps.sh
│
├── docs/                              ← DOCUMENTATION
│   ├── ROADMAP_V9_V10_V11.md          ← CE FICHIER
│   └── runbooks/
│       ├── incident_degradation.md
│       ├── incident_high_latency.md
│       └── incident_data_leakage.md
│
├── tests/                             ← TESTS INTÉGRATION
│   ├── integration/
│   │   ├── test_p4_pipeline.py
│   │   └── test_backtest_pipeline.py
│   └── [autres tests unitaires]
│
├── project_os/                        ← DIAGNOSTIC (non-prod)
├── frontend/                          ← React app (non connectée)
└── tools/                             ← Outils analyse (non-prod)
```

---

## Débris à nettoyer (P6 — Nettoyage racine)

### Dossiers obsolètes à supprimer

| Dossier | Fichiers | Raison |
|---------|----------|--------|
| `archives/` | 483 | Archives zip et exports d'anciennes phases |
| `results/` | 404 | Résultats simulations legacy |
| `feedback_logs/` | 190 | Logs de feedback UI (Pieuvre era) |
| `reports/` | 229 | Rapports auto-générés legacy |
| `supervision/` | 73 | Module Pieuvre supervision (inactif) |
| `pieuvre/` | 34 | Système Pieuvre (remplacé par couches décision) |
| `strategy_factory/` | 27 | Factory stratégies (non intégré en prod) |
| `tickets/` | 27 | Tickets de bug internes (obsolètes) |
| `governance/` | 12 | Gouvernance Pieuvre (inactif) |
| `observability/` | 12 | Doublon de `monitoring/` |
| `meta_learning/` | 10 | Meta-learning non intégré |
| `quant-hedge-ai/` | 10 | Doublon de `quant_hedge_ai/` (avec tiret) |
| `system/` | 14 | Module système non intégré |
| `mvp/` | 16 | MVP phase 1 (obsolète) |
| `audit/` | 10 | Audit logs legacy |
| `ai_autonomous_loop/` | 6 | Loop autonome (remplacé par advisor_loop) |
| `cache/` | 6 | Cache ML non utilisé |
| `checkpoints/` | 5 | Checkpoints ML (evo_state.pkl à la racine aussi) |
| `sim_summaries/` | 5 | Résumés simulations |
| `k8s/` | 3 | Kubernetes (non déployé) |
| `artifacts/` | 2 | Artefacts CI |
| `terminal_core/` | 9 | Core terminal ancienne version |
| `event_bus/` | 8 | Event bus (Pieuvre era, inactif) |
| `lm_studio/` | 8 | LM Studio (non intégré en prod) |
| `health/` | 6 | Health checks legacy |
| `crypto_quant_v16/` | 9 | Ancienne version v16 |
| `archive_results/` | 10 | Résultats archivés |

### Fichiers Python obsolètes à la racine

```
# Anciens launchers remplacés par LAUNCH_DASHBOARDS.bat
launch_all.bat, launch_all.ps1, launch_all_visible.bat, launch_pieuvre.py
launch_alert_dashboard.bat, launch_botdoctor_api.bat, launch_botdoctor_dashboard.bat
launch_dash_app.bat, launch_dashboard_*.bat, launch_equity_curve_streamlit.bat
launch_evolution_*.bat, launch_feedback_dashboard.bat, launch_monitoring_api.bat
launch_orchestrator_api.bat, launch_panel_overview.bat, launch_quant_*.bat
launch_tracker_scheduler.ps1, launch_v12_dashboard.bat, start_all.bat, stop_all.bat

# Scripts de simulation legacy
run_strategy_factory.py, run_strategy_factory_batch.py, run_strategy_factory_large.py
run_multi_simulations.py, automate_pipeline.py, automate_pipeline_task.ps1

# Scripts de génération de rapports
generate_*.py, export_*.py, panel_*.py, notify_*.py, send_orchestration_notification.py

# Scripts d'installation/setup obsolètes
install_all.ps1, install_all.sh, install_and_test.ps1, setup_quant_matrix_venv.ps1
reset_quant_matrix_venv.ps1, build_docs.ps1, build_docs.sh

# Rapports MD à la racine (devraient être dans docs/ ou supprimés)
P0_IMPLEMENTATION_REPORT.md, P1_COMPLETE_REPORT.md, P2_COMPLETE_REPORT.md
ARCHITECTURE_NOTES.md, CLEANUP_REPORT_FINAL.md, CODE_VALIDATION_REPORT.md
DEDUPLICATION_REPORT.md, INTEGRATION_REPORT.md, VALIDATION_COMPLETE.md
DOCUMENTATION_*.md, FAQ_*.md, TUTORIEL_*.md, GUIDE_*.md, QUICKSTART.md, QUICK_START.md
ACTION_PLAN_CHECKLIST.md, IMPLEMENTATION_3_PRIORITIES.md, INVENTAIRE_2026-04-25.md

# Fichiers orphelins
evo_state.pkl, strategy_lab.sqlite, evolution_params.csv, test.csv
batch_configs.json, alpha_vault_*.json, crypto_ai_terminal.zip, export_codebase_mars2026.zip
test_heatmap2d.png, test_matplotlib3d.png, test_plotly3d.png, test_plotly3d.svg
```

---

## Zones fragiles / à surveiller

### Critique — À corriger rapidement

| Zone | Problème | Impact |
|------|----------|--------|
| `advisor_loop.py` | Cycle de 300s — si un exchange timeout, le cycle entier ralentit | Signal stale |
| `live_snapshot.json` | Écrit à chaque cycle, pas de lock — corruption possible si restart pendant écriture | Dashboard stale |
| `walk_forward/` + `quant_hedge_ai/agents/quant/walk_forward.py` | Deux implémentations parallèles — risque d'incohérence | Tests faux positifs |

### Moyen — À planifier

| Zone | Problème | Impact |
|------|----------|--------|
| `evolution_core.py` (racine) | Module à la racine au lieu de `quant_hedge_ai/` — cassable si renommé | main.py casse |
| `market_data/` Bybit/OKX | CCXT uniquement, pas de WebSocket dédié | Latence données |
| `execution_health.py` | Attend `logs/execution_audit/audit.jsonl` créé au premier ordre seulement | Dashboard vide en sideways |
| Score 42/100 constant | Sideways depuis >24h — normal mais log répétitif | Bruit logs |
| ~1200 fichiers débris | Racine polluée — confusion sur quels fichiers sont actifs | Maintenabilité |

### Faible — Inoffensif

| Zone | Problème | Impact |
|------|----------|--------|
| `project_os/` | Module de diagnostic non intégré en prod | Aucun |
| `frontend/` (React) | Frontend React non connecté au système Python | Aucun |
| `docs/runbooks/` | 3 runbooks créés, jamais testés en vrai incident | Potentiellement inexacts |

---

## Roadmap prochaines phases

### P5 — Observation Sprint (en cours, 7-14 jours)
**Objectif :** Accumuler 30 trades paper → valider GO/NO-GO robustesse

```
✅ Bot tourne sur VPS (cycle 300s)
✅ Dashboards connectés via API
✅ Multi-exchange feed actif
✅ Git propre — node_modules supprimé
⏳ En attente : 30 trades pour GO/NO-GO dashboard (marché sideways, 0/30 actuellement)
⏳ Observer : fills, stale states, websocket reconnects, OOS drift
```

### P6 — Nettoyage + Stabilisation (après P5 ou en parallèle)
**Objectif :** Codebase propre, données stables

```
Nettoyage (1 jour) :
  [ ] Supprimer les 28 dossiers obsolètes (~1800 fichiers)
  [ ] Supprimer les ~60 fichiers Python/bat obsolètes à la racine
  [ ] Supprimer les ~25 fichiers MD de rapport à la racine
  [ ] Déplacer evolution_core.py dans quant_hedge_ai/

Stabilisation données :
  [ ] Lock fichier live_snapshot.json (éviter corruption)
  [ ] Unifier les 2 walk_forward (racine + quant_hedge_ai)
  [ ] Health endpoint VPS → dashboard status services
  [ ] Connecteur Bybit dédié (WebSocket)
  [ ] Connecteur OKX dédié
```

### P7 — Live Capital (conditionnel à P5 GO)
**Objectif :** Passer du paper au capital réel contrôlé

```
Pré-requis GO/NO-GO :
  [ ] ≥ 30 trades paper avec robustness GO
  [ ] Profit factor ≥ 1.5 sur 50 trades
  [ ] Drawdown normalisé < 5%
  [ ] avg_win/avg_loss ≥ 1.5
  [ ] 0 incident de corruption de données

Actions :
  [ ] Créer clés API Binance (Read + Futures Trading)
  [ ] Activer LIVE_MODE=true dans .env VPS
  [ ] Capital initial : ≤ $500 (hard limit MIN_CAPITAL_USD)
  [ ] Monitoring 24h/j via Telegram watchdog
```

---

## Problèmes silencieux à surveiller

```
1. Score 42/100 constant en sideways
   → Normal, mais vérifier que le signal change quand le régime change
   → Si score reste 42 pendant 24h, vérifier LSE + régime detector

2. Execution audit vide
   → logs/execution_audit/audit.jsonl créé seulement au premier ordre exécuté
   → En sideways, ce fichier n'existe pas = dashboard Execution Health vide
   → NORMAL en phase d'observation

3. Sync 8/8 fichiers
   → multi_exchange_snapshot.json inclus depuis P5
   → Vérifier que le sync affiche bien 8/8 après redémarrage du vps_data_sync

4. walk_forward en doublon
   → Deux modules avec des APIs différentes
   → Si un test passe mais pas l'autre, chercher lequel est appelé

5. evolution_core.py à la racine
   → main.py l'importe directement
   → Si quelqu'un déplace le fichier, main.py casse sans erreur évidente

6. ~1200 fichiers débris non supprimés
   → Aucun impact runtime mais augmente le risque de modifier le mauvais fichier
   → Nettoyage planifié en P6
```
