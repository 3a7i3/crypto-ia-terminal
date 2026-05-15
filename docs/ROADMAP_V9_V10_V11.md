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

## Zones fragiles / à surveiller (audit 2026-05-15)

### 🔴 Critique — À corriger rapidement

| Zone | Problème | Impact |
|------|----------|--------|
| `advisor_loop.py` | Cycle de 300s — si un exchange timeout, le cycle entier ralentit | Signal stale |
| `live_snapshot.json` | Écrit à chaque cycle, pas de lock — corruption possible si restart pendant écriture | Dashboard stale |
| `walk_forward/` + `quant_hedge_ai/agents/quant/walk_forward.py` | Deux implémentations parallèles — risque d'incohérence | Tests faux positifs |
| `databases/` exclu du .gitignore | Les fichiers JSONL/JSON live ne sont pas dans git (normal), mais le VPS et le PC ont des états différents | Divergence silencieuse |

### 🟡 Moyen — À planifier

| Zone | Problème | Impact |
|------|----------|--------|
| `evolution_core.py` (racine) | Module à la racine au lieu de `quant_hedge_ai/` — cassable si renommé | main.py casse |
| `anara_context/` | 15 fichiers JSON de documentation, seul `color_system.json` est utilisé | Confusion |
| `market_data/` connecteurs | Bybit/OKX/Kraken : CCXT uniquement, pas de WebSocket dédié | Latence données |
| `execution_health.py` | Attend `logs/execution_audit/audit.jsonl` qui n'existe que quand un ordre passe le gate | Dashboard vide en sideways |
| Score 42/100 constant | Le marché est sideways depuis 24h — système bloque correctement mais log répétitif | Bruit dans les logs |

### 🟢 Faible — Inoffensif

| Zone | Problème | Impact |
|------|----------|--------|
| `project_os/` | Module de diagnostic non intégré en prod | Aucun |
| `frontend/` (React) | Frontend React non connecté au système Python | Aucun |
| `docs/runbooks/` | 3 runbooks créés, jamais testés en vrai incident | Potentiellement inexacts |
| `tune.py` | Script de tuning standalone, non intégré | Aucun |

---

## Arborescence actuelle (modules actifs)

```
crypto_ai_terminal/
│
├── advisor_loop.py                  ← ORCHESTRATEUR PRINCIPAL (cycle 300s)
├── multi_exchange_feed.py           ← Feed prix live 5 exchanges
├── vps_data_sync.py                 ← Sync VPS→PC (30s)
├── api_server.py                    ← FastAPI :8000
├── watchdog_vps.py                  ← Watchdog + Telegram alert
│
├── quant_hedge_ai/                  ← NOYAU IA
│   └── agents/
│       ├── market/
│       │   ├── market_scanner.py        score/signal
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
├── market_data/                     ← CONNECTEURS EXCHANGE
│   ├── connectors/
│   │   ├── base.py
│   │   ├── binance.py               ← WebSocket complet
│   │   ├── mexc.py                  ← REST uniquement
│   │   └── hyperliquid.py           ← Perpétuels USDC
│   ├── metrics/
│   │   ├── flow.py                  ← CVD, sweeps
│   │   └── orderbook.py             ← imbalance, depth
│   ├── models.py                    ← NormalizedTrade/OrderBook/Candle
│   └── stream.py                    ← MultiExchangeStream
│
├── exchange_constraints/            ← VALIDATION ORDRES
│   ├── order_validator.py           ← LOT_SIZE, MIN_NOTIONAL
│   ├── rate_limiter.py              ← 10 ordres/s
│   └── binance_rules.py
│
├── execution_simulator/             ← SIMULATION RÉALISTE
│   ├── fill_simulator.py
│   ├── slippage.py
│   ├── latency.py
│   └── spread.py
│
├── paper_trading/                   ← PAPER TRADING ENGINE
│   ├── engine.py
│   ├── ledger.py
│   └── sandbox_validator.py
│
├── risk_limits.py                   ← HARD LIMITS (frozen)
│
├── metrics/                         ← ROBUSTESSE
│   ├── robustness.py                ← GO/NO-GO
│   ├── oos_metrics.py               ← Out-of-sample
│   └── stability_score.py
│
├── walk_forward/                    ← WALK FORWARD (tests intégration)
│   ├── engine.py
│   ├── window_splitter.py
│   └── reporter.py
│
├── monitor/                         ← DÉGRADATION
│   └── degradation_tracker.py
│
├── monitoring/                      ← OBSERVABILITÉ
│   ├── logger.py
│   ├── metrics.py
│   └── pipeline_monitor.py
│
├── tracker_system/                  ← SESSIONS & ANALYTICS
│   ├── sessions/
│   │   ├── session_manager.py
│   │   ├── session_analyzer.py
│   │   └── session_validator.py
│   └── analytics/
│       └── score_drift_monitor.py   ← Alerte dérive signal
│
├── databases/                       ← DONNÉES RUNTIME (non-git)
│   ├── live_snapshot.json           ← Snapshot cycle courant
│   ├── black_box.jsonl              ← Toutes les décisions
│   ├── cycle_data.jsonl             ← Historique cycles
│   ├── multi_exchange_snapshot.json ← Prix 5 exchanges
│   └── strategy_ranking.json
│
├── logs/                            ← LOGS RUNTIME (non-git)
│   ├── advisor_loop.log
│   ├── trades.jsonl
│   └── execution_audit/audit.jsonl  ← Créé au premier ordre
│
├── dashboards (Streamlit)
│   ├── dashboard_hub.py             :8500 ← Hub launcher
│   ├── execution_health.py          :8509 ← P2 Audit
│   ├── dashboard_master.py          :8502
│   ├── dashboard_risk.py            :8505
│   ├── dashboard_decision_trace.py  :8503
│   ├── dashboard_multi_exchange.py  :8510 ← Multi-exchange live
│   └── dashboard_live.py            :8501
│
├── deploy/                          ← DÉPLOIEMENT VPS
│   ├── deploy.sh
│   └── setup_vps.sh
│
└── docs/
    ├── ROADMAP_V9_V10_V11.md        ← CE FICHIER
    └── runbooks/
        ├── incident_degradation.md
        ├── incident_high_latency.md
        └── incident_data_leakage.md
```

---

## Modules secondaires (non critiques, garder)

```
evolution_core.py            ← Utilisé par main.py + run_multi_simulations.py
project_os/                  ← Outils de diagnostic (audit manuel)
anara_context/               ← color_system.json utilisé par dashboard/colors.py
                               Le reste est documentation système (garder)
frontend/                    ← React app non connectée (futur dashboard web)
walk_forward/                ← Utilisé par tests d'intégration P4
```

---

## Roadmap prochaines phases

### P5 — Observation Sprint (en cours, 7-14 jours)
**Objectif :** Accumuler 30 trades paper → valider GO/NO-GO robustesse

```
✅ Bot tourne sur VPS (cycle 300s)
✅ Dashboards connectés via API
✅ Multi-exchange feed actif
⏳ En attente : 30 trades pour GO/NO-GO dashboard
⏳ Observer : fills, stale states, websocket reconnects, OOS drift
```

### P6 — Stabilisation données live (après P5)
**Objectif :** Améliorer qualité et stabilité des données de marché

```
[ ] Connecteur Bybit dédié (WebSocket) — actuellement CCXT uniquement
[ ] Connecteur OKX dédié
[ ] Lock fichier live_snapshot.json (éviter corruption)
[ ] Health endpoint VPS → dashboard status services
[ ] Unifier les 2 walk_forward (racine + quant_hedge_ai)
[ ] Déplacer evolution_core.py dans quant_hedge_ai/
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

3. Sync 7→8 fichiers
   → multi_exchange_snapshot.json ajouté aujourd'hui
   → Vérifier que le sync affiche bien 8/8 après redémarrage du vps_data_sync

4. walk_forward en doublon
   → deux modules avec des APIs différentes
   → Si un test passe mais pas l'autre, chercher lequel est appelé

5. evolution_core.py à la racine
   → main.py l'importe directement
   → Si quelqu'un déplace le fichier, main.py casse sans erreur évidente
```
