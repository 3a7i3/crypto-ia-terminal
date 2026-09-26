# ROADMAP — Crypto AI Terminal (document historique)

> ⚠️ **Ce fichier n'est plus une source de vérité opérationnelle.**
>
> Révision forensique : 2026-09-26.
>
> L'autorité de feuille de route courante est
> **[#148 — MASTER ROADMAP](https://github.com/3a7i3/crypto-ia-terminal/issues/148)**.
> La mission active est pointée par `CURRENT_TASK.md`.
> Les règles invariantes et les frontières d'autorité sont dans `CLAUDE.md`.
>
> Ce document est conservé comme **vue d'ensemble historique** des phases
> P1-P13 et de la migration d'architecture. Tout énoncé d'« état courant »
> qu'il contenait a été daté et archivé ci-dessous.

---

## Navigation canonique

```
#148  MASTER ROADMAP  ← autorité de priorisation
  │
  ├─ F00 certifié — F00_FINAL_SCIENTIFIC_EXPERIMENT_CERTIFIED
  │    époque F00-EPOCH-01-20260920T084335Z
  │
  └─ Research Infrastructure (#237 RL-ARCH-00)
       ├─ #238  RL-DATA-01      ✅ SOURCE CERTIFIED
       ├─ #239  RL-REPLAY-01    ✅ SOURCE CERTIFIED / CLOSED
       ├─ #248  RL-DIAG-01      ✅ SOURCE CERTIFIED / CLOSED
       ├─ #240  RL-CANDIDATE-01 🟡 ACTIVE  (PR #264 draft, #265 miroir CI)
       ├─ #241  WEB-RL-01       ⏳
       └─ #242  RL-BURNIN-01    ⏳
```

| Document | Rôle |
|---|---|
| [#148](https://github.com/3a7i3/crypto-ia-terminal/issues/148) | feuille de route et priorités courantes |
| `CLAUDE.md` | règles constitutionnelles + frontières d'autorité PAPER/PPL/Research |
| `CURRENT_TASK.md` | pointeur vers la mission GitHub active |
| `BUGS.md` | dette technique suivie |
| `ROADMAP.md` (ce fichier) | historique des phases livrées |

---

## ⚠️ Énoncés archivés — ne plus appliquer

Les sections d'état suivantes, présentes dans les révisions antérieures de ce
fichier, sont **périmées** et remplacées par #148 :

| Énoncé archivé (daté 2026-07-17 et antérieur) | Statut | Remplacé par |
|---|---|---|
| « Statut global : Époque V4 active — burn-in paper sur univers épinglé de 135 paires » | **SUPERSEDED** | époque F00 `F00-EPOCH-01-20260920T084335Z` ; burn-in ⛔ NOT AUTHORIZED (#148) |
| « État actuel — Burn-in paper trading (ALPHA_DISCOVERY_100) », baseline BurnIn V3 | **SUPERSEDED** | F00 certifié, population PPL 27 événements (#148) |
| « Prochaines étapes (ordre décidé par l'opérateur 2026-07-17) » : scanner top-K, migration Hetzner, suivi V4, ADR-0014 | **STALE** | priorités de #148 |
| « Priorités immédiates » : surveiller burn-in → 100 trades → BURNIN_CALIBRATION_V3 → prelive_gate | **SUPERSEDED** | chaîne `#240 → #241 → #242` |
| « Gate live trading — Phase 1 / Phase 2 / Phase 3 » | **SUPERSEDED** | ordre canonique `PAPER → TESTNET → capital minuscule` (#148 PHASE F, §36-37) ; TESTNET/LIVE ⛔ NOT AUTHORIZED |
| « VPS GCP 34.171.188.99 — PID 49742 RUNNING » et commandes ssh associées | **STALE** | infrastructure et PID non vérifiables depuis ce document |
| « Bloqueur levé (2026-06-15)… ETA 100 trades ~37h » | **SUPERSEDED** | F00 a produit 13 OPEN / 13 CLOSE, puis certification finale |

L'univers de 135 paires est conservé ci-dessous comme jalon ADR-0017. État
certifié le plus récent : **135 configurés, 125 valides, 10 rejetés**, avec
dérive runtime à remédier (#148 § OPS-C / MARKET-UNIVERSE-01).

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

## RÉCAP P1-P13 (état figé au 2026-06-14)

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
| Telegram 3-bots | portfolio_bot PnL simplifié, QuantCrpto_bot 3-niveaux 100+ paires, Intel bot 6h NL | ✅ LIVRÉ | 2026-06-15 |
| Infra observabilité | dataset_integrity_gate, runtime_validator 8 checks, prelive_gate 6 gates | ✅ LIVRÉ | 2026-06-15 |

---

## Jalons d'époque et d'univers (historique ADR)

| Jalon | Contenu |
|---|---|
| ADR-0011 / 0012 | bornes `CLEAN_DATA_SINCE` v1→v3, contamination SEC-01 |
| ADR-0015 | univers épinglé burn-in |
| ADR-0016 | observation marché MEXC complet (~3224 paires spot+perp, 15 min), radar R1, horizons R2 |
| ADR-0017 | époque V4 + paliers ; palier 1 = 135 paires activé le 2026-07-17 ; V3 (28 paires, N=49) archivée |
| ADR-0018 | séparation capital scientifique / observation exchange |
| ADR-0019 → 0021 | autorisation d'ordre pré-réseau, soumission déterministe idempotente, provenance domaine d'exécution |

Outils de mesure associés : `tools/throughput_probe.py`,
`tools/scan_load_probe.py`, runbook `docs/runbook-restauration-vps.md`.

---

## Migration Architecture V2 (P1 canonique) — état 2026-06

Objectif : réduire de 89 dossiers → <40, pipeline dict-free, SSoT par verticale.

| Verticale | Canonique | Runtime câblé | Tests intégration | Legacy |
|-----------|-----------|---------------|-------------------|--------|
| Decision Layer | ✅ | ✅ | ✅ 18 tests (DL-01→DL-05) | ⏳ renommage différé |
| Event Bus | ✅ | ⏳ | ⏳ | ⏳ |
| Execution Engine | ✅ | ✅ | ⏳ | ⏳ |
| Kill Switch | ✅ | ✅ | ⏳ | ⏳ |
| Regime Detector | ✅ | ✅ | ✅ | ⏳ |

## Dettes techniques historiques — CFG-P2

| ID | Description | Statut |
|----|-------------|--------|
| CFG-P2-02 | Câbler execution_engine.py → ExecutionSettings | ⏳ |
| CFG-P2-03 | Câbler global_risk_gate.py → RiskSettings | ⏳ |
| CFG-P2-04 | Câbler advisor_loop.py → TelegramSettings.enabled | ⏳ |
| CFG-P2-05 | Supprimer config/telegram_config.json (obsolète) | ⏳ |
| CFG-P2-06 | Migrer quant_hedge_ai/runtime_config.py → PortfolioSettings | ⏳ |

Ces dettes n'ont pas été revalidées lors de la revue du 2026-09-26 ; leur
statut `⏳` est repris tel quel de la révision de juin 2026.

---

## Invariants permanents

- Permissions Spot et Futures séparées sur l'exchange
- Ne jamais activer permission « Retrait » pour un bot
- Levier dynamique interdit avant validation complète
- Aucun tuning de paramètre trading hors mission explicitement dédiée
- Gel architectural pendant toute expérience active

Ces invariants sont repris et font foi dans `CLAUDE.md`.

---

## Fichiers de pilotage

| Fichier | Rôle |
|---------|------|
| `core/advisor_loop.py` | point d'entrée principal |
| `tests/root/test_boot_system.py` | validation boot |
| `scripts/prelive_gate.py` | gate validation pré-live |
| `scripts/runtime_validator.py` | certification pré-démarrage |
| `CANONICAL_COMPONENTS.md` | tableau migration V2 |
| `scripts/deploy_vps.sh` | déploiement délibéré (jamais automatique) |
