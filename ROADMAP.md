# ROADMAP — Crypto AI Terminal

> Dernière mise à jour : 2026-05-20
> Statut global : **P6 FERMÉ** → P7 Autonomous Regulation à démarrer

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

Chaque phase ferme une boucle avant d'en ouvrir une nouvelle.

---

## RÉCAP P1-P5 (validé)

| Phase | Livré | Date |
|-------|-------|------|
| P1 | Foundation : LiveSignalEngine, MarketScanner, ExchangeMonitor, Telegram | 2026-04 |
| P2 | Operational : data pipeline, rate limiter, simulator, audit — gelé | 2026-05-13 |
| P3 | Decision Intelligence : SelfAwareness, NoTrade, Conviction, DecisionQuality | 2026-05 |
| P4 | Portfolio Brain : 8 checks, Kelly+EV+Vol sizing, GlobalRiskGate | 2026-05 |
| P5 | Paper Trading : engine, ledger, shadow log, 30+ trades validés | 2026-05-19 |
| Fix | VPS auto-deploy, Kraken testnet, TIME_STOP, TP/SL dynamique, reconciler | 2026-05-19 |

12 couches décisionnelles actives, 11 dashboards Streamlit, auto-deploy git→VPS.

---

## P6 — Adaptive Core

**Objectif** : fermer la première boucle de rétroaction (regret → threshold) et stabiliser le comportement en régime variable.

### Composants

**1. Market Regime Classifier v2 — avec hystérésis**
- États : `TREND_BULL`, `TREND_BEAR`, `SIDEWAYS`, `HIGH_VOL`, `CHOPPY`, `UNKNOWN`
- Transition validée après N cycles consécutifs (N=3-6 selon TF)
- Confirmation orthogonale : 2 familles indépendantes requises
  - Structure de tendance (ADX, EMA slope, MACD)
  - Structure de volatilité (ATR, Bollinger width)
  - Structure d'épuisement (RSI MTF, distance VWAP, volume exhaustion)
- Sortie : `RegimePacket(regime, confidence, duration_cycles, transition_from)`

**2. Adaptive Threshold Engine — contrôle PID**
```
adaptive_threshold = base_threshold(70)
                   + regime_adjustment(regime)
                   + EWMA(regret_delta, decay=0.85)
                   + damping_term(max ±1/cycle)
```
- `regime_adjustment` : SIDEWAYS → -4, TREND → +2, HIGH_VOL → +3, CHOPPY → -2
- PID : P=réaction immédiate, I=EWMA erreurs passées, D=damping anti-oscillation

**3. Regret Feedback Loop — fermée et décisionnelle**
- `RegretEngine.get_threshold_delta` : -2, -1, 0, +1
- Activation : `missed_wins > good_refusals * 1.2` ET `avg_regret > 0.6`
- Anti-oscillation : delta ne change pas de signe plus d'1 fois / 3 cycles
- Boucle complète : `RegretEngine → GlobalRiskGate.apply_regret_delta → scoring → exécution → mesure → cycle suivant`

**4. ATR Adaptive Stop-Loss**
- `sl_pct = max(atr_pct * sl_factor, min_sl=0.008)`
- `sl_factor` par régime : SIDEWAYS=1.5, TREND=2.0, HIGH_VOL=2.5
- `tp_pct = sl_pct * risk_reward_min(2.0)`
- Fallback SL fixe si `atr_pct` absent

**5. Regime Transition Smoother**
- Rampe linéaire sur 3-5 cycles lors d'un changement de régime
- `param(t) = old + (new - old) * min(t / ramp_duration, 1)`
- Rampe suspendue si nouveau changement pendant la transition

**6. Activity Tracker — version décisionnelle**
- Si `inactivity_ratio > 0.85` pendant 20+ cycles ET RegretEngine signale des opportunités :
  - Déclencher `REGIME_MISMATCH`
  - Forcer recalcul du classifieur
  - Réduire threshold d'un cran supplémentaire

### Câblage advisor_loop.py (~15 lignes)
```python
activity_tracker.log_cycle(...)
regime = classifier.classify(market_data)
delta = regret_engine.get_threshold_delta(regime)
gate.apply_regret_delta(delta)
effective_threshold = gate.get_effective_min_score(regime)
meta_strategy_engine.select(signals, threshold=effective_threshold, atr_pct=atr)
```

### Critères de succès P6
- [x] NEAR à 69/100 passe le gate en régime SIDEWAYS (REGIME_SIDEWAYS_MIN_SCORE=40)
- [x] Regret élevé → ATE delta [-5,0] progressif (≤1pt/cycle) + REGIME_MISMATCH -1 / 15 cycles si gelé >30 cycles
- [x] Aucune oscillation threshold > 3 points entre 2 cycles consécutifs (damping_max=1.0/cycle)
- [x] Transitions de régime confirmées après 3 cycles consécutifs identiques (_REGIME_STABILITY=3)

---

## P7 — Autonomous Regulation (RiskGovernor)

**Objectif** : couche de protection autonome — états de risque, modes dégradés, survie du système.

### Composants

**1. RiskGovernor — machine à états**
```
NORMAL     → activité standard, threshold adaptatif actif
DEFENSIVE  → size 50%, SL élargi, pas de trades en HIGH_VOL
RISK_OFF   → pas de nouveaux trades, liquidation progressive
RECOVERY   → size 25%, threshold +3, haute conviction seulement
AGGRESSIVE → size 120%, threshold -2, trends forts confirmés uniquement
```
- `NORMAL → DEFENSIVE` : drawdown > 3% sur 10 cycles OU vol > 2× ATR médian
- `DEFENSIVE → RISK_OFF` : drawdown > 6% OU 3 pertes consécutives
- `RISK_OFF → RECOVERY` : 10 cycles sans perte OU vol revenue sous seuil
- `RECOVERY → NORMAL` : 20 cycles stables OU PnL+ sur 15 cycles
- `NORMAL → AGGRESSIVE` : trend fort + vol stable + 10 cycles PnL+
- Délai minimum entre transitions : 5 cycles

**2. Dynamic Exposure Manager**
- Exposition max par trade selon état (100% / 50% / 0% / 25% / 120%)
- `exposure_used` tracker — plafond exposition totale par état

**3. Circuit Breaker — robuste**
```
HEALTHY  → normal
UNSTABLE → 2 échecs, backoff 30s
DEGRADED → 5 échecs, suspension composant, stub par défaut
DISABLED → 10 échecs, arrêt total, escalation
```
- Backoff exponentiel : 30s, 60s, 120s, 300s, 600s
- Recovery périodique : 300s en DEGRADED, 1800s en DISABLED

**4. Capital Throttle**
- DD > 5% : réduction linéaire size (-10% par palier de 1% DD)
- DD > 10% : RISK_OFF forcé
- Retour progressif : 5 cycles minimum

**5. Volatility Emergency Mode**
- Vol > 3× ATR médian 50 cycles → suspension immédiate trades
- Positions protégées par SL large (3× ATR)
- Durée minimale : 5 cycles après retour sous seuil

### Critères de succès P7
- [ ] Passage DEFENSIVE dans les 3 cycles après DD > 3%
- [ ] Aucun trade en RISK_OFF
- [ ] Circuit breaker DEGRADED après 5 échecs
- [ ] Capital throttle proportionnel au drawdown

---

## P8 — Dynamic Intelligence (Strategy Allocator)

**Objectif** : allocation dynamique des stratégies, contextuelle et apprenante.

### Composants

**1. Strategy Allocator — matrice contextuelle**
```
                    MEAN_REV  BREAKOUT  SCALP  MOMENTUM  GRID
SIDEWAYS             0.45      0.10     0.30    0.05     0.10
TREND_BULL           0.10      0.40     0.05    0.35     0.10
TREND_BEAR           0.15      0.20     0.10    0.40     0.15
HIGH_VOL             0.10      0.10     0.40    0.10     0.30
CHOPPY               0.30      0.10     0.25    0.10     0.25
```
- Poids normalisés, évolués par feedback de performance

**2. Confidence Scoring avec mémoire**
```
confidence = base * decay^temps_sans_trade
           + winrate_recent * 0.4
           + sharpe_recent * 0.3
           + regime_consistency * 0.3
```
- Fenêtre glissante 20 trades
- `decay_factor` = 0.95 par cycle sans trade

**3. Strategy Probation System**
- `TRACKING` → `PROBATION` (25% capital, après 5 trades)
- `PROBATION` → `ACTIVE` (WR > 35% ET Sharpe > 0.3, après 20 trades)
- `PROBATION` → `PROBATION_EXTENDED` → `SUSPENDED`
- Réévaluation suspendue : tous les 100 cycles ou changement régime majeur

**4. Dynamic Weighting Engine**
- Ajustement chaque fin de cycle, proportionnel à performance relative
- `momentum_term` : max ±0.05 par cycle
- `diversification_penalty` si poids > 0.6

**5. Correlation Monitor**
- Corrélation signaux > 0.7 → avertissement
- Corrélation > 0.85 → réduction 30% poids stratégie moins performante

### Critères de succès P8
- [ ] Poids significativement différents entre 2 régimes distincts
- [ ] Aucune stratégie > 60% capital total
- [ ] Au moins 1 stratégie en TRACKING ou PROBATION après 50 cycles
- [ ] Corrélation moyenne < 0.6

---

## P9 — Meta Governance

**Objectif** : supervision globale, détection de dérives comportementales, ajustement haut niveau.

### Composants

**1. System Health Monitor**
- Métriques : latence composants, taux d'erreur, CPU/RAM, retry count, état circuit breaker
- Dashboard `health_dashboard` : GREEN / YELLOW / RED par composant
- Alerte YELLOW > 20 cycles → escalation, RED → immédiat

**2. Behavioral Drift Detector**
- Métriques surveillées : threshold moyen, taux d'activité, distribution scores, taux refus
- Dérive = écart > 2 écarts-types sur fenêtre historique
- Action : alerte + suggestion recalibration + option reset partiel

**3. Self-Monitoring Loop**
- Le Behavioral Drift Detector est lui-même surveillé
- `meta_health_score` agrège : santé composants + absence dérive + stabilité transitions
- Si score < 0.6 → alerte niveau 2

**4. Anomaly Governance**
- Anomalies : +10× trades soudain, score moyen -20 pts, threshold +5 pts / 10 cycles, transitions RiskGovernor > 3 / 10 cycles
- Réaction : log snapshot → suspension temporaire → reset paramètres → reprise progressive

**5. Performance Supervisor**
- Sharpe glissant (20/50/100 trades), Profit Factor, Max Drawdown
- Comparaison réel vs Shadow Engine
- Écart > 2σ → alerte dérive d'exécution

**6. Portfolio Intelligence**
- Concentration : corrélation paires, concentration exchange/stratégie, exposition nette
- Si facteur > 60% → alerte + rééquilibrage auto
- Exposition nette > 80% → réduction forcée

### Critères de succès P9
- [ ] Dérive simulée détectée (threshold poussé à 80 pendant 30 cycles)
- [ ] Suspension avant 3 pertes consécutives sur dérive
- [ ] Sharpe glissant calculé en temps réel
- [ ] 0 faux positif sur 100 cycles en régime stable

---

## P10+ — Evolutionary Architecture (vision)

- Auto-optimisation hyperparamètres : boucle externe teste variations, conserve les meilleures
- Génération de stratégies : exploration combinaisons indicateurs → conservation par régime
- Mémoire épisodique : configurations gagnantes rejouées sur contextes similaires
- Apprentissage par renforcement : politique allocation apprise par RL, récompense = Sharpe glissant

---

## Synthèse cybernétique par phase

| Concept | P6 | P7 | P8 | P9 |
|---------|----|----|----|----|
| Feedback loop | regret → threshold | état → exposition | performance → poids | santé → alerte |
| Hystérésis | transitions régime | transitions état | changements poids | déclenchement anomalies |
| PID control | threshold adaptatif | capital throttle | momentum weighting | dérive → correction |
| State machine | régimes de marché | RiskGovernor | probation status | health status |
| Signal damping | rampe de transition | backoff exponentiel | plafond ±0.05/cycle | suspension progressive |
| Mémoire | EWMA regret | historique drawdown | fenêtre 20 trades | historique dérive |
| Anti-oscillation | delta signe bloqué | délai 5 cycles min | diversification penalty | meta_health_score |

---

## Anti-patterns à surveiller

- **P6** : threshold oscillant → damping + hystérésis
- **P7** : RiskGovernor trop instable → délai minimum 5 cycles entre transitions
- **P8** : une stratégie capte tout le capital → diversification_penalty à 60%
- **P9** : meta-gouvernance génère plus d'alertes que le système → meta_health_score

---

## État des modules P6 (existants à câbler)

| Module | Fichier | Statut |
|--------|---------|--------|
| RegimeDetector | `quant_hedge_ai/intelligence/regime_detector.py` | Existant — v1 |
| RegretEngine | `anara_context/modules/regret_engine.json` + impl | Existant |
| GlobalRiskGate | `quant_hedge_ai/risk/global_risk_gate.py` | Existant |
| MetaStrategyEngine | `tracker_system/meta_strategy_engine.py` | Existant |
| ActivityTracker | à localiser | À vérifier |
| RegimeTransitionSmoother | non trouvé | À créer |
| AdaptiveThresholdEngine | non trouvé | À créer |

---

## Fichiers de pilotage

| Fichier | Rôle |
|---------|------|
| `ROADMAP.md` | Vision globale |
| `advisor_loop.py` | Point d'entrée principal |
| `test_boot_system.py` | Validation 63/63 |
| `scripts/deploy_vps.sh` | Auto-deploy git → VPS |
