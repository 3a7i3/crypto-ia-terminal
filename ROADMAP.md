# ROADMAP — Crypto AI Terminal

> Dernière mise à jour : 2026-06-14
> Statut global : **P10 FERMÉ** → **Phase burn-in paper trading (MEXC)**

---

## Architecture cible — 7 couches cybernétiques

```
1. PERCEPTION           → sensors, classifieurs, analyseurs MTF
2. MÉMOIRE              → stockage contextuel, MistakeMemory, RegretEngine
3. SYSTÈME NERVEUX AUTONOME → RiskGovernor, états défensifs
4. STRATEGY ALLOCATOR   → allocation dynamique, weighting contextuel
5. MOTEUR D'EXÉCUTION   → fills, latence, ordres, shadow engine
6. BOUCLE DE FEEDBACK   → regret → threshold, adaptation fermée
7. MÉTA-GOUVERNANCE     → surveillance des couches, détection de dérive
```

---

## RÉCAP P1-P13 (état 2026-06-14)

| Phase | Livré | Statut | Date |
|-------|-------|--------|------|
| P1 | Foundation : LiveSignalEngine, MarketScanner, ExchangeMonitor, Telegram | ✅ FERMÉ | 2026-04 |
| P2 | Operational : data pipeline, rate limiter, simulator, audit | ✅ FERMÉ | 2026-05-13 |
| P3 | Decision Intelligence : SelfAwareness, NoTrade, Conviction, DecisionQuality | ✅ FERMÉ | 2026-05 |
| P4 | Portfolio Brain : 8 checks, Kelly+EV+Vol sizing, GlobalRiskGate | ✅ FERMÉ | 2026-05 |
| P5 | Paper Trading : engine, ledger, shadow log, 30+ trades validés | ✅ FERMÉ | 2026-05-19 |
| P6 | Adaptive Core : RegimeClassifier v2, AdaptiveThreshold PID, RegretLoop, ATR SL | ✅ FERMÉ | 2026-05 |
| P7 | Autonomous Regulation : RiskGovernor, CapitalThrottle, CircuitBreaker | ✅ FERMÉ | 2026-05 |
| P8 | Dynamic Intelligence : StrategyAllocator, ProbationSystem, CorrelationMonitor | ✅ FERMÉ | 2026-05 |
| P9 | Meta Governance : HealthMonitor, BehavioralDrift, AnomalyGovernance — 64/64 tests | ✅ FERMÉ | 2026-05-26 |
| P10-A | Cold Start Protocol : 9 modules, 112 tests, HMAC signing, 3 régimes | ✅ FERMÉ | 2026-05 |
| P10-F | Architecture 3 états RUNNING/DEGRADED/HALTED, SystemController câblé | ✅ FERMÉ | 2026-06-12 |
| P11-B | Restart Safety : 38 tests crash/restart zero-drift, WarmupSM, PositionReconciler | ✅ FERMÉ | 2026-05 |
| CFG-P2-01 | config/settings.py Pydantic BaseSettings SSoT — 21 tests | ✅ LIVRÉ | 2026-06-13 |
| Gouvernance | G0→G8-E certifiés, hash chain, GovernanceAuditor S1/S2/S3 | ✅ FERMÉ | 2026-06 |
| MEXC-only | Consolidation exchange : Binance archivé, 28 fichiers, 1816/1816 tests | ✅ LIVRÉ | 2026-06-13 |

12 couches décisionnelles actives. VPS GCP 34.171.188.99 — systemd crypto-advisor RUNNING.

---

## État actuel — Burn-in paper trading (ALPHA_DISCOVERY_100)

**Règle souveraine** : GEL TOTAL architecture tant que < 100 trades paper fermés ET C5==False.
Aucun tuning de GATE_MIN_SCORE_OVERRIDE, PB_MIN_POSITION_USD, ni de paramètre de trading.

### Baseline BurnIn V3 (2026-06-12)

| KPI | Valeur |
|-----|--------|
| Signaux évalués | 2332 sur 447h |
| Pass rate gate | 51.2% (≈2.7 signaux/h autorisés) |
| Rejets RiskGate | 1138 |
| Trades paper fermés | **0** (bloqueur : `PAPER_TRADING_ENABLED` absent .env VPS) |

**Bloqueur immédiat** : déployer commit `bcd841b` sur VPS + ajouter `PAPER_TRADING_ENABLED=true` dans `.env`.
ETA 100 trades : ~37h après activation.

---

## Migration Architecture V2 (P1 canonique)

Objectif : réduire de 89 dossiers → <40, pipeline dict-free, SSoT par verticale.

| Verticale | Canonique | Runtime câblé | Tests intégration | Legacy |
|-----------|-----------|---------------|-------------------|--------|
| Decision Layer | ✅ | ✅ | ✅ 18 tests (DL-01→DL-05) | ⏳ renommage différé |
| Event Bus | ✅ | ⏳ | ⏳ | ⏳ |
| Execution Engine | ✅ | ✅ | ⏳ | ⏳ |
| Kill Switch | ✅ | ✅ | ⏳ | ⏳ |
| Regime Detector | ✅ | ✅ | ✅ | ⏳ |

Prochaine verticale : **Event Bus** (`src/events/event_bus.py` → `event_bus/bus.py`).

---

## Dettes techniques actives

### CFG-P2 — Migration config SSoT (non bloquant burn-in)

| ID | Description | Statut |
|----|-------------|--------|
| CFG-P2-02 | Câbler execution_engine.py → ExecutionSettings | ⏳ |
| CFG-P2-03 | Câbler global_risk_gate.py → RiskSettings | ⏳ |
| CFG-P2-04 | Câbler advisor_loop.py → TelegramSettings.enabled | ⏳ |
| CFG-P2-05 | Supprimer config/telegram_config.json (obsolète) | ⏳ |
| CFG-P2-06 | Migrer quant_hedge_ai/runtime_config.py → PortfolioSettings | ⏳ |

### Architecture V2 P1 — Tests intégration restants

- Event Bus : runtime câblage + tests intégration
- Execution Engine : tests intégration
- Kill Switch : tests intégration
- Decision Layer : renommages legacy différés

---

## Gate live trading — Ce qui manque

Le système est architecturalement validé. La progression vers le trading réel suit 3 phases disciplinées.

### Phase 1 — API réelles en lecture seule (prochaine étape)

**Pré-requis à valider avant Phase 1 :**

- [ ] `PAPER_TRADING_ENABLED=true` déployé sur VPS + commit `bcd841b`
- [ ] 100 trades paper fermés accumulés (ETA ~37h après activation)
- [ ] C5 == True (Profit Factor > 1.0 sur la fenêtre burn-in)
- [ ] BURNIN_CALIBRATION_V3 exécuté : score floor optimal, symbol whitelist, PF/expectancy par régime
- [ ] Zéro position contradictoire observée sur 7+ jours de run stable

**Action Phase 1 :**
- Connexion MEXC API réelle en lecture seule (sans permission trading)
- Validation : carnet, positions, portefeuille, marchés — infra sur données réelles

### Phase 2 — Spot réel petit capital (50-100 USD)

**Pré-requis supplémentaires :**
- [ ] Phase 1 stable ≥ 7 jours sans interruption non planifiée
- [ ] PortfolioBrain validé sur données live (pas seulement paper)
- [ ] P10-F RUNNING stable (pas de basculement DEGRADED fréquent)
- [ ] RegretEngine données réelles : missed_win_rate et patterns confirmés
- [ ] CFG-P2 dettes comblées (config SSoT sur tous les modules runtime)
- [ ] Architecture V2 migration complète (Event Bus + tests intégration)

**Symboles Phase 2 :** BTC/USDT, ETH/USDT, SOL/USDT, XRP/USDT — sans levier.

### Phase 3 — Futures réels (horizon lointain)

- Seulement après Phase 2 stable plusieurs semaines
- Levier fixe faible (×2 ou ×3) — jamais dynamique au départ
- Ne pas discuter avant Phase 2 validée

---

## Priorités immédiates (ordre)

1. **Déployer VPS** : `git reset --hard origin/main` + ajouter `PAPER_TRADING_ENABLED=true` + `MARKET_SCANNER_EXCHANGE=mexc` dans `.env`
2. **Surveiller** : atteindre 100 trades paper fermés, vérifier C5
3. **Exécuter BURNIN_CALIBRATION_V3** (`scripts/burnin_calibration_v3.py`) après 100 trades
4. **CFG-P2-02→06** : câbler modules runtime sur config SSoT
5. **Event Bus** : migration + tests intégration (prochaine verticale P1)

---

## Invariants permanents

- Permissions Spot et Futures séparées sur l'exchange
- Ne jamais activer permission "Retrait" pour un bot
- Levier dynamique interdit avant Phase 3 et validation complète
- Aucun tuning paramètre trading avant 100 trades ET C5==True
- GEL architecture pendant burn-in

---

## Fichiers de pilotage

| Fichier | Rôle |
|---------|------|
| `ROADMAP.md` | Vision globale et état |
| `core/advisor_loop.py` | Point d'entrée principal |
| `tests/root/test_boot_system.py` | Validation boot (122/122) |
| `scripts/burnin_calibration_v3.py` | Calibration post-100 trades |
| `CANONICAL_COMPONENTS.md` | Tableau migration V2 |
| `scripts/deploy_vps.sh` | Auto-deploy git → VPS |
